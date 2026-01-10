from decimal import Decimal

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
    StrategyConfig,
    MLConfig,
)

# ==========================================
# 用户配置区域
# ==========================================

# 1. 标的配置
ETH_USDT_BINANCE = InstrumentConfig(
    venue="BINANCE",
    quote_currency="ETH",
    base_currency="USDT",
    type=InstrumentType.SWAP,
)

# 2. 数据配置
# 请确保文件名与 data/raw 下的一致
DATA_1H = DataConfig(
    csv_file_name="binance-ETHUSDT-1h-2025-01-01_2025-12-25.csv",
    bar_aggregation=BarAggregation.HOUR,
    bar_period=1,
    price_type=PriceType.LAST,
)

DATA_5M = DataConfig(
    csv_file_name="binance-ETHUSDT-5m-2025-01-01_2025-12-25.csv",
    bar_aggregation=BarAggregation.MINUTE,
    bar_period=5,
    price_type=PriceType.LAST,
)

# 3. ML 配置 (AI 过滤参数)
ML_SETTINGS = MLConfig(
    ema_period=50,
    rsi_period=14,
    rsi_oversold=30,
    rsi_overbought=70,
    stop_loss_pct=0.015,
    take_profit_pct=0.03,
    horizon_bars=24,
    use_ai_filter=True,  # 是否开启 AI 过滤
    model_path="data/models/lgbm_mtf_v1.joblib",
    min_prob_threshold=0.60,
    record_features=True,  # 是否记录特征供后续分析
    record_path="data/features_log.csv",
)

# 4. 策略配置
# BMR 策略
BMR_STRATEGY = StrategyConfig(
    name="BmrStrategy",
    module_path="strategy.bmr",
    config_class="BmrStrategyConfig",
    params={
        "size_type": "FIXED_NOTIONAL",
        "size_value": Decimal("1000"),
        "rsi_period": 14,
        "bb_period": 20,
        "bb_dev": 2.0,
        "atr_period": 14,
    }
)

# MACD 策略
MACD_STRATEGY = StrategyConfig(
    name="MACDEnhancedStrategy",
    module_path="strategy.macd_enhanced",
    config_class="MACDEnhancedConfig",
    params={
        "fast_period": 12,
        "slow_period": 26,
        "trade_size": 1000,
    }
)

# MTF_TREND
MTF_TREND_STRATEGY = StrategyConfig(
    name="MtfTrendPullbackStrategy",
    module_path="strategy.mtf_trend_pullback",
    config_class="MtfTrendPullbackConfig",
    params={
        # Instrument & BarTypes
        "instrument_id": "ETHUSDT-PERP.BINANCE",
        "trend_bar_type": "ETHUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL",
        "trade_bar_type": "ETHUSDT-PERP.BINANCE-5-MINUTE-LAST-EXTERNAL",

        # Strategy Params
        "ema_period": ML_SETTINGS.ema_period,
        "rsi_period": ML_SETTINGS.rsi_period,
        "rsi_oversold": ML_SETTINGS.rsi_oversold,
        "rsi_overbought": ML_SETTINGS.rsi_overbought,

        # Risk Management
        "qty_percent": Decimal("0.1"),
        "stop_loss_pct": Decimal(str(ML_SETTINGS.stop_loss_pct)),

        # AI Filtering
        "use_ai_filter": ML_SETTINGS.use_ai_filter,
        "model_path": ML_SETTINGS.model_path,
        "min_prob_threshold": ML_SETTINGS.min_prob_threshold,

        # Data Recording
        "record_features": ML_SETTINGS.record_features,
        "record_path": ML_SETTINGS.record_path,
    },
)

# 5. 回测环境配置
BACKTEST_SETTINGS = BacktestConfig(
    # Use date range from csv, when not indicate time span manually
    # start_date="2025-01-01",
    # end_date="2025-12-25",
    initial_balance=[Money("10000", USDT)],
)

# 6. 日志配置
# 注意：log_directory 将在运行时根据模式自动生成
LOGGING_SETTINGS = LogConfig(
    log_level="INFO",
    log_level_file="DEBUG",
    log_colors=True,
    use_pyo3=True,
)

# ==========================================
# 激活配置
# ==========================================

# 这里定义当前生效的配置
# 你可以创建多个 Config 对象，然后在 main.py 中选择，或者直接修改这里
current_config = GlobalConfig(
    instrument=ETH_USDT_BINANCE,
    data=DATA_5M,  # 主数据源 (交易层 5m)
    aux_data=DATA_1H,  # 辅助数据源 (趋势层 1h)
    strategy=MTF_TREND_STRATEGY,  # 使用 MTF 策略
    backtest=BACKTEST_SETTINGS,
    logging=LOGGING_SETTINGS,
    ml=ML_SETTINGS,
)
