from decimal import Decimal
from pathlib import Path

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
STRATEGY_LEVERAGE = 5
RISK_QTY_PERCENT = Decimal("0.2")  # 每次交易占权益百分比
INIT_BALANCES = [Money("100", USDT)]

# ==========================================
# 2. 自动化配置生成 (Auto Configuration Factory)
# ==========================================


def find_data_file(
    symbol: str, quote: str, venue: str, timeframe: str, start: str, end: str
) -> str:
    """
    自动查找符合条件的数据文件。
    如果文件不存在，则预测其命名（因为 main.py 会在之后尝试下载它）。
    """
    base_dir = Path(__file__).parent.parent / "data" / "raw"
    symbol_folder = f"{symbol}{quote}"
    target_dir = base_dir / symbol_folder

    # 优先查找已经存在的文件
    if target_dir.exists():
        files = list(target_dir.glob(f"*{timeframe}*.csv"))
        if files:
            return f"{symbol_folder}/{files[0].name}"

    # 如果没找到，返回预测的路径（符合 data_retrival.py 的命名规则）
    # 格式: {SYMBOL}{QUOTE}/{VENUE.lower()}-{SYMBOL}{QUOTE}-{TIMEFRAME}-{START}_{END}.csv
    filename = f"{venue.lower()}-{symbol}{quote}-{timeframe}-{start}_{end}.csv"
    return f"{symbol_folder}/{filename}"


def get_data_config(
    symbol: str, quote: str, venue: str, timeframe: str, start: str, end: str
) -> DataConfig:
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
    )


# ==========================================
# 3. 动态构建配置对象 (Dynamic Construction)
# ==========================================

active_instrument = InstrumentConfig(
    venue_name=VENUE,
    quote_currency=SYMBOL,
    base_currency=QUOTE,
    type=INSTRUMENT_TYPE,
)

data_main = get_data_config(SYMBOL, QUOTE, VENUE, MAIN_TIMEFRAME, START_DATE, END_DATE)
data_trend = get_data_config(
    SYMBOL, QUOTE, VENUE, TREND_TIMEFRAME, START_DATE, END_DATE
)


def get_dual_thrust_strategy(
    instrument: InstrumentConfig,
    main_data: DataConfig,
    trend_data: DataConfig,
    risk_qty_percent: Decimal,
    leverage: int,
) -> StrategyConfig:
    """自动生成 Dual Thrust 策略配置"""
    return StrategyConfig(
        name="DualThrust",
        module_path="strategy.dual_thrust",
        config_class="DualThrustConfig",
        params={
            "instrument_id": instrument.instrument_id,
            "bar_type": f"{instrument.instrument_id}-{main_data.bar_type_str}",
            "trend_bar_type": f"{instrument.instrument_id}-{trend_data.bar_type_str}",
            # 核心参数 (Core Params)
            "lookback_period": 4,
            "k1": 0.5,
            "k2": 0.5,
            "trend_ema_period": 200,
            "atr_period": 20,
            # 资金管理 (Money Management)
            "qty_percent": risk_qty_percent,
            "leverage": leverage,
            # 风控 (Risk Management)
            "stop_loss_atr_mult": 1.5,
            "stop_loss_pct": 0.015,
            "use_auto_sl": False,  # DualThrust uses its own ATR stop, so disable base auto-SL
        },
    )


# 选择并实例化策略
DUAL_THRUST_STRATEGY = get_dual_thrust_strategy(
    active_instrument, data_main, data_trend, RISK_QTY_PERCENT, STRATEGY_LEVERAGE
)


# F. 日志配置
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


# ==========================================
# 4. 最终导出 (Export)
# ==========================================

current_config = BackTestConfig(
    # 子集配置
    instrument=active_instrument,
    data=data_main,
    aux_data=data_trend,
    strategy=DUAL_THRUST_STRATEGY,  # 在这里切换策略
    # 基础配置
    start_date=START_DATE,
    end_date=END_DATE,
    initial_balances=INIT_BALANCES,
    output_html_report=False,
    # 其他配置
    logging=LOGGING_SETTINGS,
    ml=None,
)
