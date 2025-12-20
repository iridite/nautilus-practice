# %%
from nautilus_trader.backtest.config import BacktestEngineConfig  # Configure backtest engine
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.model import TraderId

config = BacktestEngineConfig(
    trader_id=TraderId("BACKTESTER-001"),
    logging=LoggingConfig(
        log_level="WARNING",
        log_colors=True,
        use_pyo3=False,
    ),
)

engine = BacktestEngine(config)

from nautilus_trader.model.currencies import USDT
from nautilus_trader.model import Money
from nautilus_trader.model.enums import OmsType, BookType, AccountType
from nautilus_trader.adapters.binance import BINANCE_VENUE

# from nautilus_trader.adapters.okx import OKX_VENUE

engine.add_venue(
        venue=BINANCE_VENUE,
        oms_type=OmsType.NETTING,
        book_type=BookType.L1_MBP,
        account_type=AccountType.MARGIN,  # Spot MARGIN account (not for perpetuals or futures)
    base_currency=USDT,  # Multi-currency account
    starting_balances=[Money(1_000_000.0, USDT)],
        trade_execution=True,  # Only use with L1_MBP book type or throttled book data
)
# %% [markdown]
# 
# %%
# Instruments now

from nautilus_trader.test_kit.providers import TestInstrumentProvider

# inst = InstrumentProvider.
inst = TestInstrumentProvider.ethusdt_perp_binance()
print(inst.id)

engine.add_instrument(inst)

# %% [markdown]
# 这一块不清楚这个 Test 到底是不是一种专供测试的，甚至算不上是回测等级的 playground 产物
# %%
import pandas as pd
from nautilus_trader.model import BarType
from nautilus_trader.persistence.wranglers import BarDataWrangler

# Data part
wrangler = BarDataWrangler(BarType.from_str("ETHUSDT-PERP.BINANCE-5-MINUTE-LAST-EXTERNAL"), inst)

df = pd.read_csv("../data/binance-ETHUSDT-5m-2025-01-01_2025-12-20.csv")
df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
df["timestamp"] = df["timestamp"] + pd.Timedelta(minutes=5)
df.set_index("timestamp", inplace=True)

df = df[["open", "high", "low", "close", "volume"]]

print("处理后的数据预览：")
print(df.head())

bar = wrangler.process(df)

engine.add_data(bar)
print(engine.trader.generate_account_report(BINANCE_VENUE))
# %% [markdown]
# # Backtesting Part
# %%
from nautilus_trader.examples.algorithms.twap import TWAPExecAlgorithm
from decimal import Decimal
from nautilus_trader.examples.strategies.ema_cross_twap import EMACrossTWAP, EMACrossTWAPConfig

# Configure your strategy
strategy_config = EMACrossTWAPConfig(
    instrument_id=inst.id,
    bar_type=BarType.from_str("ETHUSDT-PERP.BINANCE-5-MINUTE-LAST-EXTERNAL"),
        trade_size=Decimal("0.10"),
        fast_ema_period=10,
        slow_ema_period=20,
        twap_horizon_secs=10.0,
        twap_interval_secs=2.5,
)
# %%

# Instantiate and add your strategy
strategy = EMACrossTWAP(config=strategy_config)
engine.add_strategy(strategy)

# Instantiate and add your execution algorithm
exec_algorithm = TWAPExecAlgorithm()
engine.add_exec_algorithm(exec_algorithm)

# Run the engine (from start to end of data)
engine.run()

# Optionally view reports
with pd.option_context(
        "display.max_rows",
        10,
        "display.max_columns",
        None,
        "display.width",
        300,
):
    print(engine.trader.generate_account_report(BINANCE_VENUE))
    print(engine.trader.generate_order_fills_report())
    print(engine.trader.generate_positions_report())
# %%

# Generate interactive tearsheet (requires: pip install plotly>=6.3.1)
try:
        from nautilus_trader.analysis import TearsheetConfig
        from nautilus_trader.analysis.tearsheet import create_tearsheet

        print("\nGenerating tearsheet...")

        # Try different themes: "plotly_white", "plotly_dark", "nautilus", "nautilus_dark"
        tearsheet_config = TearsheetConfig(theme="plotly_white")  # Change this to test themes!

        create_tearsheet(
            engine=engine,
            output_path="crypto_ethusdt_tearsheet.html",
            config=tearsheet_config,
        )
        print("Tearsheet saved to: crypto_ethusdt_tearsheet.html")
        print(f"Theme: {tearsheet_config.theme}")
        print("Open this file in your browser to view interactive charts!")
except ImportError:
        print("\nPlotly not installed. Install with: pip install plotly>=6.3.1")
        print("  Then re-run to generate tearsheets.")

# For repeated backtest runs make sure to reset the engine
engine.reset()

# Good practice to dispose of the object
engine.dispose()
