from datetime import datetime
from pathlib import Path

import pandas as pd
from nautilus_trader.adapters.binance import BINANCE_VENUE
from nautilus_trader.adapters.okx import OKX_VENUE
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

    # Map string venue to object
    venue_map = {
        "BINANCE": BINANCE_VENUE,
        "OKX": OKX_VENUE,
    }
    venue_obj = venue_map.get(cfg.instrument.venue)
    # TODO: see if there's a better method, that could direct designate Venue
    if not venue_obj:
        raise ValueError(f"Unsupported venue: {cfg.instrument.venue}")

    engine.add_venue(
        venue=venue_obj,
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
    # low-end backtest engine loads data by itself
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
        elif "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"])
            df.set_index("datetime", inplace=True)

        # Filter columns
        df = df[["open", "high", "low", "close", "volume"]]

        # Filter by date if provided in config
        if cfg.backtest.start_date:
            df = df[df.index >= pd.Timestamp(cfg.backtest.start_date)]
        if cfg.backtest.end_date:
            df = df[df.index <= pd.Timestamp(cfg.backtest.end_date)]

        if len(df) == 0:
            print(f"❌ Error: No data found for {inst.id} within the specified date range in {cfg.backtest.start_date} to {cfg.backtest.end_date}")
            return
        else:
            print(f"📥 Loaded {len(df)} rows from CSV: {csv_path}")

        bars = wrangler.process(df)
        engine.add_data(bars)
    except FileNotFoundError:
        print(f"❌ Error: Data file not found at {csv_path}")
        return

    # 4.1 Load Aux Data (e.g. Trend Layer)
    if cfg.aux_data:
        aux_bar_type_str = f"{inst.id}-{cfg.aux_data.bar_type_str}"
        aux_bar_type = BarType.from_str(aux_bar_type_str)
        aux_wrangler = BarDataWrangler(aux_bar_type, inst)

        aux_csv_path = base_dir / "data" / "raw" / cfg.aux_data.csv_file_name
        try:
            aux_df = pd.read_csv(aux_csv_path)
            # Basic preprocessing
            if "timestamp" in aux_df.columns:
                aux_df["timestamp"] = (
                    pd.to_datetime(aux_df["timestamp"], unit="ms")
                    if aux_df["timestamp"].dtype != "datetime64[ns]"
                    else aux_df["timestamp"]
                )
                aux_df.set_index("timestamp", inplace=True)

            aux_df = aux_df[["open", "high", "low", "close", "volume"]]

            if cfg.backtest.start_date:
                aux_df = aux_df[aux_df.index >= pd.Timestamp(cfg.backtest.start_date)]
            if cfg.backtest.end_date:
                aux_df = aux_df[aux_df.index <= pd.Timestamp(cfg.backtest.end_date)]

            print(f"📥 Loaded Aux Data: {len(aux_df)} rows")
            aux_bars = aux_wrangler.process(aux_df)
            engine.add_data(aux_bars)
        except FileNotFoundError:
            print(f"❌ Error: Aux Data file not found at {aux_csv_path}")
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

    # Inject MTF params if present
    if cfg.aux_data:
        strategy_params["trade_bar_type"] = bar_type_str
        strategy_params["trend_bar_type"] = f"{inst.id}-{cfg.aux_data.bar_type_str}"

    # Instantiate Config
    # Filter params to match what the ConfigClass actually accepts
    # This handles cases where some strategies need 'bar_type' and others (like MTF) don't
    try:
        valid_fields = set(ConfigClass.__annotations__.keys())
        # Inspect parent classes for inherited fields if needed (simple approximation)
        if hasattr(ConfigClass, "__mro__"):
            for base in ConfigClass.__mro__:
                if hasattr(base, "__annotations__"):
                    valid_fields.update(base.__annotations__.keys())

        final_params = {k: v for k, v in strategy_params.items() if k in valid_fields}

        strat_config = ConfigClass(**final_params)
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
