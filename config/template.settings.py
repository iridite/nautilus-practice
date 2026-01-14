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
    MLConfig,
    StrategyConfig,
)

# ==========================================
# 用户配置区域
# ==========================================

# 1. 标的配置
# 关于杠杆 (leverage) 的说明：
# 1. 来源优先级：策略推荐杠杆 (Strategy Recommend) > 策略配置 (StrategyConfig.params) > 标的配置 (InstrumentConfig)。
#    - 优先级 1 (最高): 策略代码动态推荐的杠杆数（通过策略接口输出）。
#    - 优先级 2: 如果策略未推荐，则采用 `StrategyConfig` 的 `params` 中设置的 `leverage`。
#    - 优先级 3 (最低): 如果以上均未设置，则采用下方 `InstrumentConfig` 中设定的默认 `leverage`。
# 2. 自动上限保护：程序会结合交易所返回的 `instrument` 数据，确保最终开仓杠杆不超过交易所允许的最大上限。
# 3. 手续费配置 (Fees)：
#    - 可选配置 maker_fee 和 taker_fee (例如 0.0002 代表 0.02%)。
#    - 如果不配置且 venue 为 OKX，系统引擎将自动应用行业标准费率 (Maker 0.02%, Taker 0.05%)。
ETH_USDT_BINANCE = InstrumentConfig(
    venue="BINANCE",
    quote_currency="ETH",
    base_currency="USDT",
    type=InstrumentType.SWAP,
    leverage=3,  # 设定 3 倍杠杆
    maker_fee=0.0002,
    taker_fee=0.0005,
)

DOGE_USDT_OKX = InstrumentConfig(
    venue="OKX",
    quote_currency="DOGE",
    base_currency="USDT",
    type=InstrumentType.SWAP,
    leverage=1,
    maker_fee=0.0002,
    taker_fee=0.0005,
)

# 2. 数据配置
# 请确保文件名与 data/raw 下的一致
# TODO 出去 csv name 让 程序自己抓取并合成
DATA_4H = DataConfig(
    csv_file_name="binance-ETHUSDT-4h-2025-01-01_2025-12-25.csv",
    bar_aggregation=BarAggregation.HOUR,
    bar_period=4,
    price_type=PriceType.LAST,
)

DATA_1H = DataConfig(
    csv_file_name="okx-DOGEUSDT-1h-2024-01-01_2026-01-10.csv",
    bar_aggregation=BarAggregation.HOUR,
    bar_period=1,
    price_type=PriceType.LAST,
)

DATA_30M = DataConfig(
    csv_file_name="binance-ETHUSDT-30m-2025-01-01_2025-12-25.csv",
    bar_aggregation=BarAggregation.MINUTE,
    bar_period=30,
    price_type=PriceType.LAST,
)

DATA_5M = DataConfig(
    csv_file_name="okx-DOGEUSDT-5m-2024-01-01_2026-01-10.csv",
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
    horizon_bars=36,
    use_ai_filter=True,  # 是否开启 AI 过滤
    model_path="data/models/lgbm_mtf_v1.joblib",
    min_prob_threshold=0.3,
    record_features=True,  # 是否记录特征供后续分析
    record_path="data/record/features_log.csv",
)

# 4. 策略配置

# MTF_TREND
MTF_TREND_STRATEGY = StrategyConfig(
    name="MtfTrendPullbackStrategy",  # 必须与策略类名一致
    module_path="strategy.mtf_trend_pullback",
    config_class="MtfTrendPullbackConfig",
    params={
        # Instrument & BarTypes (will be auto-filled/validated in runner if possible, or manual here)
        "instrument_id": "ETHUSDT-PERP.BINANCE",
        "trend_bar_type": "ETHUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL",
        "trade_bar_type": "ETHUSDT-PERP.BINANCE-5-MINUTE-LAST-EXTERNAL",
        # Strategy Params
        "ema_period": ML_SETTINGS.ema_period,
        "rsi_period": ML_SETTINGS.rsi_period,
        "rsi_oversold": ML_SETTINGS.rsi_oversold,
        "rsi_overbought": ML_SETTINGS.rsi_overbought,
        # Risk Management
        "qty_percent": Decimal("0.05"),
        "stop_loss_pct": Decimal(str(ML_SETTINGS.stop_loss_pct)),
        "leverage": 3,  # 此处设置策略级的杠杆数，若策略有推荐则覆盖此处
        # AI Filtering
        "use_ai_filter": ML_SETTINGS.use_ai_filter,
        "model_path": ML_SETTINGS.model_path,
        "min_prob_threshold": ML_SETTINGS.min_prob_threshold,
        # Data Recording
        "record_features": ML_SETTINGS.record_features,
        "record_path": ML_SETTINGS.record_path,
    },
)

# DUAL_THRUST (New)
DUAL_THRUST_STRATEGY = StrategyConfig(
    name="DualThrust",  # 必须与策略类名一致
    module_path="strategy.dual_thrust",
    config_class="DualThrustConfig",
    params={
        # 使用 4H 数据对应的 ID 和 BarType
        # 注意: 外部加载的csv数据，Nautilus通常会附加 '-EXTERNAL'
        "instrument_id": "ETHUSDT-PERP.BINANCE",
        "bar_type": "ETHUSDT-PERP.BINANCE-4-HOUR-LAST-EXTERNAL",
        # 核心参数
        "lookback_period": 4,  # N=4, 4个4H周期
        "k1": 0.5,
        "k2": 0.5,
        # 交易量: 0.02 ETH (约为60-70u，适合50u挑战的激进仓位或配合杠杆)
        "qty_percent": Decimal("0.5"),
        # "trade_size": 1,
        "leverage": 3,
        "stop_loss_pct": 0.015,
        "use_trailing_stop": False,
        "trailing_stop_pct": 0.02,
    },
)

# 5. 回测环境配置
BACKTEST_SETTINGS = BacktestConfig(
    start_date="2024-01-01",
    end_date="2024-08-01",
    initial_balance=[Money("10000", USDT)],
)

# 6. 日志配置
LOGGING_SETTINGS = LogConfig(
    log_level="DEBUG",
    log_level_file="DEBUG",
    log_colors=True,
    use_pyo3=True,
    log_component_levels={
        "Portfolio": "INFO",
        "BacktestEngine": "INFO",
        "MtfTrendPullbackStrategy": "DEBUG",
        "DualThrust": "DEBUG",
    },
    log_components_only=True,
)

# ==========================================
# 激活配置
# ==========================================

# 这里定义当前生效的配置
current_config = GlobalConfig(
    instrument=DOGE_USDT_OKX,
    data=DATA_5M,  # 主数据源 (交易层 5m)
    aux_data=DATA_1H,  # 辅助数据源 (趋势层 1h)
    # TODO: data autofetch
    # inst: from Instrument config
    # dataframe and else: from data and aux_data, better no to use two or multiple data vars, yet indicate 'aux_data' inside of the 'data'
    strategy=MTF_TREND_STRATEGY,  # 使用 MTF 策略
    backtest=BACKTEST_SETTINGS,
    logging=LOGGING_SETTINGS,
    ml=ML_SETTINGS,
)
