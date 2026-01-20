from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

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
    BookType,
    OmsType,
)
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.persistence.wranglers import BarDataWrangler

from backtest.utils import (
    filter_strategy_params,
    load_strategy_class,
    load_strategy_config_class,
)
from config.definitions import (
    BackTestConfig,
    DataConfig,
)
from utils.instrument_loader import load_instrument


def _load_data_for_feed(
    engine: BacktestEngine,
    base_dir: Path,
    cfg: BackTestConfig,
    data_cfg: DataConfig,
    loaded_instruments: Dict,
) -> Optional[BarType]:
    """
    加载 CSV 数据并注入回测引擎。
    """
    # 确定关联的 Instrument ID (优先使用数据配置中的 ID，否则使用全局默认 ID)
    inst_id_str = data_cfg.instrument_id or str(cfg.instrument.instrument_id)
    inst = loaded_instruments.get(inst_id_str)
    if not inst:
        print(f"⚠️ Instrument {inst_id_str} not found for feed {data_cfg.csv_file_name}")
        return None

    feed_bar_type_str = f"{inst.id}-{data_cfg.bar_type_str}"
    feed_bar_type = BarType.from_str(feed_bar_type_str)

    csv_path = data_cfg.full_path
    if not csv_path.exists():
        print(f"⚠️ CSV file not found: {csv_path}")
        return None

    try:
        df = pd.read_csv(csv_path)
        # 统一处理时间列
        time_col = "timestamp" if "timestamp" in df.columns else "datetime"
        if time_col in df.columns:
            if time_col == "timestamp" and df[time_col].dtype != "datetime64[ns]":
                df[time_col] = pd.to_datetime(df[time_col], unit="ms")
            else:
                df[time_col] = pd.to_datetime(df[time_col])
            df.set_index(time_col, inplace=True)

        # 仅保留核心 OHLCV 列
        df = df[["open", "high", "low", "close", "volume"]]

        # 按需截取时间段（确保时区一致性）
        if cfg.start_date:
            start_ts = pd.Timestamp(cfg.start_date)
            # 移除时区信息以统一比较（NautilusTrader 内部使用 UTC 纳秒）
            if start_ts.tz is not None:
                start_ts = start_ts.tz_localize(None)
            df = df[df.index >= start_ts]

        if cfg.end_date:
            end_ts = pd.Timestamp(cfg.end_date)
            # 移除时区信息以统一比较
            if end_ts.tz is not None:
                end_ts = end_ts.tz_localize(None)
            df = df[df.index <= end_ts]

        if len(df) == 0:
            print(f"⚠️ No data available in range for {data_cfg.csv_file_name}")
            return None

        # 使用 Wrangler 转换为内部 Bar 格式并注入
        wrangler = BarDataWrangler(feed_bar_type, inst)
        bars = wrangler.process(df)
        engine.add_data(bars)
        return feed_bar_type
    except Exception as e:
        print(f"❌ Error loading {data_cfg.csv_file_name}: {e}")
        return None


def run_low_level(cfg: BackTestConfig, base_dir: Path):
    """
    运行低级引擎回测 (Low-level Engine)。
    完全由 BackTestConfig 驱动，移除了硬编码的 Universe 加载逻辑。
    """
    print(f"🚀 Starting Backtest: {cfg.strategy.name}")

    # 1. 配置日志 (Logging)
    logging_config = None
    if cfg.logging:
        logging_config = LoggingConfig(
            log_level=cfg.logging.log_level,
            log_level_file=cfg.logging.log_level_file,
            log_directory=str(base_dir / "log" / "backtest" / "low_level"),
        )

    # 2. 初始化引擎 (Engine)
    engine = BacktestEngine(
        BacktestEngineConfig(
            trader_id=TraderId("BACKTESTER-001"),
            logging=logging_config,
            risk_engine=RiskEngineConfig(bypass=False),
        )
    )

    # 3. 配置交易所 (Venue/Exchange)
    engine.add_venue(
        venue=Venue(cfg.instrument.venue_name),
        oms_type=OmsType.NETTING,
        book_type=BookType.L1_MBP,
        account_type=AccountType.MARGIN,
        base_currency=USDT,
        starting_balances=cfg.initial_balances,
        trade_execution=True,
        fee_model=MakerTakerFeeModel(),
    )

    # 4. 加载标的定义 (Instruments)
    loaded_instruments = {}
    for inst_cfg in cfg.instruments:
        inst_path = inst_cfg.get_json_path()
        if inst_path.exists():
            try:
                inst = load_instrument(inst_path)
                engine.add_instrument(inst)
                loaded_instruments[str(inst.id)] = inst
            except Exception as e:
                print(f"⚠️ Failed to load instrument {inst_cfg.instrument_id}: {e}")

    # 5. 加载回测数据 (Data Feeds)
    all_feeds = {}  # (instrument_id, label) -> bar_type_str
    for data_cfg in cfg.data_feeds:
        bt = _load_data_for_feed(engine, base_dir, cfg, data_cfg, loaded_instruments)
        if bt:
            # 默认绑定到配置的主标的，如果 DataConfig 没有指定
            inst_id = data_cfg.instrument_id or str(cfg.instrument.instrument_id)
            all_feeds[(inst_id, data_cfg.label)] = str(bt)

    # 6. 配置与添加策略 (Strategies)
    StrategyClass = load_strategy_class(cfg.strategy.module_path, cfg.strategy.name)
    ConfigClass = load_strategy_config_class(
        cfg.strategy.module_path, cfg.strategy.resolve_config_class()
    )

    # 提取全局共享数据流 (例如 label="benchmark")
    global_feeds = {
        label: bt for (iid, label), bt in all_feeds.items() if label == "benchmark"
    }
    strategies_count = 0

    # 遍历所有已加载的标的，为每个拥有 'main' 数据的标的创建一个策略实例
    for inst_id, inst in loaded_instruments.items():
        local_feeds = {
            label: bt
            for (iid, label), bt in all_feeds.items()
            if iid == inst_id and label != "benchmark"
        }

        if "main" not in local_feeds:
            continue

        # 合并本地数据和全局数据，生成策略参数
        strat_params = cfg.strategy.resolve_params(
            instrument_id=inst.id,
            leverage=cfg.instrument.leverage,
            feed_bar_types={**local_feeds, **global_feeds},
        )

        # 兼容 Universe 模式可能需要的额外参数
        if (
            isinstance(cfg.strategy.params, dict)
            and "universe_filename" in cfg.strategy.params
        ):
            strat_params["universe_filename"] = cfg.strategy.params["universe_filename"]

        # 过滤并实例化
        final_params = filter_strategy_params(strat_params, ConfigClass)
        strat_config = ConfigClass(**final_params)
        engine.add_strategy(StrategyClass(config=strat_config))
        strategies_count += 1

    # 7. 执行回测并生成报告 (Output)
    if strategies_count == 0:
        print(
            "❌ No strategy instances were created. Please check your config and data paths."
        )
    else:
        print(f"⏳ Running engine with {strategies_count} strategy instances...")
        engine.run()
        print("✅ Backtest finished.")

        if cfg.output_html_report:
            output_dir = base_dir / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            report_path = (
                output_dir
                / f"low_{cfg.strategy.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            )
            create_tearsheet(engine=engine, output_path=str(report_path))
            print(f"📊 Report generated: {report_path}")

    # 8. 收尾清理 (Cleanup)
    engine.reset()
    engine.dispose()
