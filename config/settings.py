from decimal import Decimal
from nautilus_trader.model.enums import BarAggregation, PriceType
from config.definitions import (
    GlobalConfig, 
    InstrumentConfig, 
    DataConfig, 
    StrategyConfig, 
    BacktestConfig
)

# ==========================================
# 用户配置区域
# ==========================================

# 1. 标的配置
ETH_USDT_BINANCE = InstrumentConfig(
    venue="BINANCE",
    symbol="ETHUSDT",
)

# 2. 数据配置
# 请确保文件名与 data/raw 下的一致
DATA_1H = DataConfig(
    csv_file_name="binance-ETHUSDT-1h-2025-01-01_2025-12-25.csv",
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

# 3. 策略配置
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

# MACD 策略 (示例)
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

# 4. 回测环境配置
BACKTEST_SETTINGS = BacktestConfig(
    start_date="2025-01-01",
    end_date="2025-12-20",
    initial_balance="100000 USDT"
)

# ==========================================
# 激活配置
# ==========================================

# 这里定义当前生效的配置
# 你可以创建多个 Config 对象，然后在 main.py 中选择，或者直接修改这里
current_config = GlobalConfig(
    instrument=ETH_USDT_BINANCE,
    data=DATA_30M, # 切换数据源
    strategy=BMR_STRATEGY, # 切换策略
    backtest=BACKTEST_SETTINGS
)
