from datetime import datetime
from pathlib import Path

import pandas as pd
from nautilus_trader.adapters.binance import BINANCE_VENUE
from nautilus_trader.analysis.tearsheet import create_tearsheet
from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.config import RiskEngineConfig
from nautilus_trader.model import BarType, TraderId
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import AccountType, BookType, OmsType
from nautilus_trader.persistence.wranglers import BarDataWrangler

from backtest.utils import load_strategy_class, load_strategy_config_class
from config.definitions import GlobalConfig
from utils.instrument_loader import load_instrument


def run_low_level(cfg: GlobalConfig, base_dir: Path):
    print(f"🚀 Starting Low-Level Backtest with config: {cfg.strategy.name}")

    OUTPUT_DIR = base_dir / "output"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Configure Engine
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
        risk_engine=RiskEngineConfig(
            bypass=True,  # 彻底关闭风控检查
        ),
    )
    engine = BacktestEngine(engine_config)

    # 2. Configure Venue

    engine.add_venue(
        venue=BINANCE_VENUE,  # TODO: Map cfg.instrument.venue to actual Venue object if needed
        oms_type=OmsType.HEDGING,
        book_type=BookType.L1_MBP,
        account_type=AccountType.MARGIN,
        base_currency=USDT,
        starting_balances=cfg.backtest.initial_balance,  # preconfigured at definitions.py as Money()
        trade_execution=True,
    )

    # 3. Load Instrument
    instrument_file = (
        base_dir
        / "data"
        / "instrument"
        / cfg.instrument.venue
        / f"{cfg.instrument.instrument_id.split('.')[0]}.json"
    )

    if instrument_file.exists():
        print(f"📂 Loading instrument from {instrument_file}")
        inst = load_instrument(instrument_file)
    else:
        raise FileNotFoundError(f"⚠️ Instrument file not found at {instrument_file}")
    engine.add_instrument(inst)

    # 4. Load Data
    bar_type_str = f"{inst.id}-{cfg.data.bar_type_str}"
    bar_type = BarType.from_str(bar_type_str)
    wrangler = BarDataWrangler(bar_type, inst)

    csv_path = base_dir / "data" / "raw" / cfg.data.csv_file_name
    try:
        df = pd.read_csv(csv_path)
        # Basic preprocessing
        if "timestamp" in df.columns:
            df["timestamp"] = (
                pd.to_datetime(df["timestamp"], unit="ms")
                if df["timestamp"].dtype != "datetime64[ns]"
                else df["timestamp"]
            )
            # Adjust if needed, assuming close time
            # df["timestamp"] = df["timestamp"] + pd.Timedelta(minutes=5)
            df.set_index("timestamp", inplace=True)

        # Filter columns
        df = df[["open", "high", "low", "close", "volume"]]

        # Filter by date if provided in config
        if cfg.backtest.start_date:
            df = df[df.index >= cfg.backtest.start_date]
        if cfg.backtest.end_date:
            df = df[df.index <= cfg.backtest.end_date]

        print(f"📥 Loaded {len(df)} rows from CSV")
        bars = wrangler.process(df)
        engine.add_data(bars)
    except FileNotFoundError:
        print(f"❌ Error: Data file not found at {csv_path}")
        return

    # 5. Configure Strategy
    StrategyClass = load_strategy_class(cfg.strategy.module_path, cfg.strategy.name)
    ConfigClass = load_strategy_config_class(
        cfg.strategy.module_path, cfg.strategy.config_class
    )

    # Prepare params
    strategy_params = cfg.strategy.params.copy()
    strategy_params["instrument_id"] = inst.id
    strategy_params["bar_type"] = bar_type

    # Instantiate Config
    # Note: Pydantic models or dataclasses in Nautilus might need specific types
    # We assume the ConfigClass can handle the dict unpacking or we might need to be careful
    try:
        strat_config = ConfigClass(**strategy_params)
    except Exception as e:
        print(f"❌ Error creating strategy config: {e}")
        print(f"Params provided: {strategy_params}")
        return

    strategy = StrategyClass(config=strat_config)
    engine.add_strategy(strategy)

    # 6. Run
    print("⏳ Running engine...")
    engine.run()
    print("✅ Backtest finished.")

    # 7. Report
    timestamp = datetime.now().isoformat().replace(":", "-")
    report_path = OUTPUT_DIR / f"{inst.id}_{timestamp}.html"
    create_tearsheet(
        engine=engine,
        output_path=str(report_path),
    )
    print(f"📊 Report generated: {report_path}")

    engine.reset()
    engine.dispose()
