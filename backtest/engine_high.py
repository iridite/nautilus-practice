import gc
from datetime import datetime
from pathlib import Path

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
from nautilus_trader.config import ImportableStrategyConfig, RiskEngineConfig
from nautilus_trader.model.data import Bar, BarType

from config.definitions import GlobalConfig
from utils.data_loader import loader
from utils.instrument_loader import load_instrument


def run_high_level(cfg: GlobalConfig, base_dir: Path):
    print(f"🚀 Starting High-Level Backtest with config: {cfg.strategy.name}")

    data_path = base_dir / "data"

    # 1. Setup Instrument
    # Try to load from data/instruments/{VENUE}/{SYMBOL}.json
    # This file should have been fetched by main.py -> fetch_instrument.py
    instrument_file = (
        data_path
        / "instrument"
        / cfg.instrument.venue
        / f"{cfg.instrument.instrument_id.split('.')[0]}.json"
    )

    if instrument_file.exists():
        print(f"📂 Loading instrument from {instrument_file}")
        instrument = load_instrument(instrument_file)
    else:
        raise FileNotFoundError(
            f"❌ Instrument definition not found at: {instrument_file}\n"
            f"👉 Please run: uv run main.py (to fetch instruments)"
        )

    # 2. Define BarType
    bar_type_str = f"{instrument.id}-{cfg.data.bar_type_str}"
    bar_type_def = BarType.from_str(bar_type_str)
    print(f"📊 Bar Type: {bar_type_str}")

    # 3. Load Data
    run_timestamp = datetime.now().isoformat()
    catalog_paths = []

    # 3.1 Load Main Data
    csv_path = data_path / "raw" / cfg.data.csv_file_name
    if not csv_path.exists():
        raise FileNotFoundError(f"Data file not found: {csv_path}")

    parquet_catalog, catalog_path = loader(
        csv_path=csv_path,
        output_path=data_path / "parquet" / f"{run_timestamp}_main",
        instrument=instrument,
        bar_type=bar_type_def,
    )
    catalog_paths.append(str(catalog_path))
    del parquet_catalog

    # 3.2 Load Aux Data (if any)
    if cfg.aux_data:
        aux_bar_type_str = f"{instrument.id}-{cfg.aux_data.bar_type_str}"
        aux_bar_type_def = BarType.from_str(aux_bar_type_str)
        print(f"📊 Aux Bar Type: {aux_bar_type_str}")

        aux_csv_path = data_path / "raw" / cfg.aux_data.csv_file_name
        if not aux_csv_path.exists():
            raise FileNotFoundError(f"Aux Data file not found: {aux_csv_path}")

        aux_catalog, aux_catalog_path = loader(
            csv_path=aux_csv_path,
            output_path=data_path / "parquet" / f"{run_timestamp}_aux",
            instrument=instrument,
            bar_type=aux_bar_type_def,
        )
        catalog_paths.append(str(aux_catalog_path))
        del aux_catalog

    gc.collect()

    # 4. Configure Venue
    venue_configs = [
        BacktestVenueConfig(
            name=cfg.instrument.venue,
            oms_type="HEDGING",
            account_type="MARGIN",
            base_currency="USDT",
            starting_balances=cfg.backtest.initial_balance,
        ),
    ]

    # 5. Configure Data
    data_configs = [
        BacktestDataConfig(
            catalog_path=path,
            data_cls=Bar,
            instrument_id=instrument.id,
            start_time=cfg.backtest.start_date,
            end_time=cfg.backtest.end_date,
        )
        for path in catalog_paths
    ]

    # 6. Configure Strategy
    # Merge strategy params with system params (instrument_id, bar_type)
    strategy_params = cfg.strategy.params.copy()
    strategy_params["instrument_id"] = instrument.id
    strategy_params["bar_type"] = bar_type_str

    # Auto-inject MTF params if aux data is present
    if cfg.aux_data:
        strategy_params["trade_bar_type"] = bar_type_str
        strategy_params["trend_bar_type"] = (
            f"{instrument.id}-{cfg.aux_data.bar_type_str}"
        )

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
    logging_config = LoggingConfig(
        log_level=cfg.logging.log_level,
        log_level_file=cfg.logging.log_level_file,
        log_colors=cfg.logging.log_colors,
        use_pyo3=cfg.logging.use_pyo3,
        log_component_levels=cfg.logging.log_component_levels,
        log_components_only=bool(cfg.logging.log_components_only),
        log_directory=str(base_dir / "log" / "backtest" / "high_level"),
    )

    eng_cfg = BacktestEngineConfig(
        strategies=strategies,
        logging=logging_config,
        risk_engine=RiskEngineConfig(
            bypass=False,  # 彻底关闭风控检查
        ),
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
    node.run()
    print("✅ Backtest Complete.")

    # if results:
    #     _print_results(results[0])
    # else:
    #     print("❌ No results generated.")


def _print_results(result: BacktestResult):
    print("\n" + "=" * 65)
    print("🏆 Backtest Report")
    print("=" * 65)
    print(f"⏱️ \tDuration:       {result.elapsed_time:.4f}s")
    print(f"📝 \tOrders:         {result.total_orders}")
    print(f"📍 \tPositions:      {result.total_positions}")

    if result.stats_pnls:
        for currency, metrics in result.stats_pnls.items():
            print(f"💰 PnL ({currency}):")
            for k, v in metrics.items():
                if v == v:
                    print(f"   - {k:<20}: {v:,.4f}")

    if result.stats_returns:
        print("📈 Returns:")
        for k, v in result.stats_returns.items():
            if v == v:
                print(f"   - {k:<25}: {v:.4f}")
    print("=" * 65 + "\n")
