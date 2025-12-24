import shutil
from decimal import Decimal
from pathlib import Path
from nautilus_trader.adapters.databento.data_utils import DATA_PATH
from nautilus_trader.model.currencies import DASH
from nautilus_trader.persistence.catalog import ParquetDataCatalog
import pandas as pd

from nautilus_trader.backtest.node import BacktestDataConfig # pyright: ignore[reportPrivateImportUsage]
from nautilus_trader.backtest.node import BacktestEngineConfig
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.backtest.node import BacktestRunConfig # pyright: ignore[reportPrivateImportUsage]
from nautilus_trader.backtest.node import BacktestVenueConfig # pyright: ignore[reportPrivateImportUsage]
from nautilus_trader.config import ImportableStrategyConfig
from nautilus_trader.core.datetime import dt_to_unix_nanos
from nautilus_trader.model import QuoteTick
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.model import BarType
from utils.data_loader import loader

# path setup
BASE_DIR: Path = Path(__file__).resolve().parent
DATA_PATH: Path = BASE_DIR.parent / "data" 

instrument = TestInstrumentProvider.ethusdt_perp_binance

parquet: ParquetDataCatalog = loader(
    csv_path = DATA_PATH / "raw" / "binance-ETHUSDT-5m-2025-01-01_2025-12-20",
    output_dir= DATA_PATH / "parquet",
    instrument=instrument,
    bar_type=BarType("ETH/USD.BINANCE-SPOT-5-MINUTE-LAST-INTERNAL"),
)

venue_configs: list[BacktestVenueConfig] = [
    BacktestVenueConfig(
        name="SIM",
        oms_type="HEDGING",
        account_type="MARGIN",
        base_currency="USD",
        starting_balances=["1_000_000 USD"],
    ),
]

data_configs: list[BacktestDataConfig] = [
    BacktestDataConfig(
        catalog_path=str(object=DATA_PATH / "parquet"),
        data_cls=QuoteTick,
        instrument_id=instrument.id,
        start_time="2025-01-01", # Can be an ISO 8601 format datetime string, or UNIX nanoseconds integer
        end_time="2025-12-10",
    ),
]

strategies = [
    ImportableStrategyConfig(
        strategy_path="nautilus_trader.examples.strategies.ema_cross:EMACross",
        config_path="nautilus_trader.examples.strategies.ema_cross:EMACrossConfig",
        config={
            "instrument_id": instrument.id,
            "bar_type": "EUR/USD.SIM-15-MINUTE-BID-INTERNAL",
            "fast_ema_period": 10,
            "slow_ema_period": 20,
            "trade_size": Decimal(1_000_000),
        },
    ),
]

config = BacktestRunConfig(
    engine=BacktestEngineConfig(strategies=strategies),
    data=data_configs,
    venues=venue_configs,
)

node = BacktestNode(configs=[config])

results = node.run()