from decimal import Decimal
from pathlib import Path
from typing import Optional

from nautilus_trader.model import Money
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import BarAggregation, PriceType

from config.definitions import (
    BackTestConfig,
    DataConfig,
    InstrumentConfig,
    InstrumentType,
    LogConfig,
    MLConfig,
    StrategyConfig,
)

# ==========================================
# 1. 基础回测参数设定 (Basic User Settings)
# ==========================================

# 交易标的定义
SYMBOL = "SOL"
QUOTE = "USDT"
VENUE = "OKX"  # OKX or BINANCE
INSTRUMENT_TYPE = InstrumentType.SWAP  # Usually SWAP for perps

# 回测时间段
# 不定义的话会自动使用提供数据的起止范围
START_DATE = "2022-01-01"
END_DATE = "2026-01-14"
# 有些币种，如 SOL 没有那么长的历史，获取数据会失败需要特别注意

# 数据配置 (Data Configuration)
# 策略使用的主周期和趋势辅助周期
# 注意：文件名格式必须匹配 data_retrival.py 生成的格式
# 格式: {VENUE}-{SYMBOL}{QUOTE}-{TIMEFRAME}-{START}_{END}.csv
MAIN_TIMEFRAME = "1h"
TREND_TIMEFRAME = "4h"  # TODO： 该部分设计应该是在单独的策略里面定义，如 dual_thrust 策略需要趋势和信号时间粒度，则单独指明

# 下单参数 (Order Parameters)
STRATEGY_LEVERAGE: int = 3
RISK_QTY_PERCENT: Decimal = Decimal("0.2")  # 每次交易占权益百分比
INIT_BALANCES: list = [Money("100", USDT)]

# 日志配置
LOGGING_SETTINGS = LogConfig(
    log_level="INFO",
    log_level_file="DEBUG",
    log_colors=True,
    use_pyo3=True,
    log_component_levels={
        "Portfolio": "INFO",
        "BacktestEngine": "INFO",
        "DualThrust": "DEBUG",
    },
    log_components_only=True,
)

# 机器学习配置
ML_SETTINGS = MLConfig(
    ema_period=50,
    rsi_period=14,
    rsi_oversold=30,
    rsi_overbought=70,
    stop_loss_pct=0.015,
    take_profit_pct=0.03,
    horizon_bars=36,
    use_ai_filter=False,
    model_path="data/models/lgbm_mtf_v1.joblib",
    min_prob_threshold=0.3,
    record_features=True,
    record_path="data/record/features_log.csv",
)


def get_data_config(
    symbol: str,
    quote: str,
    venue: str,
    timeframe: str,
    start: str,
    end: str,
    label: str = "main",
    instrument_id: Optional[str] = None,
) -> DataConfig:
    # TODO: 搞清楚这个 symbol，quote 是什么关系？
    """生成数据配置"""

    # 解析 timeframe 字符串到 Nautilus 枚举 (简化处理，假设 1h, 4h, 1m, 1d)
    if timeframe.endswith("h"):
        agg = BarAggregation.HOUR
        period = int(timeframe[:-1])
    elif timeframe.endswith("m"):
        agg = BarAggregation.MINUTE
        period = int(timeframe[:-1])
    elif timeframe.endswith("d"):
        agg = BarAggregation.DAY
        period = int(timeframe[:-1])
    else:
        # Default fallback
        agg = BarAggregation.MINUTE
        period = 1

    return DataConfig(
        csv_file_name=f"{symbol}{quote}/{venue.lower()}-{symbol}{quote}-{timeframe}-{start}_{end}.csv",
        bar_aggregation=agg,
        bar_period=period,
        price_type=PriceType.LAST,  # TODO: 多类型 PriceType 处理
        label=label,
        instrument_id=instrument_id,
    )


# ==========================================
# 3. 动态构建配置对象 (Dynamic Construction)
# ==========================================

active_instrument = InstrumentConfig(
    venue_name=VENUE,
    quote_currency=SYMBOL,
    base_currency=QUOTE,
    type=INSTRUMENT_TYPE,
    leverage=STRATEGY_LEVERAGE,  # 杠杆在这里导入
)

# TODO: 数据生成与处理完全自动化，即使是多类型数据也能自己搞定
data_main = get_data_config(
    SYMBOL, QUOTE, VENUE, MAIN_TIMEFRAME, START_DATE, END_DATE, label="main"
)
data_trend = get_data_config(
    SYMBOL, QUOTE, VENUE, TREND_TIMEFRAME, START_DATE, END_DATE, label="trend"
)
# 演示：如果需要多源数据（例如 RS-Squeeze 的基准数据）
# data_benchmark = get_data_config("BTC", "USDT", "BINANCE", MAIN_TIMEFRAME, START_DATE, END_DATE, label="benchmark")

DUAL_THRUST_STRATEGY = StrategyConfig(
    name="DualThrust",
    module_path="strategy.dual_thrust",
    config_class="DualThrustConfig",
    params={
        "instrument_id": active_instrument.instrument_id,
        # 核心参数 (Core Params)
        "lookback_period": 4,
        "k1": 0.5,
        "k2": 0.5,
        "trend_ema_period": 200,
        "atr_period": 20,
        # 资金管理 (Money Management)
        "qty_percent": RISK_QTY_PERCENT,
        # 风控 (Risk Management)
        "stop_loss_atr_mult": 1.5,
        "stop_loss_pct": 0.015,
        "use_auto_sl": False,  # DualThrust uses its own ATR stop, so disable base auto-SL
    },
)

# ==========================================
# 4. 最终导出 (Export)
# ==========================================

current_config = BackTestConfig(
    # 子集配置
    instrument=active_instrument,
    # 核心：使用 data_feeds 列表支持无限扩展的数据供给框架
    data_feeds=[
        # stores labels as different INSTRUMENT
        data_main,
        data_trend,
        # data_benchmark,
    ],
    strategy=DUAL_THRUST_STRATEGY,  # 在这里切换策略
    # 策略里面永远都不能明显指定交易标的，交易标的应该人工指定，策略只管在特定的标的上计算和发送订单
    # 基础配置
    start_date=START_DATE,
    end_date=END_DATE,
    initial_balances=INIT_BALANCES,
    output_html_report=False,
    # 其他配置
    logging=LOGGING_SETTINGS,
    ml=None,
)
