from datetime import datetime
from pathlib import Path

import pandas as pd
from nautilus_trader.analysis.tearsheet import create_tearsheet
from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.models.fee import MakerTakerFeeModel
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.config import RiskEngineConfig
from nautilus_trader.model import BarType, TraderId
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import AccountType, BookType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.persistence.wranglers import BarDataWrangler

from backtest.utils import load_strategy_class, load_strategy_config_class
from config.definitions import BackTestConfig
from utils.instrument_loader import load_instrument


def run_low_level(cfg: BackTestConfig, base_dir: Path):
    print(f"🚀 Starting Low-Level Backtest with config: {cfg.strategy.name}")

    OUTPUT_DIR = base_dir / "output"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Configure Engine
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

    engine_config = BacktestEngineConfig(
        trader_id=TraderId("BACKTESTER-001"),
        logging=logging_config,
        risk_engine=RiskEngineConfig(
            bypass=False,  # 彻底关闭风控检查
            # TODO: 后期加个 RiskConfig
            # 实现在 settings 中的管理
        ),
    )
    engine = BacktestEngine(engine_config)

    # 2. Configure Venue

    assert cfg.instrument.venue_name in ["BINANCE", "OKX"], "Unsupported venue"

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

    # 3. Load Instrument

    instrument_file = (
        base_dir
        / "data"
        / "instrument"
        / cfg.instrument.venue_name
        / f"{cfg.instrument.instrument_id.split('.')[0]}.json"
    )

    if instrument_file.exists():
        print(f"📂 Loading instrument from {instrument_file}")
        inst = load_instrument(
            instrument_file
        )  # Dynamically Determine fees (industry standard defaults for OKX if not provided)
    else:
        raise FileNotFoundError(f"⚠️ Instrument file not found at {instrument_file}")
    engine.add_instrument(inst)

    # 4. Load Data Feeds (Generic Supply Framework)
    feed_bar_types = {}  # label -> bar_type (BarType object)

    for feed in cfg.data_feeds:
        # Determine instrument for this feed (support multi-instrument backtest in future)
        feed_inst = inst
        if feed.instrument_id and feed.instrument_id != str(inst.id):
            # TODO: Add logic to load auxiliary instrument if needed (e.g. for benchmark)
            pass

        feed_bar_type_str = f"{feed_inst.id}-{feed.bar_type_str}"
        feed_bar_type = BarType.from_str(feed_bar_type_str)
        feed_bar_types[feed.label] = feed_bar_type

        print(f"📥 Loading Data Feed [{feed.label}]: {feed_bar_type_str}")

        csv_path = base_dir / "data" / "raw" / feed.csv_file_name
        try:
            df = pd.read_csv(csv_path)
            # Basic preprocessing
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

            # Filter columns
            df = df[["open", "high", "low", "close", "volume"]]

            # Filter by date if provided in config
            if cfg.start_date:
                df = df[df.index >= pd.Timestamp(cfg.start_date)]
            if cfg.end_date:
                df = df[df.index <= pd.Timestamp(cfg.end_date)]

            if len(df) == 0:
                print(f"⚠️ Warning: No data found for {feed.label} within range.")
                continue

            wrangler = BarDataWrangler(feed_bar_type, feed_inst)
            bars = wrangler.process(df)
            engine.add_data(bars)
            print(f"✅ Loaded {len(df)} rows for {feed.label}")

        except FileNotFoundError:
            print(f"❌ Error: Data file not found at {csv_path}")
            return

    # 5. Configure Strategy
    StrategyClass = load_strategy_class(cfg.strategy.module_path, cfg.strategy.name)
    ConfigClass = load_strategy_config_class(
        cfg.strategy.module_path, cfg.strategy.resolve_config_class()
    )

    # Resolve params using centralized logic
    strategy_params = cfg.strategy.resolve_params(
        instrument_id=inst.id,
        leverage=cfg.instrument.leverage,
        feed_bar_types=feed_bar_types,
    )

    # Instantiate Config
    # Filter params to match what the ConfigClass actually accepts
    try:
        valid_fields = set(ConfigClass.__annotations__.keys())
        if hasattr(ConfigClass, "__mro__"):
            for base in ConfigClass.__mro__:
                if hasattr(base, "__annotations__"):
                    valid_fields.update(base.__annotations__.keys())

        final_params = {k: v for k, v in strategy_params.items() if k in valid_fields}
        strat_config = ConfigClass(**final_params)
    except Exception as e:
        print(f"❌ Error creating strategy config: {e}")
        return

    strategy = StrategyClass(config=strat_config)
    engine.add_strategy(strategy)

    # 6. Run
    print("⏳ Running engine...")
    engine.run()
    print("✅ Backtest finished.")

    # 7. Report
    if cfg.output_html_report:
        timestamp = datetime.now().isoformat().replace(":", "-")
        report_path = OUTPUT_DIR / f"{inst.id}_{timestamp}.html"
        create_tearsheet(
            engine=engine,
            output_path=str(report_path),
        )
        print(f"📊 Report generated: {report_path}")
    else:
        print("📊 Omitting report generation.")
    engine.reset()
    engine.dispose()
