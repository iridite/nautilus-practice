from decimal import Decimal
from math import log
from pathlib import Path
import pandas as pd
import sys

from nautilus_trader.adapters.binance import BINANCE_VENUE
from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.model import TraderId, Money
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import OmsType, BookType, AccountType
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.model import BarType
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.examples.algorithms.twap import TWAPExecAlgorithm
from nautilus_trader.examples.strategies.ema_cross_twap import EMACrossTWAP, EMACrossTWAPConfig
# from nautilus_trader.analysis import TearsheetConfig
from nautilus_trader.analysis.tearsheet import create_tearsheet
# Import local modules
from datetime import datetime

BASE_DIR: Path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Configure backtest engine
config = BacktestEngineConfig(
    trader_id=TraderId("BACKTESTER-001"),
    logging=LoggingConfig(
        log_level="WARNING",
        log_level_file="DEBUG",
        log_file_format="json",
        log_colors=True,
        use_pyo3=True,
        log_directory=str(BASE_DIR / "log" / "backtest" / "low_level")
    ),
)

# Instantiate engine
engine = BacktestEngine(config)

# Configure Venue and OMS
engine.add_venue(
    venue=BINANCE_VENUE,
    oms_type=OmsType.NETTING,
    book_type=BookType.L1_MBP,
    account_type=AccountType.MARGIN,
    base_currency=USDT,
    starting_balances=[Money(1_000.0, USDT)],
    trade_execution=True,
)

# Load instrument
inst = TestInstrumentProvider.ethusdt_perp_binance()
print(f"Loaded instrument: {inst.id}")

engine.add_instrument(inst)

# Data loading and wrangling
bar_type = BarType.from_str(f"{inst.id}-5-MINUTE-LAST-EXTERNAL")
wrangler = BarDataWrangler(bar_type, inst)

try:
    df = pd.read_csv(BASE_DIR / "data" / "raw" / "binance-ETHUSDT-30m-2025-01-01_2025-12-25.csv")
    
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    # Adjust timestamp to close time
    df["timestamp"] = df["timestamp"] + pd.Timedelta(minutes=5)
    
    df.set_index("timestamp", inplace=True)
    df = df[["open", "high", "low", "close", "volume"]]

    print("Data preview:")
    print(df.head())

    bars = wrangler.process(df)
    engine.add_data(bars)
    
    print(f"\nLoaded {len(bars)} bars")

except FileNotFoundError:
    print("Error: Data file not found.")
    bars = []

# Strategy and Execution Algorithm configuration
strategy_config = EMACrossTWAPConfig(
    instrument_id=inst.id,
    bar_type=bar_type,
    trade_size=Decimal("2"), 
    fast_ema_period=10,
    slow_ema_period=20,
    twap_horizon_secs=10.0,
    twap_interval_secs=2.5,
)

strategy = EMACrossTWAP(config=strategy_config)
engine.add_strategy(strategy)

exec_algorithm = TWAPExecAlgorithm()
engine.add_exec_algorithm(exec_algorithm)

# Run engine
print("\nRunning backtest...")
engine.run()
print("Backtest finished.")

# Visualization
output_path = str(BASE_DIR / "output" / f"{inst.id}_{datetime.now().isoformat()}.html")

create_tearsheet(
    engine=engine,
    output_path=output_path, # 显式指定文件名
    # currency
)

# Cleanup
engine.reset()
engine.dispose()
print("Engine resources released.")