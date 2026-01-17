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

    strategies = []
    # (instrument_id, label) -> bar_type_str
    all_feed_types = {}
    backtest_data_configs = []

    # 2. 加载标的与数据处理
    loaded_instruments = {}
    for inst_cfg in cfg.instruments:
        inst_path = inst_cfg.get_json_path()
        if inst_path.exists():
            try:
                loaded_instruments[inst_cfg.instrument_id] = load_instrument(inst_path)
            except Exception as e:
                print(f"⚠️ Failed to load instrument {inst_cfg.instrument_id}: {e}")

    # 3.1 预处理并转换所有数据为 Parquet (Nautlius High-level 必须)
    for i, data_cfg in enumerate(cfg.data_feeds):
        # 此处的 data_feeds 如果在前面一切正常的话那就应该和 cfg.instruments 是完全一样的内容
        # data_feeds 来自于 load_instrument，里面已经定义了 data_cfg.csv_file_name

        inst_id = data_cfg.instrument_id or str(cfg.instrument.instrument_id)
        # 同时适配单 inst 和 多 inst

        inst = loaded_instruments.get(inst_id)

        assert inst, f"Failed to find instrument {inst_id}"

        csv_path = data_cfg.full_path
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

        _BDC = BacktestDataConfig(
            catalog_path=str(catalog_path),
            data_cls="nautilus_trader.model.data:Bar",
            instrument_id=inst.id,
            start_time=cfg.start_date,
            end_time=cfg.end_date,
        )

        backtest_data_configs.append(_BDC)

    # --- 优化后的策略实例化逻辑 ---

    # 1. 预分组：将数据流按 InstrumentID 归类，提升大规模 Universe 下的性能
    from collections import defaultdict

    feeds_by_inst = defaultdict(dict)
    global_feeds = {}

    for (iid, label), bt_str in all_feed_types.items():
        if label == "benchmark":
            global_feeds[label] = bt_str
        else:
            feeds_by_inst[iid][label] = bt_str

    # 2. 循环生成策略配置
    strategy_path = f"{cfg.strategy.module_path}:{cfg.strategy.name}"
    config_path = f"{cfg.strategy.module_path}:{cfg.strategy.resolve_config_class()}"

    for inst_id, inst in loaded_instruments.items():
        local_feeds = feeds_by_inst.get(inst_id, {})

        # 核心逻辑：只有拥有 'main' 数据流的标的才实例化策略
        if "main" not in local_feeds:
            continue

        # 合并本地和全局数据流标签
        combined_feeds = {**local_feeds, **global_feeds}

        # 生成并过滤参数
        # 注意：resolve_params 内部会自动处理 cfg.strategy.params 中的原始参数
        strat_params = cfg.strategy.resolve_params(
            instrument_id=inst.id,
            leverage=cfg.instrument.leverage,
            feed_bar_types=combined_feeds,
        )

        final_params = filter_strategy_params(strat_params, ConfigClass)

        # 3. 封装为 Nautilus 可识别的导入配置
        strategies.append(
            ImportableStrategyConfig(
                strategy_path=strategy_path,
                config_path=config_path,
                config=final_params,
            )
        )

    print(f"✅ Created {len(strategies)} strategy instances.")

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

    assert len(backtest_data_configs) != 0, "No data feeds were configured."

    run_config = BacktestRunConfig(
        engine=eng_cfg,
        data=backtest_data_configs,
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
