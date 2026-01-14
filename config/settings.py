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
# 用户配置区域 (User Configuration)
# ==========================================

# 1. 标的配置 (Instrument Configuration)
# 关于杠杆 (leverage) 的说明：
# 1. 来源优先级：策略推荐杠杆 (Strategy Recommend) > 策略配置 (StrategyConfig.params) > 标的配置 (InstrumentConfig)。
#    - 优先级 1 (最高): 策略代码动态推荐的杠杆数。
#    - 优先级 2: 如果策略未推荐，则采用 `StrategyConfig` 的 `params` 中设置的 `leverage`。
#    - 优先级 3 (最低): 如果以上均未设置，则采用下方 `InstrumentConfig` 中设定的默认 `leverage`。
# 2. 自动上限保护：程序会结合交易所返回的 `instrument` 数据，确保最终开仓杠杆不超过交易所允许的最大上限。
# 3. 手续费配置 (Fees)：
#    - 可选配置 maker_fee 和 taker_fee (例如 0.0002 代表 0.02%)。
#    - 如果不配置且 venue 为 OKX，系统引擎将自动应用行业标准费率 (Maker 0.02%, Taker 0.05%)。

ETH_USDT_BINANCE_SWAP = InstrumentConfig(
    venue="BINANCE",
    quote_currency="ETH",
    base_currency="USDT",
    type=InstrumentType.SWAP,
    leverage=3,
    maker_fee=0.0002,
    taker_fee=0.0005,
)

ETH_USDT_OKX_SWAP = InstrumentConfig(
    venue="OKX",  # Note: OKX ETH-USDT-SWAP usually has a 0.1x multiplier defined in instrument file
    quote_currency="ETH",
    base_currency="USDT",
    type=InstrumentType.SWAP,
    leverage=3,
    maker_fee=0.0002,
    taker_fee=0.0005,
)

DOGE_USDT_OKX_SWAP = InstrumentConfig(
    venue="OKX",
    quote_currency="DOGE",
    base_currency="USDT",
    type=InstrumentType.SWAP,
    leverage=1,
    maker_fee=0.0002,
    taker_fee=0.0005,
)

# 2. 数据配置 (Data Configuration)
# 请确保文件名与 data/raw 下的一致。Nautilus 会在加载外部 CSV 时自动附加 '-EXTERNAL' 后缀。

DATA_4H = DataConfig(
    csv_file_name="okx-ETHUSDT-4h-2020-01-01_2026-01-13.csv",
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

# 3. ML 配置 (AI Filter/Feature Settings)
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

# 4. 策略配置 (Strategy Configuration)

# MTF_TREND (Multi-Timeframe Trend Strategy)
MTF_TREND_STRATEGY = StrategyConfig(
    name="MtfTrendPullbackStrategy",  # 必须与策略类名一致
    module_path="strategy.mtf_trend_pullback",
    config_class="MtfTrendPullbackConfig",
    params={
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
        "stop_loss_pct": 0.015,  # 1.5%
        "leverage": 1,
        # AI Filtering
        "use_ai_filter": ML_SETTINGS.use_ai_filter,
        "model_path": ML_SETTINGS.model_path,
        "min_prob_threshold": ML_SETTINGS.min_prob_threshold,
        # Data Recording
        "record_features": ML_SETTINGS.record_features,
        "record_path": ML_SETTINGS.record_path,
    },
)

# DUAL_THRUST (Dual Thrust Breakout Strategy)
DUAL_THRUST_STRATEGY = StrategyConfig(
    name="DualThrust",  # 必须与策略类名一致
    module_path="strategy.dual_thrust",
    config_class="DualThrustConfig",
    params={
        "instrument_id": "ETHUSDT-PERP.BINANCE",
        "bar_type": "ETHUSDT-PERP.BINANCE-4-HOUR-LAST-EXTERNAL",
        # 核心参数 (Core Params)
        "lookback_period": 4,
        "k1": 0.5,
        "k2": 0.5,
        # 下单设置 (Position Sizing)
        # 1. qty_percent: 按账户总权益的比例计算下单量。系统已自动处理合约乘数修正。
        "qty_percent": Decimal("0.2"),
        # 2. trade_size: 固定下单张数。若启用此项请取消注释，它会覆盖 qty_percent。
        # "trade_size": 1,
        "leverage": 5,
        # 风险管理 (Risk Management)
        # stop_loss_pct: 强制止损比例。
        # - 计算方式：入场价格的百分比损失 (即对该笔仓位收益率的监控)。
        # - 禁用方式：设置为 None 或 0。
        "stop_loss_pct": 0.05,  # 5% SL on position entry price
        # 注意: 目前止损单使用 reduce_only=False 以确保回测存单成功。
        "use_trailing_stop": False,
        "trailing_stop_pct": 0.02,
    },
)

# 5. 回测环境配置 (Backtest Environment)
BACKTEST_SETTINGS = BacktestConfig(
    # start_date="2024-01-01",
    # end_date="2024-08-01",
    initial_balance=[Money("100", USDT)],
)

# 6. 日志配置 (Logging Configuration)
LOGGING_SETTINGS = LogConfig(
    log_level="DEBUG",
    log_level_file="DEBUG",
    log_colors=True,
    use_pyo3=True,
    log_component_levels={
        "Portfolio": "INFO",
        "BacktestEngine": "INFO",
        "DualThrust": "DEBUG",
        "MtfTrendPullbackStrategy": "DEBUG",
    },
    log_components_only=True,
)

# ==========================================
# 激活配置 (Active Configuration)
# ==========================================

# 在此处定义当前回测运行所使用的组合
current_config = GlobalConfig(
    instrument=ETH_USDT_OKX_SWAP,  # 使用标的
    data=DATA_4H,  # 主数据源
    aux_data=None,  # 辅助数据源 (Dual Thrust 不需要，MTF 需要 DATA_1H)
    strategy=DUAL_THRUST_STRATEGY,  # 运行策略
    backtest=BACKTEST_SETTINGS,
    logging=LOGGING_SETTINGS,
    ml=ML_SETTINGS,
)
