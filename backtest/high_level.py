import gc 
from decimal import Decimal
from pathlib import Path
import sys
from turtle import st
from utils.data_loader import loader

# Nautilus Imports
from nautilus_trader.backtest.node import (
    BacktestDataConfig,
    BacktestEngineConfig,
    BacktestNode,
    BacktestRunConfig,
    BacktestVenueConfig
)
from nautilus_trader.backtest.results import BacktestResult
from nautilus_trader.config import ImportableStrategyConfig
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.model.data import Bar, BarType 
from nautilus_trader.common.config import LoggingConfig

# Path setup
BASE_DIR: Path = Path(__file__).resolve().parent
RAW_DATA_PATH: Path = BASE_DIR.parent / "data" / "raw"
# 设置 Parquet 输出目录
output_dir = RAW_DATA_PATH / "parquet"


# 1. 定义 Instrument
instrument = TestInstrumentProvider.ethusdt_perp_binance()

# 2. 定义 BarType (确保 Strategy 和 Loader 使用完全相同的定义)
# 该部分依照 k 线来源进行分类，如果不是基于 tick 或者 quote 生成的 k 线，建议使用 EXTERNAL
bar_type_str = f"{instrument.id}-5-MINUTE-LAST-EXTERNAL"
bar_type_def = BarType.from_str(bar_type_str)

# 3. 加载 CSV 数据并转换为 Parquet 格式的 Catalog
parquet_catalog, catalog_path = loader(
    csv_path = RAW_DATA_PATH / "binance-ETHUSDT-1h-2025-01-01_2025-12-25.csv",
    output_dir= output_dir,
    instrument=instrument,
    bar_type=bar_type_def,
)
del parquet_catalog 

# 3. 强制垃圾回收（释放 Pandas 占用的内存）
gc.collect()
print("🧹 内存清理完成，准备回测...")


# 4. 配置 Venue (交易所)
venue_configs: list[BacktestVenueConfig] = [
    BacktestVenueConfig(
        name="BINANCE",
        oms_type="HEDGING",
        account_type="MARGIN",
        base_currency="USDT",
        # 🔧 修正 1: 增加本金，防止资金不足
        starting_balances=["1_000_000 USDT"], 
    ),
]

# 5. 配置 Data (告诉引擎读什么数据)
data_configs: list[BacktestDataConfig] = [
    BacktestDataConfig(
        catalog_path=str(catalog_path),
        # 🔧 修正 2: 这里必须是 Bar，因为你加载的是 K线
        data_cls=Bar, 
        instrument_id=instrument.id,
        # 建议：如果是刚生成的数据，可以不写 start/end，让引擎自动读取全部
        start_time="2025-01-01", 
        end_time="2025-12-20",
    ),
]

# 6. 配置 Strategy
strategies = [
    ImportableStrategyConfig(
        strategy_path="nautilus_trader.examples.strategies.ema_cross:EMACross",
        config_path="nautilus_trader.examples.strategies.ema_cross:EMACrossConfig",
        config={
            "instrument_id": instrument.id,
            "bar_type": bar_type_str, # 必须和上面定义的字符串完全一致
            "fast_ema_period": 10,
            "slow_ema_period": 20,
            # 🔧 修正 3: 调整下单数量，或者配合上面的本金调整
            "trade_size": Decimal("3")
        },
    ),
]

eng_cfg = BacktestEngineConfig(
    # trader_id=TraderId("BACKTESTER-001"),
    strategies=strategies,
    logging=LoggingConfig(
        log_level="INFO",       # 减少日志输出，只看警告及以上，提高回测速度
        log_colors=True,
        use_pyo3=True,          # 是否使用 Rust 优化的日志组件
    ),
)

# 7. 运行配置
config = BacktestRunConfig(
    engine=eng_cfg,
    data=data_configs,
    venues=venue_configs,
    # 也可以在这里设置全局的回测时间范围
    # start_time="2025-01-01",
    # end_time="2025-12-31",
)

# 8. 执行
node = BacktestNode(configs=[config])
print("开始回测...")
results: list[BacktestResult] = node.run()

# 9. 简单打印结果
# 强制刷新缓冲区，确保这句话一定能打印出来
print("✅ node.run() 已返回！程序正常结束。", flush=True)

if results:
    result = results[0] # 获取第一个回测结果
    
    print("\n" + "="*65)
    print("🏆 最终回测报告 (MANUAL REPORT)")
    print("="*65)
    
    # 1. 基础信息 (直接从类属性获取)
    print(f"🆔 Run ID:        {result.run_id}")
    print(f"⏱️ 耗时:           {result.elapsed_time:.4f} 秒")
    print(f"📦 总事件数:       {result.total_events}")
    print(f"📝 总订单数:       {result.total_orders}")
    print(f"📍 总持仓数:       {result.total_positions}")
    print("-" * 65)

    # 2. 打印 PnL 统计 (从 stats_pnls 字典中获取)
    # stats_pnls 结构通常是: {'USDT': {'PnL (total)': 100.0, ...}, 'ETH': {...}}
    if result.stats_pnls:
        # 我们遍历所有的币种统计（通常主要是 USDT）
        for currency, metrics in result.stats_pnls.items():
            print(f"💰 盈亏统计 ({currency}):")
            
            # 尝试获取一些关键指标，如果字典里有就打印，没有就跳过或打印全部
            # 这里为了保险，我们打印字典里所有的非 NaN 值
            for metric_name, value in metrics.items():
                # 过滤掉 NaN 值以保持整洁 (Python中 float('nan') != float('nan'))
                if value == value: 
                    print(f"   - {metric_name:<20}: {value:,.4f}")
            print("-" * 30)
    else:
        print("⚠️ 未找到 PnL 统计数据")

    # 3. 打印回报率统计 (从 stats_returns 字典中获取)
    # stats_returns 结构通常是: {'Sharpe Ratio (252 days)': 2.5, ...}
    if result.stats_returns:
        print("📈 回报率/风险统计:")
        for metric_name, value in result.stats_returns.items():
            if value == value: # 过滤 NaN
                print(f"   - {metric_name:<25}: {value:.4f}")
    else:
        print("⚠️ 未找到回报率统计数据")

    print("="*65 + "\n")

else:
    print("❌ 没有任何回测结果生成")

# 显式退出
sys.exit(0)