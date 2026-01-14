import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from nautilus_trader.model import Money
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import BarAggregation, PriceType

from config.definitions import (
    BacktestConfig,
    DataConfig,
    GlobalConfig,
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
SYMBOL = "BTC"
QUOTE = "USDT"
VENUE = "OKX"  # OKX or BINANCE
INSTRUMENT_TYPE = InstrumentType.SWAP  # Usually SWAP for perps

# 回测时间段
START_DATE = "2020-01-01"
END_DATE = "2026-01-14"

# 数据配置 (Data Configuration)
# 策略使用的主周期和趋势辅助周期
# 注意：文件名格式必须匹配 data_retrival.py 生成的格式
# 格式: {VENUE}-{SYMBOL}{QUOTE}-{TIMEFRAME}-{START}_{END}.csv
MAIN_TIMEFRAME = "1h"
TREND_TIMEFRAME = "4h"

# 策略参数 (Strategy Parameters)
STRATEGY_LEVERAGE = 1
RISK_QTY_PERCENT = Decimal("0.5")  # 每次交易占权益百分比


# ==========================================
# 2. 自动化配置生成 (Auto Configuration Factory)
# ==========================================


def get_instrument_config(
    symbol: str, quote: str, venue: str, instr_type: InstrumentType
) -> InstrumentConfig:
    """生成标的配置"""
    # 针对不同标的的特殊处理可以放在这里
    leverage = 3
    if symbol == "DOGE":
        leverage = 1

    return InstrumentConfig(
        venue=venue,
        quote_currency=symbol,
        base_currency=quote,
        type=instr_type,
        leverage=leverage,
        maker_fee=0.0002,
        taker_fee=0.0005,
    )


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

    file_name = find_data_file(symbol, quote, venue, timeframe, start, end)

    return DataConfig(
        csv_file_name=file_name,
        bar_aggregation=agg,
        bar_period=period,
        price_type=PriceType.LAST,
    )


# ==========================================
# 3. 动态构建配置对象 (Dynamic Construction)
# ==========================================

# A. 标的
active_instrument = get_instrument_config(SYMBOL, QUOTE, VENUE, INSTRUMENT_TYPE)

# B. 数据
# 主数据 (用于交易执行)
data_main = get_data_config(SYMBOL, QUOTE, VENUE, MAIN_TIMEFRAME, START_DATE, END_DATE)
# 辅助数据 (用于趋势判断 - MTF)
data_trend = get_data_config(
    SYMBOL, QUOTE, VENUE, TREND_TIMEFRAME, START_DATE, END_DATE
)

# C. 机器学习/风控配置
ML_SETTINGS = MLConfig(
    ema_period=50,
    rsi_period=14,
    rsi_oversold=30,
    rsi_overbought=70,
    stop_loss_pct=0.015,
    take_profit_pct=0.03,
    horizon_bars=36,
    use_ai_filter=False,  # 默认关闭，按需开启
    model_path="data/models/lgbm_mtf_v1.joblib",
    min_prob_threshold=0.3,
    record_features=True,
    record_path="data/record/features_log.csv",
)


# D. 策略配置生成函数 (Strategy Factory)
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
        },
    )


def get_mtf_trend_strategy(
    instrument: InstrumentConfig,
    main_data: DataConfig,
    trend_data: DataConfig,
    ml_settings: MLConfig,
) -> StrategyConfig:
    """自动生成 MTF Trend Pullback 策略配置"""
    return StrategyConfig(
        name="MtfTrendPullbackStrategy",
        module_path="strategy.mtf_trend_pullback",
        config_class="MtfTrendPullbackConfig",
        params={
            "instrument_id": instrument.instrument_id,
            "trend_bar_type": f"{instrument.instrument_id}-{trend_data.bar_type_str}",
            "trade_bar_type": f"{instrument.instrument_id}-{main_data.bar_type_str}",
            "ema_period": ml_settings.ema_period,
            "qty_percent": Decimal("0.05"),
            "stop_loss_pct": 0.015,
            "leverage": 1,
            "use_ai_filter": ml_settings.use_ai_filter,
        },
    )


# 选择并实例化策略
# DUAL_THRUST (Dual Thrust Breakout Strategy)
DUAL_THRUST_STRATEGY = get_dual_thrust_strategy(
    active_instrument, data_main, data_trend, RISK_QTY_PERCENT, STRATEGY_LEVERAGE
)

# MTF_TREND (备用)
MTF_TREND_STRATEGY = get_mtf_trend_strategy(
    active_instrument, data_main, data_trend, ML_SETTINGS
)

# E. 回测环境
BACKTEST_SETTINGS = BacktestConfig(
    start_date=START_DATE,
    end_date=END_DATE,
    initial_balance=[Money("100", USDT)],
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


# ==========================================
# 4. 最终导出 (Export)
# ==========================================

current_config = GlobalConfig(
    instrument=active_instrument,
    data=data_main,
    aux_data=data_trend,
    strategy=DUAL_THRUST_STRATEGY,  # 在这里切换策略
    backtest=BACKTEST_SETTINGS,
    logging=LOGGING_SETTINGS,
    ml=ML_SETTINGS,
)
