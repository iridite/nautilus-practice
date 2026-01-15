import gc
from datetime import datetime
from pathlib import Path

from nautilus_trader.backtest.config import (
    BacktestDataConfig,
    BacktestRunConfig,
    BacktestVenueConfig,
    ImportableFeeModelConfig,
)
from nautilus_trader.backtest.node import (
    BacktestEngineConfig,
    BacktestNode,
)
from nautilus_trader.backtest.results import BacktestResult
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.config import ImportableStrategyConfig, RiskEngineConfig
from nautilus_trader.model.data import BarType

from config.definitions import BackTestConfig
from utils.data_loader import loader
from utils.instrument_loader import load_instrument


def run_high_level(cfg: BackTestConfig, base_dir: Path):
    print(f"🚀 Starting High-Level Backtest with config: {cfg.strategy.name}")

    data_path = base_dir / "data"

    # 1. Setup Instrument
    # Try to load from data/instruments/{VENUE}/{SYMBOL}.json
    # This file should have been fetched by main.py -> fetch_instrument.py
    instrument_file = (
        data_path
        / "instrument"
        / cfg.instrument.venue_name
        / f"{cfg.instrument.instrument_id.split('.')[0]}.json"
    )

    if instrument_file.exists():
        print(f"📂 Loading instrument from {instrument_file}")

        instrument = load_instrument(
            instrument_file
        )  # Determine fees (industry standard defaults for OKX if not provided)
        print(
            f"✅ Fees Loaded: Maker={float(instrument.maker_fee) * 100:.4f}%, Taker={float(instrument.taker_fee) * 100:.4f}%"
        )
    else:
        raise FileNotFoundError(
            f"❌ Instrument definition not found at: {instrument_file}\n"
            f"👉 Please run: uv run main.py (to fetch instruments)"
        )

    # 2. Load Data Feeds (Generic Supply Framework)
    run_timestamp = datetime.now().isoformat()
    data_configs = []
    feed_bar_types = {}  # label -> bar_type_str

    for i, feed in enumerate(cfg.data_feeds):
        # Determine instrument for this feed (support multi-instrument backtest in future)
        feed_inst = instrument
        if feed.instrument_id and feed.instrument_id != str(instrument.id):
            # TODO: Add logic to load auxiliary instrument if needed (e.g. for benchmark)
            pass

        feed_bar_type_str = f"{feed_inst.id}-{feed.bar_type_str}"
        feed_bar_type_def = BarType.from_str(feed_bar_type_str)
        feed_bar_types[feed.label] = feed_bar_type_str

        print(f"📥 Loading Data Feed [{feed.label}]: {feed_bar_type_str}")

        csv_path = data_path / "raw" / feed.csv_file_name
        if not csv_path.exists():
            raise FileNotFoundError(f"Data file not found: {csv_path}")

        # Load and wrangle to parquet catalog
        _, catalog_path = loader(
            csv_path=csv_path,
            output_path=data_path / "parquet" / f"{run_timestamp}_{feed.label}_{i}",
            instrument=feed_inst,
            bar_type=feed_bar_type_def,
        )

        data_configs.append(
            BacktestDataConfig(
                catalog_path=str(catalog_path),
                data_cls="nautilus_trader.model.data:Bar",
                instrument_id=feed_inst.id,
                start_time=cfg.start_date,
                end_time=cfg.end_date,
            )
        )

    gc.collect()

    # 3. Configure Venue
    venue_configs = [
        BacktestVenueConfig(
            name=cfg.instrument.venue_name,
            oms_type="HEDGING",
            account_type="MARGIN",
            base_currency="USDT",
            starting_balances=cfg.initial_balances,
            fee_model=ImportableFeeModelConfig(
                fee_model_path="nautilus_trader.backtest.models:MakerTakerFeeModel",
                config_path="nautilus_trader.backtest.config:MakerTakerFeeModelConfig",
                config={},
            ),
            trade_execution=True,
        ),
    ]

    # 4. Configure Strategy
    # Merge strategy params with system params
    strategy_params = cfg.strategy.params.copy()
    strategy_params["instrument_id"] = instrument.id
    strategy_params["leverage"] = cfg.instrument.leverage

    # Inject bar types from feeds based on labels
    if "main" in feed_bar_types:
        strategy_params["bar_type"] = feed_bar_types["main"]
        strategy_params["trade_bar_type"] = feed_bar_types["main"]

    if "trend" in feed_bar_types:
        strategy_params["trend_bar_type"] = feed_bar_types["trend"]

    # Generic injection for other labels (e.g. benchmark -> benchmark_bar_type)
    for label, bt_str in feed_bar_types.items():
        if label not in ["main", "trend"]:
            strategy_params[f"{label}_bar_type"] = bt_str

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
    if cfg.logging:
        logging_config = LoggingConfig(
            log_level=cfg.logging.log_level,
            log_level_file=cfg.logging.log_level_file,
            log_colors=cfg.logging.log_colors,
            use_pyo3=cfg.logging.use_pyo3,
            log_component_levels=cfg.logging.log_component_levels,
            log_components_only=bool(cfg.logging.log_components_only),
            log_directory=str(base_dir / "log" / "backtest" / "low_level"),
        )
    else:
        logging_config = None

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
        raise_exception=True,
    )

    # 8. Execute
    node = BacktestNode(configs=[run_config])
    print("⏳ Running BacktestNode...")
    results = node.run()
    print("✅ Backtest Complete.")

    if results:
        _print_results(results[0])
    else:
        print(f"❌ No results generated: {results}")


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
            # 核心指标优先展示
            core_metrics = ["PnL (total)", "PnL% (total)", "Commissions", "Fees"]
            for k in core_metrics:
                if k in metrics and metrics[k] == metrics[k]:
                    print(f"   * {k:<25}: {metrics[k]:,.4f}")

            print("   " + "-" * 40)
            # 其他指标按字母顺序排列
            for k in sorted(metrics.keys()):
                if k not in core_metrics and metrics[k] == metrics[k]:
                    print(f"   - {k:<25}: {metrics[k]:,.4f}")

    if result.stats_returns:
        print("📈 Returns:")
        for k, v in result.stats_returns.items():
            if v == v:
                print(f"   - {k:<25}: {v:.4f}")
    print("=" * 65 + "\n")
