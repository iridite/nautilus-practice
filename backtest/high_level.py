import shutil
from decimal import Decimal
from pathlib import Path
import pandas as pd

from nautilus_trader.backtest.node import BacktestDataConfig # pyright: ignore[reportPrivateImportUsage]
from nautilus_trader.backtest.node import BacktestEngineConfig
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.backtest.node import BacktestRunConfig # pyright: ignore[reportPrivateImportUsage]
from nautilus_trader.backtest.node import BacktestVenueConfig # pyright: ignore[reportPrivateImportUsage]
from nautilus_trader.config import ImportableStrategyConfig
from nautilus_trader.core.datetime import dt_to_unix_nanos
from nautilus_trader.model import QuoteTick
# from nautilus_trader.persistence.catalog import ParquetDataCatalog
# from nautilus_trader.persistence.wranglers import QuoteTickDataWrangler
# from nautilus_trader.test_kit.providers import CSVTickDataLoader
# from nautilus_trader.test_kit.providers import TestInstrumentProvider

venue_configs = [
    BacktestVenueConfig(
        name="SIM",
        oms_type="HEDGING",
        account_type="MARGIN",
        base_currency="USD",
        starting_balances=["1_000_000 USD"],
    ),
]

data_configs = [
    BacktestDataConfig(
        catalog_path=str(CATALOG_PATH),
        data_cls=QuoteTick,
        instrument_id=instrument.id,
        start_time=start_time,
        end_time=end_time,
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