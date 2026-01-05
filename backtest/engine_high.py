import sys
import gc
from pathlib import Path
from decimal import Decimal
from datetime import datetime

from nautilus_trader.backtest.config import (
    BacktestDataConfig,
    BacktestRunConfig,
    BacktestVenueConfig,
)
from nautilus_trader.backtest.node import (
    BacktestEngineConfig,
    BacktestNode,
)
from nautilus_trader.backtest.results import BacktestResult
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.config import ImportableStrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.test_kit.providers import TestInstrumentProvider

from config.definitions import GlobalConfig
from utils.data_loader import loader

def run_high_level(cfg: GlobalConfig, base_dir: Path):
    print(f"🚀 Starting High-Level Backtest with config: {cfg.strategy.name}")
    
    data_path = base_dir / "data"
    
    # 1. Setup Instrument (Currently using TestInstrumentProvider for simplicity, 
    # in a real scenario you might construct this from cfg.instrument)
    # For now, we map the config symbol to the test provider if possible, or create a custom one.
    # To keep it simple and working with existing code, we'll use the provider but check consistency.
    if cfg.instrument.symbol == "ETHUSDT" and cfg.instrument.venue == "BINANCE":
        instrument = TestInstrumentProvider.ethusdt_perp_binance()
    else:
        # Fallback or TODO: Create instrument from config properties
        print(f"⚠️ Warning: Using default ETHUSDT instrument for {cfg.instrument.symbol}")
        instrument = TestInstrumentProvider.ethusdt_perp_binance()

    # 2. Define BarType
    bar_type_str = f"{instrument.id}-{cfg.data.bar_type_str}"
    bar_type_def = BarType.from_str(bar_type_str)
    print(f"📊 Bar Type: {bar_type_str}")

    # 3. Load Data
    csv_path = data_path / "raw" / cfg.data.csv_file_name
    if not csv_path.exists():
        raise FileNotFoundError(f"Data file not found: {csv_path}")

    parquet_catalog, catalog_path = loader(
        csv_path=csv_path,
        output_path=data_path / "parquet" / f"{datetime.now().isoformat()}",
        instrument=instrument,
        bar_type=bar_type_def,
    )
    del parquet_catalog
    gc.collect()

    # 4. Configure Venue
    venue_configs = [
        BacktestVenueConfig(
            name=cfg.instrument.venue,
            oms_type="HEDGING",
            account_type="MARGIN",
            base_currency="USDT",
            starting_balances=[cfg.backtest.initial_balance],
        ),
    ]

    # 5. Configure Data
    data_configs = [
        BacktestDataConfig(
            catalog_path=str(catalog_path),
            data_cls=Bar,
            instrument_id=instrument.id,
            start_time=cfg.backtest.start_date,
            end_time=cfg.backtest.end_date,
        ),
    ]

    # 6. Configure Strategy
    # Merge strategy params with system params (instrument_id, bar_type)
    strategy_params = cfg.strategy.params.copy()
    strategy_params["instrument_id"] = instrument.id
    strategy_params["bar_type"] = bar_type_str
    
    # Convert Decimal strings to Decimal objects if needed (Nautilus config usually handles this, 
    # but ImportableStrategyConfig passes dict)
    # Note: ImportableStrategyConfig expects a dict.
    
    strategies = [
        ImportableStrategyConfig(
            strategy_path=f"{cfg.strategy.module_path}:{cfg.strategy.name}",
            config_path=f"{cfg.strategy.module_path}:{cfg.strategy.config_class}",
            config=strategy_params,
        ),
    ]

    # 7. Configure Logging
    log_dir = base_dir / "log" / "backtest" / "high_level"
    logging_config = LoggingConfig(
        log_level=cfg.logging.log_level,
        log_level_file=cfg.logging.log_level_file,
        log_colors=cfg.logging.log_colors,
        use_pyo3=cfg.logging.use_pyo3,
        log_directory=str(log_dir),
    )
    cfg.logging.log_directory = str(log_dir)

    eng_cfg = BacktestEngineConfig(
        strategies=strategies,
        logging=logging_config,
    )

    # 7. Run Config
    run_config = BacktestRunConfig(
        engine=eng_cfg,
        data=data_configs,
        venues=venue_configs,
    )

    # 8. Execute
    node = BacktestNode(configs=[run_config])
    print("⏳ Running BacktestNode...")
    results = node.run()
    print("✅ Backtest Complete.")

    if results:
        _print_results(results[0])
    else:
        print("❌ No results generated.")

def _print_results(result: BacktestResult):
    print("\n" + "=" * 65)
    print("🏆 Backtest Report")
    print("=" * 65)
    print(f"⏱️ Duration:       {result.elapsed_time:.4f}s")
    print(f"📝 Orders:         {result.total_orders}")
    print(f"📍 Positions:      {result.total_positions}")
    
    if result.stats_pnls:
        for currency, metrics in result.stats_pnls.items():
            print(f"💰 PnL ({currency}):")
            for k, v in metrics.items():
                if v == v: print(f"   - {k:<20}: {v:,.4f}")
    
    if result.stats_returns:
        print("📈 Returns:")
        for k, v in result.stats_returns.items():
            if v == v: print(f"   - {k:<25}: {v:.4f}")
    print("=" * 65 + "\n")
