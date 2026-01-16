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
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.persistence.loaders import CSVBarDataLoader
from nautilus_trader.persistence.wranglers import BarDataWrangler
from pandas import DataFrame

from backtest.utils import (
    filter_strategy_params,
    load_strategy_config_class,
)
from config.definitions import BackTestConfig
from utils.instrument_loader import load_instrument


def run_high_level(cfg: BackTestConfig, base_dir: Path):
    """
    运行高级引擎回测 (High-level Engine/BacktestNode)。
    完全由 BackTestConfig 驱动，移除了硬编码的 Universe 加载逻辑。
    """
    print(f"🚀 Starting High-Level Backtest: {cfg.strategy.name}")

    data_path: Path = base_dir / "data"
    catalog_path: Path = data_path / "parquet" / f"{cfg.strategy.name}"
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. 准备策略与配置类（用于参数过滤）
    ConfigClass = load_strategy_config_class(
        cfg.strategy.module_path, cfg.strategy.resolve_config_class()
    )

    # 2. 加载标的定义 (Instruments)
    loaded_instruments = {}
    for inst_cfg in cfg.instruments:
        inst_path = inst_cfg.get_json_path()
        if inst_path.exists():
            try:
                loaded_instruments[inst_cfg.instrument_id] = load_instrument(inst_path)
            except Exception as e:
                print(f"⚠️ Failed to load instrument {inst_cfg.instrument_id}: {e}")

    # 3. 准备数据流与策略实例
    strategies = []

    # (instrument_id, label) -> bar_type_str
    all_feed_types = {}

    # 3.1 预处理并转换所有数据为 Parquet (Nautlius High-level 必须)
    for i, data_cfg in enumerate(cfg.data_feeds):
        # 此处的 data_feeds 如果在前面一切正常的话那就应该和 cfg.instruments 是完全一样的内容
        # data_feeds 来自于 load_instrument，里面已经定义了 data_cfg.csv_file_name

        inst_id = data_cfg.instrument_id or str(cfg.instrument.instrument_id)
        # 同时适配单 inst 和 多 inst

        inst = loaded_instruments.get(inst_id)

        assert inst, f"Failed to find instrument {inst_id}"

        csv_path = Path(data_cfg.csv_file_name)
        assert csv_path.exists(), f"CSV file not found: {csv_path}"

        feed_bar_type_str = f"{inst.id}-{data_cfg.bar_type_str}"
        all_feed_types[(inst_id, data_cfg.label)] = feed_bar_type_str

        _catalog = ParquetDataCatalog(catalog_path)

        try:
            # 高级引擎需要将数据导入 Catalog (Parquet)
            catalog_loader(
                catalog=_catalog,
                csv_path=csv_path,
                instrument=inst,
                bar_type=BarType.from_str(feed_bar_type_str),
            )
        except Exception as e:
            print(f"❌ Error loading {data_cfg.csv_file_name}: {e}")

        BacktestDataConfig(
            catalog_path=str(catalog_path),
            data_cls="nautilus_trader.model.data:Bar",
            instrument_id=inst.id,
            start_time=cfg.start_date,
            end_time=cfg.end_date,
        )

    # 3.2 实例化策略配置
    global_feeds = {
        label: bt for (iid, label), bt in all_feed_types.items() if label == "benchmark"
    }

    for inst_id, inst in loaded_instruments.items():
        local_feeds = {
            label: bt
            for (iid, label), bt in all_feed_types.items()
            if iid == inst_id and label != "benchmark"
        }

        if "main" not in local_feeds:
            continue

        # 生成策略参数
        strat_params = cfg.strategy.resolve_params(
            instrument_id=inst.id,
            leverage=cfg.instrument.leverage,
            feed_bar_types={**local_feeds, **global_feeds},
        )

        # 兼容 Universe 文件名传递
        if (
            isinstance(cfg.strategy.params, dict)
            and "universe_filename" in cfg.strategy.params
        ):
            strat_params["universe_filename"] = cfg.strategy.params["universe_filename"]

        # 过滤并添加策略配置
        final_params = filter_strategy_params(strat_params, ConfigClass)
        strategies.append(
            ImportableStrategyConfig(
                strategy_path=f"{cfg.strategy.module_path}:{cfg.strategy.name}",
                config_path=f"{cfg.strategy.module_path}:{cfg.strategy.resolve_config_class()}",
                config=final_params,
            )
        )

    # 4. 配置交易所 (Venue)
    venue_configs = [
        BacktestVenueConfig(
            name=cfg.instrument.venue_name,
            oms_type="HEDGING",
            account_type="MARGIN",
            base_currency="USDT",  # TODO：到时候使用内置的货币类型
            starting_balances=cfg.initial_balances,
            fee_model=ImportableFeeModelConfig(  # TODO: 看看能不能就进行简单的加密手续费模型
                fee_model_path="nautilus_trader.backtest.models:MakerTakerFeeModel",
                config_path="nautilus_trader.backtest.config:MakerTakerFeeModelConfig",
                config={},
            ),
            trade_execution=True,
        ),
    ]

    # 5. 配置日志 (Logging)
    logging_config = None
    if cfg.logging:
        logging_config = LoggingConfig(
            log_level=cfg.logging.log_level,
            log_level_file=cfg.logging.log_level_file,
            log_directory=str(base_dir / "log" / "backtest" / "high_level"),
        )

    # 6. 执行回测 (Execution)
    if not strategies:
        print(
            "❌ No strategy instances were created. Please check your config and data paths."
        )
        return

    eng_cfg = BacktestEngineConfig(
        strategies=strategies,
        logging=logging_config,
        risk_engine=RiskEngineConfig(bypass=False),
    )

    run_config = BacktestRunConfig(
        engine=eng_cfg,
        data=data_configs,
        venues=venue_configs,
        raise_exception=True,
    )

    gc.collect()
    node = BacktestNode(configs=[run_config])
    print(f"⏳ Running BacktestNode with {len(strategies)} strategy instances...")
    results = node.run()
    print("✅ Backtest Complete.")

    if results:
        _print_results(results[0])


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
            for k, v in metrics.items():
                if v == v:  # Check for NaN
                    print(f"   * {k:<25}: {v:,.4f}")
    print("=" * 65 + "\n")


def catalog_loader(
    catalog: ParquetDataCatalog,
    csv_path: Path,
    instrument: Instrument,
    bar_type: BarType,
    force_rebuild: bool = False,
) -> None:
    """
    高效构建或加载数据 Catalog。

    优化点：
    1. 增加 force_rebuild 开关，默认跳过已存在的数据。
    2. 使用 header() 代替 bars() 进行轻量级校验，避免内存溢出。
    3. 合并路径创建与对象初始化。
    """

    # 2. 检查数据是否已存在 (核心优化：避免重复解析巨大的 CSV)
    if not force_rebuild:
        # header 仅读取元数据，极快且不占内存
        existing_header = catalog.header(bar_type=bar_type, instrument_id=instrument.id)
        if existing_header:
            print(
                f"✅ Data already exists in catalog for {instrument.id}, skipping CSV import."
            )
            return

    print(f"📖 Importing CSV to Catalog: {csv_path}")

    # 3. 高效加载 CSV
    # 建议：如果 datetime 是标准格式，不指定 date_format 有时反而更快 (pandas 内部优化)
    df: DataFrame = CSVBarDataLoader.load(
        file_path=csv_path,
        index_col=0,
        usecols=["datetime", "open", "high", "low", "close", "volume"],
        parse_dates=["datetime"],
    )
    df.sort_index(inplace=True)

    # 4. 转换并写入
    # Wrangler 将 DataFrame 转换为 NT 内部的 Bar 序列
    wrangler = BarDataWrangler(bar_type, instrument)

    # 写入标的信息 (NT 的写入是幂等的，多次写入同一个 Instrument 不会报错)
    catalog.write_data(instrument)

    # 写入 Bar 数据
    # 注意：对于极大数据量，这里可以考虑分块写入，但通常 1GB 以下的 CSV 这样写没问题
    catalog.write_data(wrangler.process(df))

    # 5. 轻量级校验
    header = catalog.header(bar_type=bar_type, instrument_id=instrument.id)
    if header:
        print(f"🚀 Successfully indexed {header.count} bars for {instrument.id}.")
        return
    else:
        raise ValueError(f"❌ Failed to verify data in catalog for {instrument.id}")
