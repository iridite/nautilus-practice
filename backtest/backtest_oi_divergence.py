"""
OI Divergence 策略回测脚本

演示如何使用 NautilusTrader 回测引擎测试 OI Divergence 策略。
包含 OHLCV、Open Interest 和 Funding Rate 数据的加载和处理。

Usage:
    uv run python backtest/backtest_oi_divergence.py
"""

from decimal import Decimal
from pathlib import Path

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.backtest.modules import FXRolloverInterestModule
from nautilus_trader.core.datetime import dt_to_unix_nanos
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.test_kit.providers import TestInstrumentProvider

from config.settings import END_DATE, INITIAL_BALANCES, START_DATE, VENUE
from strategy.oi_divergence import OIDivergence, OIDivergenceConfig
from utils.custom_data import FundingRateData, OpenInterestData
from utils.oi_funding_adapter import OIFundingDataLoader, merge_custom_data_with_bars

# ==========================================
# 配置参数
# ==========================================

# 交易品种
SYMBOL = "BTCUSDT"
INSTRUMENT_ID = f"{SYMBOL}.{VENUE}"

# 数据周期
MAIN_TIMEFRAME = "1h"  # 主执行周期
TREND_TIMEFRAME = "4h"  # 趋势判断周期（可选）

# 项目路径
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "raw"


# ==========================================
# 数据加载函数
# ==========================================


def load_ohlcv_data(engine: BacktestEngine, symbol: str, timeframe: str):
    """
    加载 OHLCV 数据到回测引擎

    Parameters
    ----------
    engine : BacktestEngine
        回测引擎实例
    symbol : str
        交易对符号
    timeframe : str
        时间周期
    """
    safe_symbol = symbol.replace("/", "")
    filename = f"{VENUE.lower()}-{safe_symbol}-{timeframe}-{START_DATE}_{END_DATE}.csv"
    file_path = DATA_DIR / safe_symbol / filename

    if not file_path.exists():
        raise FileNotFoundError(f"OHLCV data file not found: {file_path}")

    # 解析 Bar 类型
    bar_type = BarType.from_str(f"{INSTRUMENT_ID}-{timeframe.upper()}-LAST")

    # 使用 BarDataWrangler 加载数据
    wrangler = BarDataWrangler(
        bar_type=bar_type, instrument=engine.cache.instrument(INSTRUMENT_ID)
    )

    # 读取 CSV 并转换
    import pandas as pd

    df = pd.read_csv(file_path)

    # 确保列名正确
    if "datetime" not in df.columns and "timestamp" in df.columns:
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")

    # 处理数据
    bars = wrangler.process(df)

    # 添加到引擎
    engine.add_data(bars)

    print(f"✅ Loaded {len(bars)} bars for {symbol} ({timeframe})")
    return bars


def load_custom_data(engine: BacktestEngine, symbol: str):
    """
    加载 OI 和 Funding Rate 数据到回测引擎

    Parameters
    ----------
    engine : BacktestEngine
        回测引擎实例
    symbol : str
        交易对符号
    """
    from nautilus_trader.model.identifiers import InstrumentId

    instrument_id = InstrumentId.from_str(INSTRUMENT_ID)

    # 初始化数据加载器
    loader = OIFundingDataLoader(PROJECT_ROOT)

    # 加载自定义数据
    custom_data = loader.load_all_custom_data(
        symbol=symbol,
        instrument_id=instrument_id,
        start_date=START_DATE,
        end_date=END_DATE,
        exchange=VENUE.lower(),
        oi_period=MAIN_TIMEFRAME,
    )

    # 合并并排序数据
    merged_data = merge_custom_data_with_bars(custom_data["oi"], custom_data["funding"])

    # 添加到引擎
    if merged_data:
        engine.add_data(merged_data)
        print(
            f"✅ Loaded {len(custom_data['oi'])} OI points and "
            f"{len(custom_data['funding'])} Funding Rate points"
        )
    else:
        print("⚠️  Warning: No custom data loaded. Strategy may not function properly.")

    return custom_data


# ==========================================
# 回测主函数
# ==========================================


def run_backtest():
    """执行 OI Divergence 策略回测"""

    print("\n" + "=" * 70)
    print("🚀 OI Divergence Strategy Backtest")
    print("=" * 70)

    # === 1. 创建回测引擎 ===
    config = BacktestEngineConfig(
        bypass_logging=False,
        run_analysis=True,
    )

    engine = BacktestEngine(config=config)

    # === 2. 添加场所和账户 ===
    venue = Venue(VENUE)

    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=USDT,
        starting_balances=INITIAL_BALANCES,
    )

    # === 3. 添加合约 ===
    # 使用测试合约提供商创建合约
    instrument = TestInstrumentProvider.btcusdt_binance()
    engine.add_instrument(instrument)

    print(f"\n📊 Instrument: {instrument.id}")
    print(f"   Price Precision: {instrument.price_precision}")
    print(f"   Size Precision: {instrument.size_precision}")

    # === 4. 加载 OHLCV 数据 ===
    print(f"\n📥 Loading data from {START_DATE} to {END_DATE}...")

    bars_main = load_ohlcv_data(engine, SYMBOL, MAIN_TIMEFRAME)

    # 可选：加载趋势周期数据
    # if TREND_TIMEFRAME:
    #     load_ohlcv_data(engine, SYMBOL, TREND_TIMEFRAME)

    # === 5. 加载自定义数据（OI + Funding Rate） ===
    print(f"\n📊 Loading OI and Funding Rate data...")
    custom_data = load_custom_data(engine, SYMBOL)

    # === 6. 配置策略 ===
    strategy_config = OIDivergenceConfig(
        instrument_id=INSTRUMENT_ID,
        bar_type=f"{INSTRUMENT_ID}-{MAIN_TIMEFRAME.upper()}-LAST",
        # trend_bar_type=f"{INSTRUMENT_ID}-{TREND_TIMEFRAME.upper()}-LAST" if TREND_TIMEFRAME else None,
        # === 下单参数 ===
        trade_size=0.01,  # 固定每次交易 0.01 BTC
        # 或者使用动态仓位：
        # qty_percent=Decimal("0.1"),  # 使用账户净值的 10%
        # leverage=3,  # 3倍杠杆
        # === 策略核心参数 ===
        lookback_bars=48,  # 48 小时回溯期（2天）
        oi_decline_threshold=0.05,  # OI 下降 5% 触发背离信号
        oi_lookback=12,  # OI 移动平均周期 12 小时
        # === 资金费率过滤 ===
        use_funding_filter=True,  # 启用资金费率过滤
        funding_rate_threshold_annual=30.0,  # 年化费率 30% 以上表示极度拥挤
        # === 入场参数 ===
        breakout_reentry_pct=0.002,  # 回撤 0.2% 进入
        # === 出场参数 ===
        tp_use_vwap=True,  # 止盈目标使用 VWAP
        vwap_period=48,  # VWAP 周期 48 小时
        stop_loss_pct=0.01,  # 硬止损 1%
        time_stop_bars=24,  # 时间止损 24 小时
        # === 风控参数 ===
        max_positions=1,  # 最大持仓数
        use_auto_sl=False,  # 禁用自动止损（已有手动止损）
    )

    # 创建策略实例
    strategy = OIDivergence(config=strategy_config)
    engine.add_strategy(strategy)

    print(f"\n⚙️  Strategy Configuration:")
    print(f"   Lookback Bars: {strategy_config.lookback_bars}")
    print(f"   OI Decline Threshold: {strategy_config.oi_decline_threshold:.1%}")
    print(
        f"   Funding Rate Threshold: {strategy_config.funding_rate_threshold_annual:.1f}% (annual)"
    )
    print(f"   Take Profit: VWAP-{strategy_config.vwap_period}")
    print(f"   Stop Loss: {strategy_config.stop_loss_pct:.1%}")
    print(f"   Time Stop: {strategy_config.time_stop_bars} bars")

    # === 7. 运行回测 ===
    print(f"\n🔄 Running backtest...")
    engine.run()

    # === 8. 输出结果 ===
    print("\n" + "=" * 70)
    print("📈 Backtest Results")
    print("=" * 70)

    # 获取账户信息
    account = engine.trader.generate_account_report(venue)
    print(f"\n💰 Account Summary:")
    print(account)

    # 获取订单报告
    order_fills = engine.trader.generate_order_fills_report()
    if not order_fills.empty:
        print(f"\n📋 Order Fills ({len(order_fills)} total):")
        print(order_fills.head(10))
    else:
        print(f"\n⚠️  No orders filled during backtest period")

    # 获取仓位报告
    positions = engine.trader.generate_positions_report()
    if not positions.empty:
        print(f"\n📊 Positions Report ({len(positions)} total):")
        print(positions.head(10))
    else:
        print(f"\n⚠️  No positions opened during backtest period")

    # 保存详细报告到文件
    output_dir = PROJECT_ROOT / "output" / "oi_divergence"
    output_dir.mkdir(parents=True, exist_ok=True)

    order_fills.to_csv(output_dir / "order_fills.csv", index=False)
    positions.to_csv(output_dir / "positions.csv", index=False)

    print(f"\n💾 Reports saved to: {output_dir}")

    print("\n" + "=" * 70)
    print("✅ Backtest Complete!")
    print("=" * 70 + "\n")

    return engine


# ==========================================
# 主入口
# ==========================================

if __name__ == "__main__":
    # 首先检查数据文件是否存在
    import sys

    safe_symbol = SYMBOL.replace("/", "")
    ohlcv_file = (
        DATA_DIR
        / safe_symbol
        / f"{VENUE.lower()}-{safe_symbol}-{MAIN_TIMEFRAME}-{START_DATE}_{END_DATE}.csv"
    )
    oi_file = (
        DATA_DIR
        / safe_symbol
        / f"{VENUE.lower()}-{safe_symbol}-oi-{MAIN_TIMEFRAME}-{START_DATE}_{END_DATE}.csv"
    )
    funding_file = (
        DATA_DIR
        / safe_symbol
        / f"{VENUE.lower()}-{safe_symbol}-funding-{START_DATE}_{END_DATE}.csv"
    )

    missing_files = []
    if not ohlcv_file.exists():
        missing_files.append(f"OHLCV: {ohlcv_file}")
    if not oi_file.exists():
        missing_files.append(f"OI: {oi_file}")
    if not funding_file.exists():
        missing_files.append(f"Funding: {funding_file}")

    if missing_files:
        print("\n❌ Error: Required data files not found:")
        for f in missing_files:
            print(f"   - {f}")
        print("\n💡 Please run the data fetching scripts first:")
        print(f"   1. Fetch OHLCV data:")
        print(f"      uv run python utils/data_retrival.py")
        print(f"   2. Fetch OI and Funding data:")
        print(f"      uv run python utils/oi_funding_fetcher.py")
        sys.exit(1)

    # 运行回测
    try:
        engine = run_backtest()
    except Exception as e:
        print(f"\n❌ Backtest failed with error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
