import gc
import json
from datetime import datetime
from pathlib import Path
from typing import Any

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

from backtest.utils import (
    filter_strategy_params,
    load_strategy_config_class,
    resolve_instrument_path,
)
from config.definitions import (
    BackTestConfig,
    InstrumentConfig,
    InstrumentType,
)
from utils.data_loader import loader
from utils.instrument_loader import load_instrument


def run_high_level(cfg: BackTestConfig, base_dir: Path):
    """
    运行高级引擎回测 (High-level Engine/BacktestNode)。
    高级引擎支持并行运行、自动化数据加载和更复杂的测试场景。
    """
    print(f"🚀 Starting High-Level Backtest: {cfg.strategy.name}")

    data_path = base_dir / "data"
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. 解析 Universe
    universe_symbols = set()
    u_name = None
    params = cfg.strategy.params
    if isinstance(params, dict):
        u_name = params.get("universe_filename")
    elif hasattr(params, "universe_filename"):
        u_name = getattr(params, "universe_filename")

    if u_name:
        universe_file = data_path / u_name
        if universe_file.exists():
            with open(universe_file, "r") as f:
                u_data = json.load(f)
                for month_list in u_data.values():
                    universe_symbols.update(month_list)
            print(f"🌌 Universe loaded: {len(universe_symbols)} symbols found.")

    # 2. 准备策略与配置类
    # 即使使用 ImportableStrategyConfig，我们也需要配置类来过滤参数，防止 msgspec 校验失败
    ConfigClass = load_strategy_config_class(
        cfg.strategy.module_path, cfg.strategy.resolve_config_class()
    )

    # 2. 加载标的定义 (Instruments)
    loaded_instruments = {}
    for inst_cfg in cfg.instruments:
        inst_path = resolve_instrument_path(
            base_dir, inst_cfg.venue_name, inst_cfg.get_symbol()
        )
        if inst_path.exists():
            try:
                inst = load_instrument(inst_path)
                loaded_instruments[str(inst.id)] = inst
            except Exception as e:
                print(f"⚠️ Failed to load instrument {inst_cfg.instrument_id}: {e}")

    # 3. 准备数据流与策略实例
    data_configs = []
    strategies = []
    loaded_instruments = {}

    if universe_symbols:
        # === Case A: Universe 多标的模式 (如 RS-Squeeze) ===
        print(
            f"🌌 Running in Universe Mode with {len(universe_symbols)} potential symbols."
        )

        # 2.1 加载基准数据 (Benchmark)
        benchmark_bar_type_str = None
        for feed in cfg.data_feeds:
            if feed.label == "benchmark" and feed.instrument_id:
                s_part = feed.instrument_id.split(".")[0]
                v_part = (
                    feed.instrument_id.split(".")[1]
                    if "." in feed.instrument_id
                    else cfg.instrument.venue_name
                )
                path = resolve_instrument_path(base_dir, v_part, s_part)

                if path.exists():
                    benchmark_inst = load_instrument(path)
                    loaded_instruments[str(benchmark_inst.id)] = benchmark_inst

                    bt_str = f"{benchmark_inst.id}-{feed.bar_type_str}"
                    benchmark_bar_type_str = bt_str

                    csv_path = data_path / "raw" / feed.csv_file_name
                    if csv_path.exists():
                        _, catalog_path = loader(
                            csv_path=csv_path,
                            output_path=data_path
                            / "parquet"
                            / f"{run_timestamp}_benchmark",
                            instrument=benchmark_inst,
                            bar_type=BarType.from_str(bt_str),
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

        # 2.2 加载 Universe 各个成员
        main_feed_template = next(
            (f for f in cfg.data_feeds if f.label == "main"), None
        )
        if not main_feed_template:
            print("❌ No 'main' data feed found in config to use as template.")
            return

        for i, symbol in enumerate(sorted(list(universe_symbols))):
            # 提取基础资产 (e.g., SOLUSDT:USDT -> SOL-USDT-SWAP)
            raw_pair = symbol.split(":")[0]
            base_cur = cfg.instrument.base_currency
            clean_base = raw_pair.replace(base_cur, "")

            # 使用 InstrumentConfig.get_id_for 动态生成符合交易所规范的 ID
            inst_id_str = InstrumentConfig.get_id_for(
                venue_name=cfg.instrument.venue_name,
                base_currency=base_cur,
                quote_currency=clean_base,
                inst_type=cfg.instrument.type,
            )

            if inst_id_str in loaded_instruments:
                inst = loaded_instruments[inst_id_str]
            else:
                inst_path = resolve_instrument_path(
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

            # 构造数据路径 (推断 timeframe)
            timeframe = f"{main_feed_template.bar_period}"
            if main_feed_template.bar_aggregation == BarAggregation.HOUR:
                timeframe += "h"
            elif main_feed_template.bar_aggregation == BarAggregation.DAY:
                timeframe += "d"
            else:
                timeframe += "m"

            csv_file_name = f"{clean_base}{base_cur}/{cfg.instrument.venue_name.lower()}-{clean_base}{base_cur}-{timeframe}-{cfg.start_date}_{cfg.end_date}.csv"
            csv_path = data_path / "raw" / csv_file_name

            if csv_path.exists():
                feed_bar_type_str = f"{inst.id}-{main_feed_template.bar_type_str}"
                try:
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

                    # 准备策略参数
                    feed_bar_types = {"main": feed_bar_type_str}
                    if benchmark_bar_type_str:
                        feed_bar_types["benchmark"] = benchmark_bar_type_str

                    strat_params = cfg.strategy.resolve_params(
                        instrument_id=inst.id,
                        leverage=cfg.instrument.leverage,
                        feed_bar_types=feed_bar_types,
                    )
                    if u_name:
                        strat_params["universe_filename"] = u_name

                    # 过滤多余参数
                    final_params = filter_strategy_params(strat_params, ConfigClass)

                    strategies.append(
                        ImportableStrategyConfig(
                            strategy_path=f"{cfg.strategy.module_path}:{cfg.strategy.name}",
                            config_path=f"{cfg.strategy.module_path}:{cfg.strategy.resolve_config_class()}",
                            config=final_params,
                        )
                    )
                except Exception as e:
                    print(f"⚠️ Failed to setup {inst_id_str}: {e}")

    else:
        # === Case B: 单标的模式 ===
        print(f"🎯 Running in Single-Instrument Mode: {cfg.instrument.instrument_id}")

        symbol_part = cfg.instrument.instrument_id.split(".")[0]
        inst_path = resolve_instrument_path(
            base_dir, cfg.instrument.venue_name, symbol_part
        )
        if not inst_path.exists():
            raise FileNotFoundError(f"❌ Instrument definition not found: {inst_path}")

        main_inst = load_instrument(inst_path)
        loaded_instruments[str(main_inst.id)] = main_inst

        feed_bar_types = {}
        for i, feed in enumerate(cfg.data_feeds):
            target_inst = main_inst
            if feed.instrument_id and feed.instrument_id != str(main_inst.id):
                s_part = feed.instrument_id.split(".")[0]
                v_part = (
                    feed.instrument_id.split(".")[1]
                    if "." in feed.instrument_id
                    else cfg.instrument.venue_name
                )
                aux_path = resolve_instrument_path(base_dir, v_part, s_part)
                if aux_path.exists():
                    target_inst = load_instrument(aux_path)
                    loaded_instruments[str(target_inst.id)] = target_inst

            feed_bar_type_str = f"{target_inst.id}-{feed.bar_type_str}"
            feed_bar_types[feed.label] = feed_bar_type_str

            csv_path = data_path / "raw" / feed.csv_file_name
            if csv_path.exists():
                _, catalog_path = loader(
                    csv_path=csv_path,
                    output_path=data_path
                    / "parquet"
                    / f"{run_timestamp}_{feed.label}_{i}",
                    instrument=target_inst,
                    bar_type=BarType.from_str(feed_bar_type_str),
                )
                data_configs.append(
                    BacktestDataConfig(
                        catalog_path=str(catalog_path),
                        data_cls="nautilus_trader.model.data:Bar",
                        instrument_id=target_inst.id,
                        start_time=cfg.start_date,
                        end_time=cfg.end_date,
                    )
                )

        # 实例化策略参数
        strat_params = cfg.strategy.resolve_params(
            instrument_id=main_inst.id,
            leverage=cfg.instrument.leverage,
            feed_bar_types=feed_bar_types,
        )
        final_params = filter_strategy_params(strat_params, ConfigClass)
        strategies.append(
            ImportableStrategyConfig(
                strategy_path=f"{cfg.strategy.module_path}:{cfg.strategy.name}",
                config_path=f"{cfg.strategy.module_path}:{cfg.strategy.resolve_config_class()}",
                config=final_params,
            )
        )

    # 3. 配置交易所 (Venue)
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

    # 4. 配置日志
    logging_config = None
    if cfg.logging:
        logging_config = LoggingConfig(
            log_level=cfg.logging.log_level,
            log_level_file=cfg.logging.log_level_file,
            log_colors=cfg.logging.log_colors,
            use_pyo3=cfg.logging.use_pyo3,
            log_component_levels=cfg.logging.log_component_levels,
            log_components_only=bool(cfg.logging.log_components_only),
            log_directory=str(base_dir / "log" / "backtest" / "high_level"),
        )

    # 5. 引擎全局配置
    eng_cfg = BacktestEngineConfig(
        strategies=strategies,
        logging=logging_config,
        risk_engine=RiskEngineConfig(bypass=False),
    )

    # 6. 运行会话配置
    run_config = BacktestRunConfig(
        engine=eng_cfg,
        data=data_configs,
        venues=venue_configs,
        raise_exception=True,
    )

    # 7. 执行
    if not strategies:
        print(
            "❌ No strategies were initialized. Check your configuration and data files."
        )
        return

    gc.collect()
    node = BacktestNode(configs=[run_config])
    print(f"⏳ Running BacktestNode with {len(strategies)} strategy instances...")
    results = node.run()
    print("✅ Backtest Complete.")

    if results:
        _print_results(results[0])
    else:
        print("❌ No results generated.")


def _print_results(result: BacktestResult):
    """打印回测结果摘要"""
    print("\n" + "=" * 65)
    print("🏆 Backtest Report")
    print("=" * 65)
    print(f"⏱️ \tDuration:       {result.elapsed_time:.4f}s")
    print(f"📝 \tOrders:         {result.total_orders}")
    print(f"📍 \tPositions:      {result.total_positions}")

    if result.stats_pnls:
        for currency, metrics in result.stats_pnls.items():
            print(f"💰 PnL ({currency}):")
            core_metrics = ["PnL (total)", "PnL% (total)", "Commissions", "Fees"]
            for k in core_metrics:
                if k in metrics and metrics[k] == metrics[k]:
                    print(f"   * {k:<25}: {metrics[k]:,.4f}")

            print("   " + "-" * 40)
            for k in sorted(metrics.keys()):
                if k not in core_metrics and metrics[k] == metrics[k]:
                    print(f"   - {k:<25}: {metrics[k]:,.4f}")

    if result.stats_returns:
        print("📈 Returns:")
        for k, v in result.stats_returns.items():
            if v == v:
                print(f"   - {k:<25}: {v:.4f}")
    print("=" * 65 + "\n")
