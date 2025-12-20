# %% [markdown]
# # 1. 初始化回测引擎 (Engine Configuration)
# 这里是整个系统的起点。我们需要定义“谁”在交易（TraderId），以及系统的日志级别。

# %%
import pandas as pd
from decimal import Decimal

# Nautilus 核心组件
from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.model import TraderId, Money
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import OmsType, BookType, AccountType

# 交易所适配器配置 (这里只用作 Venue 的标识符)
from nautilus_trader.adapters.binance import BINANCE_VENUE

# 配置回测引擎
config = BacktestEngineConfig(
    trader_id=TraderId("BACKTESTER-001"),
    logging=LoggingConfig(
        log_level="WARNING",  # 减少日志输出，只看警告及以上，提高回测速度
        log_colors=True,
        use_pyo3=False,       # 是否使用 Rust 优化的日志组件
    ),
)

# 实例化引擎
engine = BacktestEngine(config)

# %% [markdown]
# # 2. 配置 Venue (交易场所)与 OMS
# 这里对应了我们之前讨论的 **OMS** 概念。
# - `oms_type`: 决定了持仓是合并(Netting)还是独立(Hedging)。
# - `account_type`: 定义账户性质（现货、保证金、期货等）。

# %%
# 添加 Venue（交易所）配置
engine.add_venue(
    venue=BINANCE_VENUE,
    # 【重点】这里定义了 OMS 为净额结算模式，意味着同方向订单会合并，反向订单会平仓
    oms_type=OmsType.NETTING,
    # 订单簿类型：L1_MBP 表示 Level 1 (最优买卖价) Market By Price
    book_type=BookType.L1_MBP,
    # 账户类型：注意，原代码使用的是 MARGIN (现货杠杆)，
    # 如果交易永续合约(Perp)，通常应使用 AccountType.FUTURE，但在此仅作演示不影响运行。
    account_type=AccountType.MARGIN,
    base_currency=USDT,  # 账户本位币
    starting_balances=[Money(1_000_000.0, USDT)],  # 初始资金 100万 USDT
    # 开启简易撮合模式，不需要完整的 L2/L3 数据，仅用 L1 数据即可回测
    trade_execution=True,
)

# %% [markdown]
# # 3. 配置 Instrument (交易标的)
#
# **关于你的疑问：TestInstrumentProvider 是什么？**
# 它并不是一种“仅供娱乐”的玩具。在 NT 中，`Instrument` 对象本质上是一组**元数据（Metadata）**，
# 包含：精度（tick size）、最小交易量（lot size）、合约乘数等。
#
# 正常实盘时，这些数据会从交易所 API 自动下载。
# 但在回测时，我们需要手动提供这些数据。`TestInstrumentProvider` 只是一个**预设的工厂类**，
# 帮我们快速生成标准化的 `Instrument` 对象，免去了手动编写一大堆参数的麻烦。
# 它生成的对象是完全合法的标准 Instrument 对象。

# %%
from nautilus_trader.test_kit.providers import TestInstrumentProvider

# 从预设库中加载 "ETHUSDT 永续合约" 的标的信息
# 这会自动包含价格精度、数量精度等关键信息
inst = TestInstrumentProvider.ethusdt_perp_binance()
print(f"已加载交易标的: {inst.id}")

# 将标的注册到引擎中
engine.add_instrument(inst)

# %% [markdown]
# # 4. 数据加载与清洗 (Data Wrangling)
# NT 是事件驱动的，需要将 CSV 数据转换成系统能理解的 `Bar` 对象。

# %%
from nautilus_trader.model import BarType
from nautilus_trader.persistence.wranglers import BarDataWrangler

# 定义数据类型：Binance 交易所的 5分钟 K线
# 格式解析: [INSTRUMENT]-[TIMEFRAME]-[BAR_AGGREGATION]-[SOURCE]
bar_type = BarType.from_str("ETHUSDT-PERP.BINANCE-5-MINUTE-LAST-EXTERNAL")

# 初始化数据转换器 (Wrangler)
wrangler = BarDataWrangler(bar_type, inst)

# 读取 CSV 数据
# 假设 CSV 路径正确，且包含 timestamp, open, high, low, close, volume 列
try:
    df = pd.read_csv("../data/binance-ETHUSDT-5m-2025-01-01_2025-12-20.csv")
    
    # 处理时间戳：转换为 datetime 对象
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    
    # 【关键逻辑说明】
    # 很多数据源（如 Binance）的 timestamp 是 K线的“开始时间”。
    # NautilusTrader 的匹配引擎通常使用“结束时间”作为 Bar 的生效时间。
    # 所以这里 +5分钟，是为了把 timestamp 修正为 K线的 Close Time。
    df["timestamp"] = df["timestamp"] + pd.Timedelta(minutes=5)
    
    # 设置索引并筛选列
    df.set_index("timestamp", inplace=True)
    df = df[["open", "high", "low", "close", "volume"]]

    print("数据预处理预览：")
    print(df.head())

    # 将 Pandas DataFrame 转换为 NT 的 Bar 对象列表
    bars = wrangler.process(df)

    # 将数据加载进引擎
    engine.add_data(bars)
    
    print(f"成功加载 {len(bars)} 条 K线数据")

except FileNotFoundError:
    print("错误：找不到数据文件，请检查路径。")
    # 为了防止代码报错停止，这里创建一个空列表（实际运行时请确保有数据）
    bars = []

# 查看初始账户状态
print("\n初始账户状态:")
print(engine.trader.generate_account_report(BINANCE_VENUE))

# %% [markdown]
# # 5. 策略与执行算法配置
# 这里我们将策略 (Strategy) 和执行算法 (Execution Algorithm) 挂载到引擎上。
# - **Strategy**: 大脑，决定“买什么、什么时候买”。
# - **Exec Algorithm (TWAP)**: 手脚，决定“怎么买”（例如拆单执行，减少滑点）。

# %%
from nautilus_trader.examples.algorithms.twap import TWAPExecAlgorithm
from nautilus_trader.examples.strategies.ema_cross_twap import EMACrossTWAP, EMACrossTWAPConfig

# 5.1 配置策略参数
strategy_config = EMACrossTWAPConfig(
    instrument_id=inst.id,
    bar_type=bar_type,             # 使用前面定义的 BarType
    trade_size=Decimal("0.10"),    # 每次交易 0.1 个 ETH
    fast_ema_period=10,            # 快线周期
    slow_ema_period=20,            # 慢线周期
    twap_horizon_secs=10.0,        # TWAP 执行总时长
    twap_interval_secs=2.5,        # TWAP 拆单间隔
)

# 5.2 实例化并添加策略
strategy = EMACrossTWAP(config=strategy_config)
engine.add_strategy(strategy)

# 5.3 实例化并添加执行算法
# 注意：在这个特定的示例策略中，策略内部会调用这个 Exec Algo
exec_algorithm = TWAPExecAlgorithm()
engine.add_exec_algorithm(exec_algorithm)

# %% [markdown]
# # 6. 运行回测 (Run Engine)

# %%
print("\n开始运行回测...")
engine.run()
print("回测结束。")

# %% [markdown]
# # 7. 报告与分析 (Reporting)
# 使用 Pandas context manager 格式化输出，便于在控制台查看。

# %%
with pd.option_context(
    "display.max_rows", 10,
    "display.max_columns", None,
    "display.width", 300,
):
    print("\n=== 账户最终资金报告 ===")
    print(engine.trader.generate_account_report(BINANCE_VENUE))
    
    print("\n=== 订单成交记录 (Fills) ===")
    print(engine.trader.generate_order_fills_report())
    
    print("\n=== 持仓记录 (Positions) ===")
    # 这里的 Positions 展示逻辑受 OMS (NETTING/HEDGING) 的直接影响
    print(engine.trader.generate_positions_report())

# %% [markdown]
# # 8. 可视化 (Tearsheet)
# 如果安装了 Plotly，可以生成交互式的 HTML 报表。

# %%
try:
    from nautilus_trader.analysis import TearsheetConfig
    from nautilus_trader.analysis.tearsheet import create_tearsheet

    print("\n正在生成可视化报表 (Tearsheet)...")

    # 配置报表主题: "plotly_white", "plotly_dark", "nautilus", "nautilus_dark"
    tearsheet_config = TearsheetConfig(theme="plotly_white")

    create_tearsheet(
        engine=engine,
        output_path="crypto_ethusdt_tearsheet.html",
        config=tearsheet_config,
    )
    print("报表已保存至: crypto_ethusdt_tearsheet.html")
    print("请在浏览器中打开该文件查看交互式图表。")

except ImportError:
    print("\n提示: 未安装 Plotly，无法生成图表。")
    print("请运行: pip install plotly>=6.3.1")
except Exception as e:
    print(f"\n生成报表时发生错误: {e}")

# %% [markdown]
# # 9. 清理资源
# 这是一个良好的编程习惯，释放 C++/Rust 底层的内存资源。

# %%
engine.reset()
engine.dispose()
print("引擎资源已释放。")