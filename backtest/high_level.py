import shutil
from decimal import Decimal
from pathlib import Path
import pandas as pd
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
# ⚠️ 注意这里改成了 Bar

# Path setup
BASE_DIR: Path = Path(__file__).resolve().parent
DATA_PATH: Path = BASE_DIR.parent / "data" 

# 1. 定义 Instrument
instrument = TestInstrumentProvider.ethusdt_perp_binance()

# 2. 定义 BarType (确保 Strategy 和 Loader 使用完全相同的定义)
# 该部分依照 k 线来源进行分类，如果不是基于 tick 或者 quote 生成的 k 线，建议使用 EXTERNAL
bar_type_str = f"{instrument.id}-5-MINUTE-LAST-EXTERNAL"
bar_type_def = BarType.from_str(bar_type_str)

# 3. 加载数据 (执行转换)
parquet_catalog, catalog_path = loader(
    csv_path = DATA_PATH / "raw" / "binance-ETHUSDT-5m-2025-01-01_2025-12-24.csv",
    output_dir= DATA_PATH / "parquet",
    instrument=instrument,
    bar_type=bar_type_def,
)

# 调试：打印一下确认数据真的进去了
print(f"Data Catalog Path: {catalog_path}")
print(f"Instruments in Catalog: {parquet_catalog.instruments()}")

# 4. 配置 Venue (交易所)
venue_configs: list[BacktestVenueConfig] = [
    BacktestVenueConfig(
        name="BINANCE",
        oms_type="HEDGING",
        account_type="MARGIN",
        base_currency="USDT",
        # 🔧 修正 1: 增加本金，防止资金不足
        starting_balances=["1_000 USDT"], 
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
        end_time="2025-01-20",
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
            "trade_size": Decimal("10")
        },
    ),
]

# 7. 运行配置
config = BacktestRunConfig(
    engine=BacktestEngineConfig(strategies=strategies),
    data=data_configs,
    venues=venue_configs,
)

# 8. 执行
node = BacktestNode(configs=[config])
print("开始回测...")
results: list[BacktestResult] = node.run()

# 9. 简单打印结果
print("回测结束")
print(f"Total Orders: {results[0].total_orders}")