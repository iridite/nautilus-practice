import gc
import json
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
from nautilus_trader.model.enums import BarAggregation

from config.definitions import BackTestConfig, DataConfig
from utils.data_loader import loader
from utils.instrument_loader import load_instrument


def _resolve_instrument_path(base_dir: Path, venue_name: str, symbol: str) -> Path:
    """解析 instrument json 文件的路径"""
    clean_symbol = symbol.replace(":", "-").replace("USDT-USDT", "USDT")
    potential_names = [
        f"{clean_symbol}.json",
        f"{clean_symbol.replace('USDT', '-USDT-SWAP')}.json",
        f"{clean_symbol.replace('USDT', '-USDT')}.json",
    ]
    for name in potential_names:
        path = base_dir / "data" / "instrument" / venue_name / name
        if path.exists():
            return path
    return base_dir / "data" / "instrument" / venue_name / f"{clean_symbol}.json"


def run_high_level(cfg: BackTestConfig, base_dir: Path):
    print(f"🚀 Starting High-Level Backtest with config: {cfg.strategy.name}")

    data_path = base_dir / "data"

    # 1. Resolve Universe
    universe_symbols = set()
    params = cfg.strategy.params
    u_name = (
        params.get("universe_filename")
        if isinstance(params, dict)
        else getattr(params, "universe_filename", None)
    )

    if u_name:
        universe_file = data_path / u_name
        if universe_file.exists():
            with open(universe_file, "r") as f:
                u_data = json.load(f)
                for month_list in u_data.values():
                    universe_symbols.update(month_list)
            print(f"🌌 Universe loaded: {len(universe_symbols)} symbols found.")

    # 2. Data and Strategy Preparation
    run_timestamp = datetime.now().isoformat()
    data_configs = []
    strategies = []
    loaded_instruments = {}

    if universe_symbols:
        # === Case A: Universe-based Multi-Instrument Strategy ===
        print(
            f"🌌 Running in Universe Mode with {len(universe_symbols)} potential symbols."
        )

        # 2.1 Load Benchmark (if any)
        benchmark_inst = None
        benchmark_bar_type = None
        for feed in cfg.data_feeds:
            if feed.label == "benchmark" and feed.instrument_id:
                symbol_part = feed.instrument_id.split(".")[0]
                venue_part = (
                    feed.instrument_id.split(".")[1]
                    if "." in feed.instrument_id
                    else cfg.instrument.venue_name
                )
                path = _resolve_instrument_path(base_dir, venue_part, symbol_part)
                if path.exists():
                    benchmark_inst = load_instrument(path)
                    loaded_instruments[str(benchmark_inst.id)] = benchmark_inst

                    feed_bar_type_str = f"{benchmark_inst.id}-{feed.bar_type_str}"
                    benchmark_bar_type = feed_bar_type_str

                    csv_path = data_path / "raw" / feed.csv_file_name
                    if csv_path.exists():
                        _, catalog_path = loader(
                            csv_path=csv_path,
                            output_path=data_path
                            / "parquet"
                            / f"{run_timestamp}_benchmark",
                            instrument=benchmark_inst,
                            bar_type=BarType.from_str(feed_bar_type_str),
                        )
                        data_configs.append(
                            BacktestDataConfig(
                                catalog_path=str(catalog_path),
                                data_cls="nautilus_trader.model.data:Bar",
                                instrument_id=benchmark_inst.id,
                                start_time=cfg.start_date,
                                end_time=cfg.end_date,
                            )
                        )

        # 2.2 Load each Universe member
        main_feed_template = next(
            (f for f in cfg.data_feeds if f.label == "main"), None
        )
        if not main_feed_template:
            print("❌ No 'main' data feed found in config to use as template.")
            return

        for i, symbol in enumerate(sorted(list(universe_symbols))):
            raw_pair = symbol.split(":")[0]
            clean_base = raw_pair.replace("USDT", "")
            inst_id_str = f"{clean_base}-USDT-SWAP.{cfg.instrument.venue_name}"

            if inst_id_str in loaded_instruments:
                inst = loaded_instruments[inst_id_str]
            else:
                inst_path = _resolve_instrument_path(
                    base_dir, cfg.instrument.venue_name, inst_id_str.split(".")[0]
                )
                if not inst_path.exists():
                    continue
                try:
                    inst = load_instrument(inst_path)
                    loaded_instruments[str(inst.id)] = inst
                except Exception as e:
                    print(f"⚠️ Failed to load instrument {inst_id_str}: {e}")
                    continue

            # Load Data
            timeframe = f"{main_feed_template.bar_period}{'h' if main_feed_template.bar_aggregation == BarAggregation.HOUR else 'm'}"
            if main_feed_template.bar_aggregation == BarAggregation.DAY:
                timeframe = f"{main_feed_template.bar_period}d"

            csv_file_name = f"{clean_base}USDT/{cfg.instrument.venue_name.lower()}-{clean_base}USDT-{timeframe}-{cfg.start_date}_{cfg.end_date}.csv"
            csv_path = data_path / "raw" / csv_file_name

            if csv_path.exists():
                feed_bar_type_str = f"{inst.id}-{main_feed_template.bar_type_str}"
                _, catalog_path = loader(
                    csv_path=csv_path,
                    output_path=data_path
                    / "parquet"
                    / f"{run_timestamp}_{clean_base}_{i}",
                    instrument=inst,
                    bar_type=BarType.from_str(feed_bar_type_str),
                )
                data_configs.append(
                    BacktestDataConfig(
                        catalog_path=str(catalog_path),
                        data_cls="nautilus_trader.model.data:Bar",
                        instrument_id=inst.id,
                        start_time=cfg.start_date,
                        end_time=cfg.end_date,
                    )
                )

                # Strategy Instance
                feed_bar_types = {"main": feed_bar_type_str}
                if benchmark_bar_type:
                    feed_bar_types["benchmark"] = benchmark_bar_type

                strategy_params = cfg.strategy.resolve_params(
                    instrument_id=inst.id,
                    leverage=cfg.instrument.leverage,
                    feed_bar_types=feed_bar_types,
                )
                if u_name:
                    strategy_params["universe_filename"] = u_name

                strategies.append(
                    ImportableStrategyConfig(
                        strategy_path=f"{cfg.strategy.module_path}:{cfg.strategy.name}",
                        config_path=f"{cfg.strategy.module_path}:{cfg.strategy.resolve_config_class()}",
                        config=strategy_params,
                    )
                )
                print(f"✅ Prepared strategy for {inst.id}")

    else:
        # === Case B: Single-Instrument Strategy ===
        print(f"🎯 Running in Single-Instrument Mode: {cfg.instrument.instrument_id}")

        instrument_file = _resolve_instrument_path(
            base_dir,
            cfg.instrument.venue_name,
            cfg.instrument.instrument_id.split(".")[0],
        )
        if not instrument_file.exists():
            raise FileNotFoundError(
                f"❌ Instrument definition not found: {instrument_file}"
            )

        instrument = load_instrument(instrument_file)
        loaded_instruments[str(instrument.id)] = instrument

        feed_bar_types = {}
        for i, feed in enumerate(cfg.data_feeds):
            feed_inst = instrument
            if feed.instrument_id and feed.instrument_id != str(instrument.id):
                s_part = feed.instrument_id.split(".")[0]
                v_part = (
                    feed.instrument_id.split(".")[1]
                    if "." in feed.instrument_id
                    else cfg.instrument.venue_name
                )
                aux_path = _resolve_instrument_path(base_dir, v_part, s_part)
                if aux_path.exists():
                    feed_inst = load_instrument(aux_path)
                    loaded_instruments[str(feed_inst.id)] = feed_inst

            feed_bar_type_str = f"{feed_inst.id}-{feed.bar_type_str}"
            feed_bar_types[feed.label] = feed_bar_type_str

            csv_path = data_path / "raw" / feed.csv_file_name
            if csv_path.exists():
                _, catalog_path = loader(
                    csv_path=csv_path,
                    output_path=data_path
                    / "parquet"
                    / f"{run_timestamp}_{feed.label}_{i}",
                    instrument=feed_inst,
                    bar_type=BarType.from_str(feed_bar_type_str),
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

        strategy_params = cfg.strategy.resolve_params(
            instrument_id=instrument.id,
            leverage=cfg.instrument.leverage,
            feed_bar_types=feed_bar_types,
        )
        strategies.append(
            ImportableStrategyConfig(
                strategy_path=f"{cfg.strategy.module_path}:{cfg.strategy.name}",
                config_path=f"{cfg.strategy.module_path}:{cfg.strategy.resolve_config_class()}",
                config=strategy_params,
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
