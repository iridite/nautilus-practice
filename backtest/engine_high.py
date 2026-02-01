import gc
import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
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

from backtest.exceptions import (
    BacktestEngineError,
    CatalogError,
    DataLoadError,
    InstrumentLoadError,
)
from core.schemas import BacktestConfig
from strategy.core.loader import (
    filter_strategy_params,
    load_strategy_config_class,
)
from utils.filename_parser import FilenameParser
from utils.instrument_loader import load_instrument
from utils.oi_funding_adapter import OIFundingDataLoader

logger = logging.getLogger(__name__)


def _load_instruments(cfg: BacktestConfig) -> Dict[str, Instrument]:
    """
    加载交易标的信息

    Args:
        cfg: 回测配置

    Returns:
        Dict[str, Instrument]: instrument_id -> Instrument 的映射

    Raises:
        InstrumentLoadError: 当标的加载失败时
    """
    loaded_instruments = {}
    inst_cfg_map = {ic.instrument_id: ic for ic in cfg.instruments}

    for inst_id in inst_cfg_map:
        inst_cfg = inst_cfg_map[inst_id]
        inst_path = inst_cfg.get_json_path()

        if not inst_path.exists():
            raise InstrumentLoadError(
                f"Instrument path not found: {inst_path}", inst_id
            )

        try:
            loaded_instruments[inst_id] = load_instrument(inst_path)
        except Exception as e:
            raise InstrumentLoadError(
                f"Failed to load instrument {inst_id}: {e}", inst_id, e
            )

    return loaded_instruments


def _check_parquet_coverage(
    catalog: ParquetDataCatalog,
    bar_type: BarType,
    cfg: BacktestConfig,
) -> Tuple[bool, float]:
    """
    检查Parquet数据覆盖率

    Returns:
        Tuple[bool, float]: (是否存在, 覆盖率百分比)
    """
    try:
        existing_intervals = catalog.get_intervals(
            data_cls=Bar, identifier=str(bar_type)
        )
        if not existing_intervals:
            return False, 0.0
    except Exception:
        return False, 0.0

    # 简化逻辑：如果 Parquet 数据存在则返回 True
    return True, 100.0


def _handle_parquet_exists(
    catalog: ParquetDataCatalog,
    csv_path: Path,
    inst: Instrument,
    bar_type: BarType,
    data_cfg,
    cfg: BacktestConfig,
    feed_idx: int,
    total_feeds: int,
) -> str:
    """
    处理Parquet数据已存在的情况

    Returns:
        str: 状态消息（用于日志）
    """
    csv_exists = csv_path.exists()

    if csv_exists:
        is_consistent = _verify_data_consistency(csv_path, catalog, bar_type)

        if not is_consistent:
            try:
                catalog_loader(catalog, csv_path, inst, bar_type)
                return f"\r📖 [{feed_idx:3d}/{total_feeds}] Updated: {str(bar_type.instrument_id):<32}"
            except Exception:
                return f"\r⚠️  [{feed_idx:3d}/{total_feeds}] Using Parquet: {str(bar_type.instrument_id):<28}"
        else:
            return f"\r⏩ [{feed_idx:3d}/{total_feeds}] Verified: {str(bar_type.instrument_id):<35}"
    else:
        # 检查Parquet覆盖率
        parquet_exists, coverage_pct = _check_parquet_coverage(catalog, bar_type, cfg)

        if parquet_exists and coverage_pct < 95.0:
            # 数据不完整，触发自动下载
            download_success = _auto_download_missing_data(data_cfg, cfg)

            if download_success and csv_path.exists():
                try:
                    catalog_loader(catalog, csv_path, inst, bar_type)
                    return f"\r📖 [{feed_idx:3d}/{total_feeds}] Completed: {str(bar_type.instrument_id):<32}"
                except Exception:
                    return f"\r⚠️  [{feed_idx:3d}/{total_feeds}] Partial Parquet: {str(bar_type.instrument_id):<25} ({coverage_pct:.1f}%)"
            else:
                return f"\r⚠️  [{feed_idx:3d}/{total_feeds}] Partial Parquet: {str(bar_type.instrument_id):<25} ({coverage_pct:.1f}%)"
        else:
            # 尝试常规下载
            download_success = _auto_download_missing_data(data_cfg, cfg)

            if download_success and csv_path.exists():
                try:
                    catalog_loader(catalog, csv_path, inst, bar_type)
                    return f"\r📖 [{feed_idx:3d}/{total_feeds}] Imported: {str(bar_type.instrument_id):<32}"
                except Exception:
                    return f"\r⚠️  [{feed_idx:3d}/{total_feeds}] Using Parquet: {str(bar_type.instrument_id):<28}"
            else:
                return f"\r⚠️  [{feed_idx:3d}/{total_feeds}] Partial Parquet: {str(bar_type.instrument_id):<25}"


def _handle_parquet_missing(
    catalog: ParquetDataCatalog,
    csv_path: Path,
    inst: Instrument,
    bar_type: BarType,
    data_cfg,
    cfg: BacktestConfig,
    feed_idx: int,
    total_feeds: int,
) -> str:
    """
    处理Parquet数据不存在的情况

    Returns:
        str: 状态消息

    Raises:
        DataLoadError: 当数据完全缺失时
    """
    csv_exists = csv_path.exists()

    if csv_exists:
        try:
            catalog_loader(catalog, csv_path, inst, bar_type)
            return f"\r📖 [{feed_idx:3d}/{total_feeds}] Imported: {str(bar_type.instrument_id):<32}"
        except Exception as e:
            raise DataLoadError(
                f"Error loading {data_cfg.csv_file_name}: {e}", str(csv_path), e
            )
    else:
        download_success = _auto_download_missing_data(data_cfg, cfg)

        if download_success and csv_path.exists():
            try:
                catalog_loader(catalog, csv_path, inst, bar_type)
                return f"\r📖 [{feed_idx:3d}/{total_feeds}] Imported: {str(bar_type.instrument_id):<32}"
            except Exception:
                pass

        # 数据完全缺失
        raise DataLoadError(
            f"Critical data missing for {bar_type.instrument_id}. "
            f"CSV file not found: {csv_path}, Parquet data not available, "
            f"and auto-download failed.",
            str(csv_path),
        )


def _auto_download_data(data_cfg, cfg: BacktestConfig) -> bool:
    """
    自动下载缺失的数据文件

    Returns:
        bool: 下载是否成功
    """
    try:
        from utils.data_management.data_retrieval import batch_fetch_ohlcv

        parsed = FilenameParser.parse(data_cfg.csv_file_name)
        if not parsed:
            return False

        base_dir = Path(__file__).parent.parent
        configs = batch_fetch_ohlcv(
            symbols=[parsed.symbol],
            start_date=parsed.start_date,
            end_date=parsed.end_date,
            timeframe=parsed.timeframe,
            exchange_id=parsed.exchange,
            base_dir=base_dir,
        )

        if configs:
            csv_path = data_cfg.full_path
            return csv_path.exists() and csv_path.stat().st_size > 1024

        return False
    except Exception:
        return False


def _import_data_to_catalog(
    cfg: BacktestConfig,
    loaded_instruments: Dict[str, Instrument],
    catalog_path: Path,
) -> Tuple[Dict[str, Dict], Dict[str, str], Dict]:
    """
    将CSV数据导入Parquet目录，并组织数据流

    智能数据处理：检查Parquet覆盖率，按需导入CSV或下载数据
    """
    _catalog = ParquetDataCatalog(catalog_path)
    data_config_by_inst = {}
    feeds_by_inst = defaultdict(dict)
    global_feeds = {}
    total_feeds = len(cfg.data_feeds)

    for feed_idx, data_cfg in enumerate(cfg.data_feeds, 1):
        inst_id = data_cfg.instrument_id or (cfg.instrument.instrument_id if cfg.instrument else None)
        if inst_id not in loaded_instruments:
            continue

        inst = loaded_instruments[inst_id]
        csv_path = data_cfg.full_path
        feed_bar_type_str = f"{inst.id}-{data_cfg.bar_type_str}"
        bar_type = BarType.from_str(feed_bar_type_str)

        # 检查Parquet数据覆盖率
        parquet_exists, coverage_pct = _check_parquet_coverage(_catalog, bar_type, cfg)

        # 处理数据导入
        if parquet_exists and coverage_pct >= 80:
            status_msg = f"\r✅ [{feed_idx:3d}/{total_feeds}] Ready: {str(bar_type.instrument_id):<35}"
        elif parquet_exists:
            status_msg = _handle_parquet_exists(
                _catalog, csv_path, inst, bar_type, data_cfg, cfg, feed_idx, total_feeds
            )
        else:
            status_msg = _handle_parquet_missing(
                _catalog, csv_path, inst, bar_type, data_cfg, cfg, feed_idx, total_feeds
            )

        logger.info(status_msg, end="", flush=True)

        # 归类数据流
        if data_cfg.label == "benchmark":
            global_feeds[data_cfg.label] = feed_bar_type_str
        else:
            feeds_by_inst[inst_id][data_cfg.label] = feed_bar_type_str

        # 合并bar_types
        inst_id_str = str(inst.id)
        if inst_id_str not in data_config_by_inst:
            data_config_by_inst[inst_id_str] = {
                "instrument_id": inst.id,
                "bar_types": [],
                "catalog_path": str(catalog_path),
            }

        bar_type_str = str(bar_type)
        if bar_type_str not in data_config_by_inst[inst_id_str]["bar_types"]:
            data_config_by_inst[inst_id_str]["bar_types"].append(bar_type_str)

    logger.info(f"\n✅ Data import complete. Created {len(data_config_by_inst)} data configs.")
    return data_config_by_inst, global_feeds, feeds_by_inst


def _auto_download_missing_data(data_cfg, backtest_cfg: BacktestConfig) -> bool:
    """自动下载缺失的数据文件"""
    return _auto_download_data(data_cfg, backtest_cfg)


def _clear_parquet_data(catalog: ParquetDataCatalog, bar_type: BarType) -> None:
    """
    清理指定bar_type的Parquet数据

    Args:
        catalog: Parquet数据目录
        bar_type: 要清理的数据类型标识
    """
    try:
        import shutil

        # 获取catalog的根路径
        catalog_root = Path(catalog.path)

        # NautilusTrader实际的文件结构是: data/crypto_perpetual/{instrument_id}/
        instrument_id = str(bar_type.instrument_id)

        # 查找所有可能的数据目录
        possible_dirs = [
            catalog_root / "data" / "crypto_perpetual" / instrument_id,
            catalog_root / "data" / "Bar" / instrument_id,
            catalog_root / "data" / instrument_id,
        ]

        for data_dir in possible_dirs:
            if data_dir.exists():
                logger.info(f"   🗑️ Clearing existing Parquet data: {data_dir}")
                shutil.rmtree(data_dir)
                break
        else:
            # 如果没有找到标准目录，尝试查找包含instrument_id的任何目录
            for root, dirs, files in catalog_root.rglob("*"):
                if instrument_id in str(root) and any(
                    f.endswith(".parquet") for f in files
                ):
                    logger.info(f"   🗑️ Clearing found Parquet data: {root}")
                    shutil.rmtree(root)
                    break

    except Exception as e:
        logger.warning(f"   ⚠️ Warning: Could not clear Parquet data: {e}")
        # 不抛出异常，因为这不是致命错误


def _verify_data_consistency(
    csv_path: Path, catalog: ParquetDataCatalog, bar_type: BarType
) -> bool:
    """
    轻量级验证CSV和Parquet数据的一致性

    简化检查策略（性能优先）：
    1. 比较文件修改时间
    2. 比较数据行数（快速估算）
    3. 比较文件大小范围

    Args:
        csv_path: CSV文件路径
        catalog: Parquet数据目录
        bar_type: 数据类型标识

    Returns:
        bool: 数据是否一致
    """
    try:
        # 1. 检查CSV文件基本信息
        if not csv_path.exists() or csv_path.stat().st_size < 1024:
            return False

        # 2. 快速检查Parquet数据是否存在
        try:
            existing_intervals = catalog.get_intervals(
                data_cls=Bar, identifier=str(bar_type)
            )
            if not existing_intervals:
                return False
        except Exception:
            return False

        # 3. 比较文件修改时间（如果CSV比Parquet新，认为不一致）
        csv_mtime = csv_path.stat().st_mtime

        # 查找Parquet文件的修改时间
        catalog_root = Path(catalog.path)
        instrument_id = str(bar_type.instrument_id)
        parquet_dir = catalog_root / "data" / "crypto_perpetual" / instrument_id

        if parquet_dir.exists():
            parquet_files = list(parquet_dir.glob("*.parquet"))
            if parquet_files:
                parquet_mtime = max(f.stat().st_mtime for f in parquet_files)

                # 如果CSV文件比Parquet文件新超过1小时，认为不一致
                if csv_mtime - parquet_mtime > 3600:  # 1小时
                    return False

        # 4. 快速比较数据量（只读取CSV行数，不加载全部数据）
        try:
            csv_line_count = sum(1 for _ in open(csv_path)) - 1  # 减去header

            # 估算Parquet数据量（通过时间间隔）
            if existing_intervals:
                interval = existing_intervals[0]
                # 假设1小时数据，估算数据点数量
                estimated_parquet_count = (interval[1] - interval[0]) // (
                    3600 * 1_000_000_000
                )  # 纳秒转小时

                # 允许20%的差异（比较宽松的检查）
                if (
                    abs(csv_line_count - estimated_parquet_count)
                    / max(csv_line_count, 1)
                    > 0.2
                ):
                    return False
        except Exception:
            # 如果快速检查失败，默认认为一致（避免阻塞）
            pass

        return True

    except Exception as e:
        return False


def _create_strategy_configs(
    cfg: BacktestConfig,
    loaded_instruments: Dict[str, Instrument],
    feeds_by_inst: Dict,
    global_feeds: Dict[str, str],
    ConfigClass,
) -> List[ImportableStrategyConfig]:
    """
    创建策略配置

    Args:
        cfg: 回测配置
        loaded_instruments: 已加载的标的映射
        feeds_by_inst: 按标的分组的数据流
        global_feeds: 全局数据流
        ConfigClass: 策略配置类

    Returns:
        List[ImportableStrategyConfig]: 策略配置列表
    """
    strategies = []
    strategy_path = f"{cfg.strategy.module_path}:{cfg.strategy.name}"
    config_path = f"{cfg.strategy.module_path}:{cfg.strategy.resolve_config_class()}"

    for inst_id, inst in loaded_instruments.items():
        local_feeds = feeds_by_inst.get(inst_id, {})

        # 只有拥有 'main' 数据流的标的才创建策略实例
        if "main" not in local_feeds:
            continue

        # 合并本地和全局数据流
        combined_feeds = {**local_feeds, **global_feeds}

        # 生成并过滤参数
        strat_params = cfg.strategy.resolve_params(
            instrument_id=inst.id,
            leverage=cfg.instrument.leverage if cfg.instrument else 1,
            feed_bar_types=combined_feeds,
        )

        final_params = filter_strategy_params(strat_params, ConfigClass)

        strategies.append(
            ImportableStrategyConfig(
                strategy_path=strategy_path,
                config_path=config_path,
                config=final_params,
            )
        )

    return strategies


def run_high_level(cfg: BacktestConfig, base_dir: Path):
    """
    运行高级引擎回测 (High-level Engine/BacktestNode)

    Args:
        cfg: 回测配置
        base_dir: 项目根目录
    """
    logger.info(f"🚀 Starting High-Level Backtest: {cfg.strategy.name}")

    try:
        # 1. 准备配置类（用于参数过滤）
        ConfigClass = load_strategy_config_class(
            cfg.strategy.module_path, cfg.strategy.resolve_config_class()
        )

        # 2. 加载交易标的
        loaded_instruments = _load_instruments(cfg)
        logger.info(f"✅ Loaded {len(loaded_instruments)} instruments")

        # 3. 导入数据到Parquet目录
        data_path = base_dir / "data"
        catalog_path = data_path / "parquet" / f"{cfg.strategy.name}"

        data_config_by_inst, global_feeds, feeds_by_inst = _import_data_to_catalog(
            cfg, loaded_instruments, catalog_path
        )

        # 4. 创建策略配置
        strategies = _create_strategy_configs(
            cfg, loaded_instruments, feeds_by_inst, global_feeds, ConfigClass
        )
        logger.info(f"✅ Created {len(strategies)} strategy configurations")

        # 5. 准备回测数据配置
        backtest_data_configs = []
        for inst_id_str, cfg_data in data_config_by_inst.items():
            backtest_data_configs.append(
                BacktestDataConfig(
                    catalog_path=cfg_data["catalog_path"],
                    data_cls="nautilus_trader.model.data:Bar",
                    instrument_id=cfg_data["instrument_id"],
                    bar_types=cfg_data["bar_types"],
                    start_time=cfg.start_date,
                    end_time=cfg.end_date,
                )
            )

        # 6. 运行回测
        _run_backtest_with_custom_data(
            cfg, base_dir, strategies, backtest_data_configs, loaded_instruments
        )

    except (InstrumentLoadError, DataLoadError, CatalogError) as e:
        logger.error(f"❌ Backtest failed: {e}")
        raise
    except Exception as e:
        raise BacktestEngineError(f"Unexpected error during backtest: {e}", e)


def _run_backtest_with_custom_data(
    cfg: BacktestConfig,
    base_dir: Path,
    strategies: List[ImportableStrategyConfig],
    backtest_data_configs: List[BacktestDataConfig],
    loaded_instruments: Dict[str, Instrument],
):
    """运行BacktestNode并处理自定义数据"""
    if not strategies:
        raise BacktestEngineError(
            "No strategy instances were created. Check config and data paths."
        )

    # 配置交易所
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
            base_currency="USDT",
            starting_balances=cfg.initial_balances,
            fee_model=ImportableFeeModelConfig(
                fee_model_path="nautilus_trader.backtest.models:MakerTakerFeeModel",
                config_path="nautilus_trader.backtest.config:MakerTakerFeeModelConfig",
                config={},
            ),
            trade_execution=True,
        )
    ]

    # 配置日志
    logging_config = None
    if cfg.logging:
        logging_config = LoggingConfig(
            log_level=cfg.logging.log_level,
            log_level_file=cfg.logging.log_level_file,
            log_component_levels=cfg.logging.log_component_levels,
            log_components_only=cfg.logging.log_components_only,
            log_directory=str(base_dir / "log" / "backtest" / "high_level"),
        )

    # 构建BacktestNode配置
    eng_cfg = BacktestEngineConfig(
        strategies=strategies,
        logging=logging_config,
        risk_engine=RiskEngineConfig(bypass=False),
    )

    run_config = BacktestRunConfig(
        engine=eng_cfg,
        data=backtest_data_configs,
        venues=venue_configs,
        raise_exception=True,
    )

    # 创建并运行BacktestNode
    gc.collect()
    node = BacktestNode(configs=[run_config])
    logger.info(f"⏳ Running BacktestNode with {len(strategies)} strategy instances...")

    # 加载自定义数据
    _load_custom_data_to_engine(cfg, base_dir, node, run_config, loaded_instruments)

    # 运行回测
    results = node.run()
    logger.info("✅ Backtest Complete.")

    # 处理结果
    if results:
        _process_backtest_results(cfg, base_dir, results)


def _check_if_needs_custom_data(strategies: List[ImportableStrategyConfig]) -> bool:
    """检查策略是否需要自定义数据（OI/Funding）"""
    for strategy in strategies:
        # 检查策略配置中的 data_dependencies
        if hasattr(strategy, 'config') and isinstance(strategy.config, dict):
            data_deps = strategy.config.get('data_dependencies', [])
            if data_deps:
                for dep in data_deps:
                    if isinstance(dep, dict):
                        data_type = dep.get('data_type', '')
                        if data_type in ['oi', 'funding']:
                            return True
                    elif hasattr(dep, 'data_type'):
                        if dep.data_type in ['oi', 'funding']:
                            return True
    return False


def _load_custom_data_to_engine(
    cfg: BacktestConfig,
    base_dir: Path,
    node: BacktestNode,
    run_config: BacktestRunConfig,
    loaded_instruments: Dict[str, Instrument],
):
    """加载自定义数据(OI, Funding Rate)到回测引擎"""
    if not (cfg.start_date and cfg.end_date):
        logger.warning("⚠️ No date range specified, skipping custom data loading")
        return

    logger.info("📊 Loading custom data (OI, Funding Rate)...")

    try:
        # 构建引擎
        node.build()
        engine = node.get_engine(run_config.id)

        if engine is None:
            logger.warning("⚠️ Could not get engine from node")
            return

        # 加载自定义数据
        from utils.oi_funding_adapter import merge_custom_data_with_bars

        data_dir = base_dir / "data" / "raw"
        total_loaded = 0

        for inst_id_str, inst in loaded_instruments.items():
            instrument_id = inst.id
            symbol = str(instrument_id.symbol).split("-")[0]  # BTCUSDT-PERP -> BTCUSDT
            symbol_dir = data_dir / symbol

            if not symbol_dir.exists():
                continue

            # 查找数据文件
            oi_files = list(symbol_dir.glob("*-oi-1h-*.csv"))
            funding_files = list(symbol_dir.glob("*-funding-*.csv"))

            oi_data_list = []
            funding_data_list = []

            # 加载OI数据
            if oi_files:
                loader = OIFundingDataLoader(base_dir)
                for oi_file in oi_files:
                    oi_data_list.extend(loader.load_oi_data(
                        symbol=symbol,
                        instrument_id=instrument_id,
                        start_date=cfg.start_date,
                        end_date=cfg.end_date,
                        exchange=cfg.instrument.venue_name.lower() if cfg.instrument else "binance"
                    ))

            # 加载Funding Rate数据
            if funding_files:
                loader = OIFundingDataLoader(base_dir)
                for funding_file in funding_files:
                    funding_data_list.extend(loader.load_funding_data(
                        symbol=symbol,
                        instrument_id=instrument_id,
                        start_date=cfg.start_date,
                        end_date=cfg.end_date,
                        exchange=cfg.instrument.venue_name.lower() if cfg.instrument else "binance"
                    ))

            # 合并并添加到引擎
            if oi_data_list or funding_data_list:
                merged_data = merge_custom_data_with_bars(
                    oi_data_list, funding_data_list
                )
                engine.add_data(merged_data)
                total_loaded += len(merged_data)
                logger.info(f"   ✅ Added {len(merged_data)} custom data points for {symbol}")

        logger.info(f"✅ Total custom data loaded: {total_loaded} points")

    except Exception as e:
        logger.error(f"⚠️ Custom data loading failed: {e}")
        logger.info("Strategy will run without OI/Funding data")




def _process_backtest_results(
    cfg: BacktestConfig, base_dir: Path, results: List[BacktestResult]
):
    """处理回测结果"""
    # 收集策略统计数据
    filter_stats = None
    trade_metrics = None

    try:
        from strategy.rs_squeeze import RSSqueezeStrategy

        filter_stats = RSSqueezeStrategy.get_filter_stats_summary()
        trade_metrics = RSSqueezeStrategy.get_trade_metrics()
        RSSqueezeStrategy.print_filter_stats_report()
        RSSqueezeStrategy.reset_class_stats()
    except (ImportError, AttributeError):
        pass  # 非RS Squeeze策略时跳过

    # 提取策略配置参数
    strategy_params = cfg.strategy.params
    if hasattr(strategy_params, "model_dump"):
        strategy_config = strategy_params.model_dump()
    elif hasattr(strategy_params, "dict"):
        strategy_config = strategy_params.dict()
    elif isinstance(strategy_params, dict):
        strategy_config = strategy_params
    else:
        strategy_config = {}

    # 构建回测配置信息
    backtest_config = {
        "start_date": str(cfg.start_date),
        "end_date": str(cfg.end_date),
        "initial_balances": cfg.initial_balances,
        "strategies_count": len(results),
    }

    # 处理每个结果
    for result in results:
        # 终端输出
        _print_results(result)

        # 构建完整结果字典
        result_dict = _build_result_dict(
            result=result,
            strategy_name=cfg.strategy.name,
            strategy_config=strategy_config,
            filter_stats=filter_stats,
            trade_metrics=trade_metrics,
            backtest_config=backtest_config,
        )

        # 保存JSON文件
        json_path = _save_results_to_json(result_dict, cfg.strategy.name, base_dir)
        logger.info(f"📁 Complete results saved to: {json_path}")


def _build_result_dict(
    result: BacktestResult,
    strategy_name: str,
    strategy_config: Optional[Dict[str, Any]] = None,
    filter_stats: Optional[Dict[str, Dict[str, int]]] = None,
    trade_metrics: Optional[List[Dict]] = None,
    backtest_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    构建完整的回测结果字典，包含所有可用的回测数据。

    设计目标：
    1. 包含回测引擎能产生的所有数据，不遗漏任何信息
    2. 结构化组织，便于 AI 和人工分析
    3. 同时支持快速查看（performance）和深度分析（详细数据）

    JSON 结构：
    - meta: 元数据（策略名、时间戳、执行时长）
    - summary: 摘要统计（订单数、持仓数）
    - pnl: 盈亏数据（按货币分组）
    - returns: 收益率数据（夏普率、最大回撤、总回报等）
    - strategy_config: 完整的策略配置参数（供 AI 分析优化）
    - backtest_config: 回测配置信息（时间范围、标的数量等）
    - filter_stats: 信号过滤统计
        - by_instrument: 按标的分组的详细统计
        - total: 汇总统计
        - rates: 各种过滤率（通过率、各过滤器占比）
        - instrument_count: 标的数量
    - trade_metrics: 交易数据
        - trades: 所有交易的明细列表
        - analysis: 基础分析（胜率、盈亏比、均值等）
        - detailed_analysis: 详细分析（胜者 vs 败者对比）
    - performance: 性能摘要（整合关键指标，便于快速查看）

    Args:
        result: BacktestResult 对象
        strategy_name: 策略名称
        strategy_config: 策略配置参数（完整保存，供 AI 优化参考）
        filter_stats: 过滤器统计（来自策略类变量）
        trade_metrics: 交易指标（来自策略类变量）
        backtest_config: 回测配置信息

    Returns:
        完整的结果字典，包含回测引擎能输出的所有信息
    """
    result_dict = {
        "meta": {
            "strategy_name": strategy_name,
            "timestamp": datetime.now().isoformat(),
            "elapsed_time_seconds": result.elapsed_time,
        },
        "summary": {
            "total_orders": result.total_orders,
            "total_positions": result.total_positions,
        },
        "pnl": {},
        "returns": {},
        "strategy_config": strategy_config or {},
        "backtest_config": backtest_config or {},
        "filter_stats": {},
        "trade_metrics": {
            "trades": trade_metrics or [],
            "analysis": {},
            "detailed_analysis": {},  # 新增：更详细的交易分析
        },
        "performance": {},  # 新增：性能摘要
    }

    # 处理 PnL 指标
    if result.stats_pnls:
        for currency, metrics in result.stats_pnls.items():
            result_dict["pnl"][str(currency)] = {
                k: v if v == v else None
                for k, v in metrics.items()  # NaN -> None
            }

    # 处理收益率指标
    if result.stats_returns:
        for currency, val in result.stats_returns.items():
            result_dict["returns"][str(currency)] = val if val == val else None

    # ===== 处理过滤器统计（完整保存所有过滤器细节） =====
    if filter_stats:
        # 汇总所有实例的统计
        total_stats = {}
        for inst_id, stats in filter_stats.items():
            for key, value in stats.items():
                total_stats[key] = total_stats.get(key, 0) + value

        # 计算过滤率
        signal_checks = total_stats.get("signal_checks", 0)
        all_passed = total_stats.get("all_passed", 0)

        filter_rates = {}
        if signal_checks > 0:
            filter_rates = {
                "pass_rate": (all_passed / signal_checks * 100)
                if signal_checks > 0
                else 0,
                "filter_rate": ((signal_checks - all_passed) / signal_checks * 100)
                if signal_checks > 0
                else 0,
            }
            # 计算各个过滤器的占比
            for key in [
                "fail_trend",
                "fail_squeeze",
                "fail_squeeze_maturity",
                "fail_rs",
                "fail_extension",
                "fail_btc_bear",
                "fail_breakout",
                "fail_volume",
            ]:
                if key in total_stats:
                    filter_rates[f"{key}_rate"] = total_stats[key] / signal_checks * 100

        result_dict["filter_stats"] = {
            "by_instrument": filter_stats,
            "total": total_stats,
            "rates": filter_rates,  # 新增：各种过滤率
            "instrument_count": len(filter_stats),
        }

    # ===== 处理交易指标分析（完整保存所有交易统计） =====
    if trade_metrics:
        winners = [t for t in trade_metrics if t.get("result") == "WINNER"]
        losers = [t for t in trade_metrics if t.get("result") == "LOSER"]

        # 基础统计
        analysis = {
            "total_trades": len(trade_metrics),
            "winning_trades": len(winners),
            "losing_trades": len(losers),
            "win_rate": len(winners) / len(trade_metrics) if trade_metrics else 0,
        }

        # 盈亏统计
        all_pnls = [t.get("pnl_pct", 0) for t in trade_metrics]
        analysis["total_pnl_pct"] = sum(all_pnls)
        analysis["avg_pnl_pct"] = sum(all_pnls) / len(all_pnls) if all_pnls else 0
        analysis["max_winning_trade"] = max(all_pnls) if all_pnls else 0
        analysis["max_losing_trade"] = min(all_pnls) if all_pnls else 0

        # 胜者统计
        if winners:
            winner_pnls = [t.get("pnl_pct", 0) for t in winners]
            analysis["avg_winning_trade"] = sum(winner_pnls) / len(winners)
            analysis["avg_winner_rs_score"] = sum(
                t.get("entry_rs_score", 0) for t in winners
            ) / len(winners)
            analysis["avg_winner_bb_width_pct"] = sum(
                t.get("entry_bb_width_pct", 0) for t in winners
            ) / len(winners)
            analysis["avg_winner_volume_mult"] = sum(
                t.get("entry_volume_mult", 0) for t in winners
            ) / len(winners)

        # 败者统计
        if losers:
            loser_pnls = [t.get("pnl_pct", 0) for t in losers]
            analysis["avg_losing_trade"] = sum(loser_pnls) / len(losers)
            analysis["avg_loser_rs_score"] = sum(
                t.get("entry_rs_score", 0) for t in losers
            ) / len(losers)
            analysis["avg_loser_bb_width_pct"] = sum(
                t.get("entry_bb_width_pct", 0) for t in losers
            ) / len(losers)
            analysis["avg_loser_volume_mult"] = sum(
                t.get("entry_volume_mult", 0) for t in losers
            ) / len(losers)

        # 盈亏比和利润因子
        if winners and losers and analysis.get("avg_losing_trade", 0) != 0:
            analysis["profit_loss_ratio"] = abs(
                analysis["avg_winning_trade"] / analysis["avg_losing_trade"]
            )

            total_wins = sum([t.get("pnl_pct", 0) for t in winners])
            total_losses = abs(sum([t.get("pnl_pct", 0) for t in losers]))
            if total_losses > 0:
                analysis["profit_factor"] = total_wins / total_losses

        # 详细分析（胜者 vs 败者对比）
        detailed_analysis = {}
        if winners and losers:
            detailed_analysis["winners"] = {
                "count": len(winners),
                "avg_pnl_pct": analysis.get("avg_winning_trade", 0),
                "avg_rs_score": analysis.get("avg_winner_rs_score", 0),
                "avg_bb_width_pct": analysis.get("avg_winner_bb_width_pct", 0),
                "avg_volume_mult": analysis.get("avg_winner_volume_mult", 0),
            }
            detailed_analysis["losers"] = {
                "count": len(losers),
                "avg_pnl_pct": analysis.get("avg_losing_trade", 0),
                "avg_rs_score": analysis.get("avg_loser_rs_score", 0),
                "avg_bb_width_pct": analysis.get("avg_loser_bb_width_pct", 0),
                "avg_volume_mult": analysis.get("avg_loser_volume_mult", 0),
            }

        result_dict["trade_metrics"]["analysis"] = analysis
        result_dict["trade_metrics"]["detailed_analysis"] = detailed_analysis

    # ===== 添加性能摘要（整合关键指标，方便快速查看） =====
    # 这个部分从各个详细数据中提取关键指标，便于：
    # 1. AI 快速评估回测结果
    # 2. 人工快速浏览 JSON 时了解整体表现
    # 3. 与 current_backtest_result 对应，用于 LangGraph State
    performance_summary = {
        "total_trades": result.total_positions,
        "total_orders": result.total_orders,
        "elapsed_time_seconds": result.elapsed_time,
    }

    # 从 returns 中提取关键指标
    if result.stats_returns:
        for key, val in result.stats_returns.items():
            if "Sharpe Ratio" in str(key):
                performance_summary["sharpe_ratio"] = val if val == val else None
            elif "Max Drawdown" in str(key):
                performance_summary["max_drawdown"] = val if val == val else None
            elif "Total Return" in str(key):
                performance_summary["total_return"] = val if val == val else None

    # 从交易分析中提取关键指标
    if trade_metrics:
        analysis = result_dict["trade_metrics"]["analysis"]
        performance_summary["win_rate"] = analysis.get("win_rate", 0)
        performance_summary["profit_loss_ratio"] = analysis.get("profit_loss_ratio", 0)
        performance_summary["avg_winning_trade"] = analysis.get("avg_winning_trade", 0)
        performance_summary["avg_losing_trade"] = analysis.get("avg_losing_trade", 0)
        performance_summary["total_pnl_pct"] = analysis.get("total_pnl_pct", 0)

    # 从过滤统计中提取信息
    if filter_stats:
        filter_data = result_dict["filter_stats"]
        performance_summary["total_signals"] = filter_data["total"].get(
            "signal_checks", 0
        )
        performance_summary["signals_passed"] = filter_data["total"].get(
            "all_passed", 0
        )
        if "rates" in filter_data:
            performance_summary["signal_pass_rate"] = filter_data["rates"].get(
                "pass_rate", 0
            )

    result_dict["performance"] = performance_summary

    return result_dict


def _save_results_to_json(
    result_dict: Dict[str, Any],
    strategy_name: str,
    base_dir: Path,
) -> Path:
    """
    将回测结果保存为 JSON 文件。

    文件命名格式: {策略名称}_{YYYY-MM-DD_HH-MM-SS}.json
    存放路径: output/backtest/result/

    Args:
        result_dict: 完整的结果字典
        strategy_name: 策略名称
        base_dir: 项目根目录

    Returns:
        保存的文件路径
    """
    # 创建目录
    result_dir = base_dir / "output" / "backtest" / "result"
    result_dir.mkdir(parents=True, exist_ok=True)

    # 生成文件名
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{strategy_name}_{timestamp}.json"
    # filename = f"{strategy_name}"
    filepath = result_dir / filename

    # 保存 JSON
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result_dict, f, indent=2, ensure_ascii=False, default=str)

    return filepath


def _print_results(
    result: BacktestResult,
    strategy_config: Optional[Dict[str, Any]] = None,
):
    """
    打印回测结果摘要到终端（简化版）

    目标：保持终端输出简洁，只显示核心性能指标
    完整数据（包括策略配置、交易明细等）已保存到 JSON 文件中

    Args:
        result: 回测结果对象
        strategy_config: 策略配置（已移除，设为 None 以简化输出）
    """
    logger.info("\n" + "=" * 65)
    logger.info("🏆 Backtest Report")
    logger.info("=" * 65)
    logger.info(f"Duration:       {result.elapsed_time:.4f}s")
    logger.info(f"Orders:         {result.total_orders}")
    logger.info(f"Positions:      {result.total_positions}")

    if result.stats_pnls:
        for currency, metrics in result.stats_pnls.items():
            logger.info(f"💰 PnL ({currency}):")
            for k, v in metrics.items():
                if v == v:  # Check for NaN
                    logger.info(f"   * {k:<25}: {v:,.4f}")

    if result.stats_returns:
        for currency, val in result.stats_returns.items():
            logger.info(f"- {currency:<25} {val:,.4f}")

    # 注意：策略配置参数已保存到 JSON 文件中，终端不再打印
    # 原因：
    # 1. 保持终端输出简洁，只显示关键性能指标
    # 2. 策略配置可能有几十个参数，会使终端输出过长
    # 3. AI 可以从 JSON 文件中读取完整配置进行分析
    # 4. 人工查看时也更倾向于查看 JSON 文件而非终端滚动输出

    logger.info("=" * 65 + "\n")


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

    # 1. 读取前几行检查列名（兼容 "datetime" 和 "timestamp" 两种列名）
    sample_df = pd.read_csv(csv_path, nrows=5)

    # 确定时间列名（优先使用 timestamp，兼容 datetime）
    if "timestamp" in sample_df.columns:
        time_col = "timestamp"
    elif "datetime" in sample_df.columns:
        time_col = "datetime"
    else:
        raise ValueError(
            f"No valid time column found in {csv_path}. "
            f"Expected 'datetime' or 'timestamp', got: {list(sample_df.columns)}"
        )

    # 2. 高效加载 CSV（使用检测到的列名）
    # 注意：必须使用 index_col='<time_col>' 而非 index_col=0
    # 因为 usecols 会改变列的相对位置，index_col=0 会错误地把 'open' 作为索引
    df: DataFrame = CSVBarDataLoader.load(
        file_path=csv_path,
        index_col=time_col,  # 动态使用检测到的列名
        usecols=[time_col, "open", "high", "low", "close", "volume"],
        parse_dates=True,
    )
    df.sort_index(inplace=True)

    # 3. 转换并写入
    # Wrangler 将 DataFrame 转换为 NT 内部的 Bar 序列
    wrangler = BarDataWrangler(bar_type, instrument)

    # 写入标的信息 (NT 的写入是幂等的，多次写入同一个 Instrument 不会报错)
    catalog.write_data([instrument])

    # 写入 Bar 数据
    catalog.write_data(wrangler.process(df))

    # 4. 轻量级校验
    intervals = catalog.get_intervals(data_cls=Bar, identifier=str(bar_type))
    if not intervals:
        raise ValueError(f"❌ Failed to verify data in catalog for {instrument.id}")


# 注意：自定义数据（OI, Funding Rate）现在通过 OIFundingDataLoader 直接加载
# 不再需要序列化到 Parquet Catalog
