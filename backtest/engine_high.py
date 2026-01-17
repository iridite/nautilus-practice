import gc
import sys
from collections import defaultdict
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
from nautilus_trader.model.data import Bar, BarType
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

    # 1. 准备策略与配置类（用于参数过滤）
    ConfigClass = load_strategy_config_class(
        cfg.strategy.module_path, cfg.strategy.resolve_config_class()
    )

    strategies = []
    loaded_instruments = {}

    # 用于合并同一 instrument_id 的多个 bar_types
    # 结构: {instrument_id: {"bar_types": [str], "catalog_path": str}}
    data_config_by_inst = {}

    # 预分组：将数据流按 InstrumentID 归类，提升大规模 Universe 下的性能
    feeds_by_inst = defaultdict(dict)
    global_feeds = {}

    # 创建 instrument_id -> inst_cfg 的映射用于快速查找
    inst_cfg_map = {ic.instrument_id: ic for ic in cfg.instruments}

    _catalog = ParquetDataCatalog(catalog_path)

    # 2. 数据处理与标的加载 (合并原有循环，减少冗余遍历)
    total_feeds = len(cfg.data_feeds)
    for feed_idx, data_cfg in enumerate(cfg.data_feeds, 1):
        # 优先使用 data_cfg 中的 instrument_id，如果为 None 则回退到主标的配置
        inst_id = data_cfg.instrument_id
        if inst_id is None and cfg.instrument is not None:
            inst_id = cfg.instrument.instrument_id

        # 2.1 按需加载标的信息 (仅加载有数据流定义的标的)
        if inst_id not in loaded_instruments:
            inst_cfg = inst_cfg_map.get(inst_id)
            if inst_cfg:
                inst_path = inst_cfg.get_json_path()
                if inst_path.exists():
                    try:
                        loaded_instruments[inst_id] = load_instrument(inst_path)
                    except Exception as e:
                        print(f"⚠️ Failed to load instrument {inst_id}: {e}")
                        continue
                else:
                    print(f"⚠️ Instrument path not found: {inst_path}")
                    continue
            else:
                print(f"⚠️ No instrument configuration found for {inst_id}")
                continue

        inst = loaded_instruments[inst_id]
        csv_path = data_cfg.full_path
        assert csv_path.exists(), f"CSV file not found: {csv_path}"

        feed_bar_type_str = f"{inst.id}-{data_cfg.bar_type_str}"

        # 2.2 归类数据流标签 (benchmark 为全局，其余归属特定标的)
        if data_cfg.label == "benchmark":
            global_feeds[data_cfg.label] = feed_bar_type_str
        else:
            feeds_by_inst[inst_id][data_cfg.label] = feed_bar_type_str

        # 2.3 高级引擎需要将数据导入 Catalog (Parquet)
        # 优化：先检查 catalog 中是否已存在该 bar_type 的数据，避免重复导入
        bar_type = BarType.from_str(feed_bar_type_str)
        existing_intervals = _catalog.get_intervals(
            data_cls=Bar, identifier=str(bar_type)
        )

        if existing_intervals:
            # 单行更新进度
            sys.stdout.write(
                f"\r⏩ [{feed_idx}/{total_feeds}] Skipping: {bar_type.instrument_id} (exists in catalog){' ' * 20}"
            )
            sys.stdout.flush()
        else:
            try:
                sys.stdout.write(
                    f"\r📖 [{feed_idx}/{total_feeds}] Importing: {bar_type.instrument_id}{' ' * 30}"
                )
                sys.stdout.flush()
                catalog_loader(
                    catalog=_catalog,
                    csv_path=csv_path,
                    instrument=inst,
                    bar_type=bar_type,
                )
            except Exception as e:
                print(
                    f"\n[Backtest Engine High] ❌ Error loading {data_cfg.csv_file_name}: {e}"
                )

        # 2.4 合并同一 instrument_id 的 bar_types
        # 关键：必须使用 bar_types (list[str]) 而非 bar_type，否则参数被忽略导致无数据加载！
        inst_id_str = str(inst.id)
        if inst_id_str not in data_config_by_inst:
            data_config_by_inst[inst_id_str] = {
                "instrument_id": inst.id,
                "bar_types": [],
                "catalog_path": str(catalog_path),
            }
        # 避免添加重复的 bar_type
        bar_type_str = str(bar_type)
        if bar_type_str not in data_config_by_inst[inst_id_str]["bar_types"]:
            data_config_by_inst[inst_id_str]["bar_types"].append(bar_type_str)

    # 4. 循环生成策略配置
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
            leverage=cfg.instrument.leverage if cfg.instrument else 1,
            # TODO：所以说杠杆不能跟 inst 绑定
            feed_bar_types=combined_feeds,
        )

        final_params = filter_strategy_params(strat_params, ConfigClass)

        # 封装为 Nautilus 可识别的导入配置
        strategies.append(
            ImportableStrategyConfig(
                strategy_path=strategy_path,
                config_path=config_path,
                config=final_params,
            )
        )

    # 3. 从合并后的配置生成 BacktestDataConfig 列表
    backtest_data_configs = []
    for inst_id_str, cfg_data in data_config_by_inst.items():
        backtest_data_configs.append(
            BacktestDataConfig(
                catalog_path=cfg_data["catalog_path"],
                data_cls="nautilus_trader.model.data:Bar",
                instrument_id=cfg_data["instrument_id"],
                bar_types=cfg_data["bar_types"],  # 合并后的 bar_types 列表
                start_time=cfg.start_date,
                end_time=cfg.end_date,
            )
        )

    # 换行结束进度显示
    print(
        f"\n✅ Data import complete. Created {len(backtest_data_configs)} data configs (merged by instrument)."
    )

    # 诊断日志：单行刷新显示数据配置进度
    total_configs = len(backtest_data_configs)
    print(f"\n📋 BacktestDataConfig Summary: {total_configs} configs")
    for i, data_cfg in enumerate(backtest_data_configs, 1):
        sys.stdout.write(
            f"\r  Processing [{i}/{total_configs}]: {data_cfg.instrument_id}{'':20}"
        )
        sys.stdout.flush()
    print(f"\r  ✅ Loaded {total_configs} data configs{'':40}")

    # 验证 catalog 中实际存在的数据（单行刷新）
    print("🔍 Verifying catalog data availability...")
    verified_count = 0
    missing_count = 0
    total_bar_types = sum(
        len(data_cfg.bar_types or []) for data_cfg in backtest_data_configs
    )
    checked = 0
    for data_cfg in backtest_data_configs:
        if data_cfg.bar_types:
            for bt_str in data_cfg.bar_types:
                checked += 1
                intervals = _catalog.get_intervals(data_cls=Bar, identifier=bt_str)
                if intervals:
                    verified_count += 1
                else:
                    missing_count += 1
                    # 只打印缺失数据的警告
                    print(f"\n  ❌ {bt_str}: NO DATA FOUND IN CATALOG!")
                # 单行刷新进度
                sys.stdout.write(
                    f"\r  Verifying [{checked}/{total_bar_types}] ✅ {verified_count} | ❌ {missing_count}{'':20}"
                )
                sys.stdout.flush()
    print(
        f"\r  📊 Catalog verification: {verified_count} OK, {missing_count} missing{'':30}"
    )

    # 5. 配置交易所 (Venue)
    venue_name = (
        cfg.instrument.venue_name
        if cfg.instrument
        else cfg.data_feeds[0].csv_file_name.split("/")[-1].split("-")[0]
    )

    venue_configs = [
        BacktestVenueConfig(
            name=venue_name,
            oms_type="NETTING",
            account_type="MARGIN",
            base_currency="USDT",  # TODO：到时候使用内置的货币类型
            starting_balances=cfg.initial_balances,
            fee_model=ImportableFeeModelConfig(
                fee_model_path="nautilus_trader.backtest.models:MakerTakerFeeModel",
                config_path="nautilus_trader.backtest.config:MakerTakerFeeModelConfig",
                config={},
            ),
            trade_execution=True,
        ),
    ]

    # 6. 配置日志 (Logging)
    logging_config = None
    if cfg.logging:
        logging_config = LoggingConfig(
            log_level=cfg.logging.log_level,
            log_level_file=cfg.logging.log_level_file,
            log_component_levels=cfg.logging.log_component_levels,
            log_components_only=cfg.logging.log_components_only,
            log_directory=str(base_dir / "log" / "backtest" / "high_level"),
        )

    # 7. 执行回测 (Execution)
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
    print(f"   - Data configs: {len(backtest_data_configs)}")
    print(f"   - Venue configs: {len(venue_configs)}")
    print(f"   - Strategy configs: {len(strategies)}")

    results = node.run()

    print("✅ Backtest Complete.")

    # 打印回测结果摘要
    if results:
        for result in results:
            _print_results(result)

    # if results:
    #     _print_results(results[0])


def _print_results(result: BacktestResult):
    """打印回测结果摘要"""
    print("\n" + "=" * 65)
    print("🏆 Backtest Report")
    print("=" * 65)
    print(f"Duration:\t       {result.elapsed_time:.4f}s")
    print(f"Orders:\t         {result.total_orders}")
    print(f"Positions:\t      {result.total_positions}")

    if result.stats_pnls:
        for currency, metrics in result.stats_pnls.items():
            print(f"💰 PnL ({currency}):")
            for k, v in metrics.items():
                if v == v:  # Check for NaN
                    print(f"   * {k:<25}: {v:,.4f}")

    if result.stats_returns:
        for currency, val in result.stats_returns.items():
            print(f"- {currency:<25} {val:,.4f}")
    print("=" * 65 + "\n")


def catalog_loader(
    catalog: ParquetDataCatalog,
    csv_path: Path,
    instrument: Instrument,
    bar_type: BarType,
) -> None:
    """
    将 CSV 数据导入 Catalog (Parquet)。

    注意：调用前应先检查数据是否已存在，避免重复解析巨大的 CSV。
    检查逻辑已移至 run_high_level 主循环中，以减少冗余函数调用。
    """
    # 日志输出已移至调用方，此处不再打印

    # 3. 高效加载 CSV
    # 注意：必须使用 index_col='datetime' 而非 index_col=0
    # 因为 usecols 会改变列的相对位置，index_col=0 会错误地把 'open' 作为索引
    df: DataFrame = CSVBarDataLoader.load(
        file_path=csv_path,
        index_col="datetime",
        usecols=["datetime", "open", "high", "low", "close", "volume"],
        parse_dates=True,
    )
    df.sort_index(inplace=True)

    # 4. 转换并写入
    # Wrangler 将 DataFrame 转换为 NT 内部的 Bar 序列
    wrangler = BarDataWrangler(bar_type, instrument)

    # 写入标的信息 (NT 的写入是幂等的，多次写入同一个 Instrument 不会报错)
    catalog.write_data([instrument])

    # 写入 Bar 数据
    catalog.write_data(wrangler.process(df))

    # 5. 轻量级校验
    intervals = catalog.get_intervals(data_cls=Bar, identifier=str(bar_type))
    if not intervals:
        raise ValueError(f"❌ Failed to verify data in catalog for {instrument.id}")
