import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Set

import pandas as pd
from nautilus_trader.analysis.tearsheet import create_tearsheet
from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.models.fee import MakerTakerFeeModel
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.config import RiskEngineConfig
from nautilus_trader.model import BarType, TraderId
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import (
    AccountType,
    BarAggregation,
    BookType,
    OmsType,
)
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.persistence.wranglers import BarDataWrangler

from backtest.utils import load_strategy_class, load_strategy_config_class
from config.definitions import BackTestConfig, DataConfig
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


def _load_data_for_inst(
    engine: BacktestEngine,
    base_dir: Path,
    cfg: BackTestConfig,
    inst,
    data_cfg: DataConfig,
):
    """为特定 Instrument 加载数据"""
    feed_bar_type_str = f"{inst.id}-{data_cfg.bar_type_str}"
    feed_bar_type = BarType.from_str(feed_bar_type_str)

    # 构建 CSV 路径。如果是从 Universe 自动推导的，我们需要根据模板寻找
    # 这里假设 csv_file_name 已经由 settings 或逻辑处理好，或者我们根据 symbol 动态生成
    csv_path = base_dir / "data" / "raw" / data_cfg.csv_file_name

    if not csv_path.exists():
        return None

    try:
        df = pd.read_csv(csv_path)
        if "timestamp" in df.columns:
            df["timestamp"] = (
                pd.to_datetime(df["timestamp"], unit="ms")
                if df["timestamp"].dtype != "datetime64[ns]"
                else df["timestamp"]
            )
            df.set_index("timestamp", inplace=True)
        elif "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"])
            df.set_index("datetime", inplace=True)

        df = df[["open", "high", "low", "close", "volume"]]
        if cfg.start_date:
            df = df[df.index >= pd.Timestamp(cfg.start_date)]
        if cfg.end_date:
            df = df[df.index <= pd.Timestamp(cfg.end_date)]

        if len(df) > 0:
            wrangler = BarDataWrangler(feed_bar_type, inst)
            bars = wrangler.process(df)
            engine.add_data(bars)
            return feed_bar_type
    except Exception as e:
        print(f"❌ Error loading data for {inst.id}: {e}")
    return None


def run_low_level(cfg: BackTestConfig, base_dir: Path):
    print(f"🚀 Starting Multi-Instrument Low-Level Backtest: {cfg.strategy.name}")

    # 1. Configure Engine
    logging_config = None
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

    engine_config = BacktestEngineConfig(
        trader_id=TraderId("BACKTESTER-001"),
        logging=logging_config,
        risk_engine=RiskEngineConfig(bypass=False),
    )
    engine = BacktestEngine(engine_config)

    # 2. Configure Venue
    engine.add_venue(
        venue=Venue(cfg.instrument.venue_name),
        oms_type=OmsType.HEDGING,
        book_type=BookType.L1_MBP,
        account_type=AccountType.MARGIN,
        base_currency=USDT,
        starting_balances=cfg.initial_balances,
        trade_execution=True,
        fee_model=MakerTakerFeeModel(),
    )

    # 3. Resolve Universe Instruments
    universe_symbols = set()
    universe_file = None

    # 尝试获取 universe_filename
    params = cfg.strategy.params
    u_name = (
        params.get("universe_filename")
        if isinstance(params, dict)
        else getattr(params, "universe_filename", None)
    )

    if u_name:
        universe_file = base_dir / "data" / u_name
        if universe_file.exists():
            with open(universe_file, "r") as f:
                u_data = json.load(f)
                for month_list in u_data.values():
                    universe_symbols.update(month_list)
            print(f"🌌 Universe loaded: {len(universe_symbols)} symbols found.")

    # 4. Load Strategy Classes
    StrategyClass = load_strategy_class(cfg.strategy.module_path, cfg.strategy.name)
    ConfigClass = load_strategy_config_class(
        cfg.strategy.module_path, cfg.strategy.resolve_config_class()
    )

    # 5. Data and Strategy Loading
    loaded_instruments = {}
    strategies_count = 0

    if universe_symbols:
        # === Case A: Universe-based Multi-Instrument Strategy (e.g., RS-Squeeze) ===
        print(
            f"🌌 Running in Universe Mode with {len(universe_symbols)} potential symbols."
        )

        # 5.1 Load Benchmark (if any)
        benchmark_inst = None
        benchmark_bt = None
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
                    engine.add_instrument(benchmark_inst)
                    loaded_instruments[str(benchmark_inst.id)] = benchmark_inst
                    benchmark_bt = _load_data_for_inst(
                        engine, base_dir, cfg, benchmark_inst, feed
                    )

        # 5.2 Load each Universe member
        # Find the 'main' data feed as a template for timeframe/exchange
        main_feed_template = next(
            (f for f in cfg.data_feeds if f.label == "main"), None
        )
        if not main_feed_template:
            print(
                "❌ No 'main' data feed found in config to use as template for universe."
            )
            return

        for symbol in sorted(list(universe_symbols)):
            # 提取基础资产 (e.g., SOLUSDT:USDT -> SOL)
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
                    engine.add_instrument(inst)
                    loaded_instruments[str(inst.id)] = inst
                except Exception as e:
                    print(f"⚠️ Failed to load instrument {inst_id_str}: {e}")
                    continue

            try:
                # 构造 DataConfig
                timeframe = f"{main_feed_template.bar_period}{'h' if main_feed_template.bar_aggregation == BarAggregation.HOUR else 'm'}"
                if main_feed_template.bar_aggregation == BarAggregation.DAY:
                    timeframe = f"{main_feed_template.bar_period}d"

                universe_data_cfg = DataConfig(
                    csv_file_name=f"{clean_base}USDT/{cfg.instrument.venue_name.lower()}-{clean_base}USDT-{timeframe}-{cfg.start_date}_{cfg.end_date}.csv",
                    label="main",
                )

                bt = _load_data_for_inst(engine, base_dir, cfg, inst, universe_data_cfg)
                if bt:
                    feed_bar_types = {"main": str(bt)}
                    if benchmark_bt:
                        feed_bar_types["benchmark"] = str(benchmark_bt)

                    strat_params = cfg.strategy.resolve_params(
                        instrument_id=inst.id,
                        leverage=cfg.instrument.leverage,
                        feed_bar_types=feed_bar_types,
                    )

                    # 自动注入 universe_filename 如果策略需要
                    valid_fields = set(ConfigClass.__annotations__.keys())
                    if hasattr(ConfigClass, "__mro__"):
                        for base in ConfigClass.__mro__:
                            if hasattr(base, "__annotations__"):
                                valid_fields.update(base.__annotations__.keys())

                    if "universe_filename" in valid_fields and u_name:
                        strat_params["universe_filename"] = u_name

                    # 实例化并添加
                    # 过滤掉 ConfigClass 不支持的参数
                    final_params = {
                        k: v for k, v in strat_params.items() if k in valid_fields
                    }
                    strat_config = ConfigClass(**final_params)
                    strategy = StrategyClass(config=strat_config)
                    engine.add_strategy(strategy)
                    strategies_count += 1
                    print(f"✅ Added strategy for {inst.id}")
            except Exception as e:
                print(f"⚠️ Failed to setup {inst_id_str}: {e}")

    else:
        # === Case B: Single-Instrument Strategy (e.g., Dual Thrust) ===
        print(f"🎯 Running in Single-Instrument Mode: {cfg.instrument.instrument_id}")

        # 5.1 Load Main Instrument
        symbol_part = cfg.instrument.instrument_id.split(".")[0]
        venue_part = cfg.instrument.venue_name
        inst_path = _resolve_instrument_path(base_dir, venue_part, symbol_part)
        if not inst_path.exists():
            print(f"❌ Main instrument file not found: {inst_path}")
            return

        main_inst = load_instrument(inst_path)
        engine.add_instrument(main_inst)
        loaded_instruments[str(main_inst.id)] = main_inst

        # 5.2 Load All Configured Feeds
        feed_bar_types = {}
        for feed in cfg.data_feeds:
            # 如果 feed 指定了不同的 instrument_id，则加载它
            if feed.instrument_id and feed.instrument_id != str(main_inst.id):
                # 这里支持辅助标的 (例如 benchmark)
                s_part = feed.instrument_id.split(".")[0]
                v_part = (
                    feed.instrument_id.split(".")[1]
                    if "." in feed.instrument_id
                    else venue_part
                )
                aux_path = _resolve_instrument_path(base_dir, v_part, s_part)
                if aux_path.exists():
                    aux_inst = load_instrument(aux_path)
                    if str(aux_inst.id) not in loaded_instruments:
                        engine.add_instrument(aux_inst)
                        loaded_instruments[str(aux_inst.id)] = aux_inst
                    bt = _load_data_for_inst(engine, base_dir, cfg, aux_inst, feed)
                    if bt:
                        feed_bar_types[feed.label] = str(bt)
            else:
                # 否则加载主标的数据
                bt = _load_data_for_inst(engine, base_dir, cfg, main_inst, feed)
                if bt:
                    feed_bar_types[feed.label] = str(bt)

        # 5.3 Instantiate Strategy
        strat_params = cfg.strategy.resolve_params(
            instrument_id=main_inst.id,
            leverage=cfg.instrument.leverage,
            feed_bar_types=feed_bar_types,
        )
        valid_fields = set(ConfigClass.__annotations__.keys())
        if hasattr(ConfigClass, "__mro__"):
            for base in ConfigClass.__mro__:
                if hasattr(base, "__annotations__"):
                    valid_fields.update(base.__annotations__.keys())

        final_params = {k: v for k, v in strat_params.items() if k in valid_fields}
        strat_config = ConfigClass(**final_params)
        strategy = StrategyClass(config=strat_config)
        engine.add_strategy(strategy)
        strategies_count = 1
        print(f"✅ Added strategy for {main_inst.id}")

    # 5. Run
    if strategies_count == 0:
        print("❌ No strategies were initialized. Check your universe and data files.")
        return

    print(f"⏳ Running engine with {strategies_count} strategy instances...")
    engine.run()
    print("✅ Backtest finished.")

    # 6. Report
    if cfg.output_html_report:
        OUTPUT_DIR = base_dir / "output"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().isoformat().replace(":", "-")
        report_path = OUTPUT_DIR / f"multi_backtest_{timestamp}.html"
        create_tearsheet(engine=engine, output_path=str(report_path))
        print(f"📊 Report generated: {report_path}")

    engine.reset()
    engine.dispose()
