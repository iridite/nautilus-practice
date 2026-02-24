import gc
import hashlib
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml  # type: ignore[import-untyped]
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
from nautilus_trader.persistence.wranglers import BarDataWrangler
from pandas import DataFrame

from core.exceptions import (
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
from utils.data_file_checker import check_single_data_file
from utils.filename_parser import FilenameParser
from utils.instrument_loader import load_instrument

logger = logging.getLogger(__name__)


# ============================================================
# 数据加载模块
# ============================================================

# ============================================================
# 数据加载模块
# ============================================================


def _extract_symbol_from_instrument_id(inst_id: str) -> str:
    """从instrument_id提取符号"""
    return inst_id.split("-")[0] if "-" in inst_id else inst_id.split(".")[0]


def _build_timeframe_string(cfg: BacktestConfig) -> str:
    """构建时间周期字符串"""
    if not cfg.data_feeds:
        return "1h"

    first_feed = cfg.data_feeds[0]
    from nautilus_trader.model.enums import BarAggregation

    unit_map = {BarAggregation.MINUTE: "m", BarAggregation.HOUR: "h", BarAggregation.DAY: "d"}
    return f"{first_feed.bar_period}{unit_map.get(first_feed.bar_aggregation, 'h')}"


def _check_instrument_data_availability(
    inst_id: str, inst_cfg, cfg: BacktestConfig, base_dir: Path, timeframe: str
) -> bool:
    """检查单个标的的数据可用性"""
    symbol = _extract_symbol_from_instrument_id(inst_id)

    # 确保日期不为 None
    if not cfg.start_date or not cfg.end_date:
        return False

    has_data, _ = check_single_data_file(
        symbol=symbol,
        start_date=cfg.start_date,
        end_date=cfg.end_date,
        timeframe=timeframe,
        exchange=inst_cfg.venue_name.lower(),
        base_dir=base_dir,
    )

    if not has_data:
        logger.debug(f"⏭️ Skipping {inst_id}: no data file")

    return has_data


def _filter_instruments_with_data(
    cfg: BacktestConfig, inst_cfg_map: Dict[str, Any], base_dir: Path
) -> list[str]:
    """过滤有数据的标的"""
    if not cfg.start_date or not cfg.end_date:
        logger.warning("⚠️ start_date 或 end_date 未配置，跳过数据可用性检查")
        return list(inst_cfg_map.keys())

    timeframe = _build_timeframe_string(cfg)
    instruments_with_data = []

    for inst_id, inst_cfg in inst_cfg_map.items():
        if _check_instrument_data_availability(inst_id, inst_cfg, cfg, base_dir, timeframe):
            instruments_with_data.append(inst_id)

    if not instruments_with_data:
        raise InstrumentLoadError("No instruments with available data found", "all")

    logger.info(f"📊 Found {len(instruments_with_data)}/{len(inst_cfg_map)} instruments with data")
    return instruments_with_data


def _load_single_instrument(inst_id: str, inst_cfg) -> Instrument:
    """加载单个标的"""
    inst_path = inst_cfg.get_json_path()

    if not inst_path.exists():
        raise InstrumentLoadError(f"Instrument path not found: {inst_path}", inst_id)

    try:
        return load_instrument(inst_path)
    except Exception as e:
        raise InstrumentLoadError(f"Failed to load instrument {inst_id}: {e}", inst_id, e)


def _load_instruments(cfg: BacktestConfig, base_dir: Path) -> Dict[str, Instrument]:
    """
    加载交易标的信息（带数据可用性检查）

    Args:
        cfg: 回测配置
        base_dir: 项目根目录

    Returns:
        Dict[str, Instrument]: instrument_id -> Instrument 的映射

    Raises:
        InstrumentLoadError: 当标的加载失败时
    """
    inst_cfg_map = {ic.instrument_id: ic for ic in cfg.instruments}

    # 过滤有数据的标的
    instruments_with_data = _filter_instruments_with_data(cfg, inst_cfg_map, base_dir)

    # 加载标的
    loaded_instruments = {}
    for inst_id in instruments_with_data:
        inst_cfg = inst_cfg_map[inst_id]
        loaded_instruments[inst_id] = _load_single_instrument(inst_id, inst_cfg)

    return loaded_instruments


# ============================================================
# 数据验证模块
# ============================================================


def _parse_backtest_time_range(cfg: BacktestConfig) -> Tuple[int, int]:
    """
    解析回测时间范围为纳秒时间戳

    Args:
        cfg: 回测配置

    Returns:
        (start_ns, end_ns): 纳秒时间戳
    """
    from utils.time_helpers import get_ns_timestamp

    start_ns = get_ns_timestamp(cfg.start_date)
    end_ns = get_ns_timestamp(cfg.end_date)

    return start_ns, end_ns


def _calculate_coverage_percentage(
    data_intervals: List[Tuple[int, int]], required_start: int, required_end: int
) -> float:
    """
    计算数据覆盖率

    Args:
        data_intervals: Parquet 数据的时间间隔列表 [(start_ns, end_ns), ...]
        required_start: 回测需要的开始时间（纳秒）
        required_end: 回测需要的结束时间（纳秒）

    Returns:
        覆盖率百分比 (0.0 - 100.0)

    算法：
    1. 计算所需的总时间范围
    2. 对于每个数据间隔，计算与所需范围的交集
    3. 累加所有交集的长度
    4. 覆盖率 = (交集总长度 / 所需总长度) * 100
    """
    if not data_intervals:
        return 0.0

    required_duration = required_end - required_start
    if required_duration <= 0:
        return 0.0

    covered_duration = 0
    for interval_start, interval_end in data_intervals:
        # 计算交集
        overlap_start = max(interval_start, required_start)
        overlap_end = min(interval_end, required_end)

        if overlap_start < overlap_end:
            covered_duration += overlap_end - overlap_start

    coverage_pct = (covered_duration / required_duration) * 100.0
    return min(coverage_pct, 100.0)  # 限制在 100% 以内


def _check_parquet_coverage(
    catalog: ParquetDataCatalog,
    bar_type: BarType,
    cfg: BacktestConfig,
) -> Tuple[bool, float]:
    """
    检查 Parquet 数据覆盖率

    计算 Parquet 数据对回测时间范围的覆盖率，确保数据完整性。

    Args:
        catalog: Parquet 数据目录
        bar_type: Bar 类型标识
        cfg: 回测配置（包含 start_date 和 end_date）

    Returns:
        Tuple[bool, float]: (是否满足要求, 覆盖率百分比)
        - 第一个值：覆盖率是否 >= 95%
        - 第二个值：实际覆盖率百分比

    Examples:
        >>> is_ok, pct = _check_parquet_coverage(catalog, bar_type, cfg)
        >>> if not is_ok:
        ...     logger.warning(f"Coverage insufficient: {pct:.1f}%")
    """
    try:
        # 1. 获取数据间隔
        existing_intervals = catalog.get_intervals(data_cls=Bar, identifier=str(bar_type))
        if not existing_intervals:
            return False, 0.0

        # 2. 解析回测时间范围
        required_start, required_end = _parse_backtest_time_range(cfg)

        # 3. 计算覆盖率
        coverage_pct = _calculate_coverage_percentage(
            existing_intervals, required_start, required_end
        )

        # 4. 判断是否满足要求（阈值 95%）
        COVERAGE_THRESHOLD = 95.0
        is_sufficient = coverage_pct >= COVERAGE_THRESHOLD

        # 5. 记录日志
        if not is_sufficient:
            logger.warning(
                f"\nParquet coverage insufficient for {bar_type}: "
                f"{coverage_pct:.1f}% < {COVERAGE_THRESHOLD}%"
            )
        else:
            logger.debug(f"Parquet coverage OK for {bar_type}: {coverage_pct:.1f}%")

        return is_sufficient, coverage_pct

    except (KeyError, AttributeError) as e:
        logger.warning(f"Failed to check coverage for {bar_type}: {e}")
        return False, 0.0


# ============================================================
# Parquet 数据处理模块
# ============================================================


def _format_status_message(
    feed_idx: int, total_feeds: int, status: str, inst_id: str, extra: str = ""
) -> str:
    """格式化状态消息"""
    return f"\r{status} [{feed_idx:3d}/{total_feeds}] {extra}: {str(inst_id):<32}"


def _update_parquet_from_csv(
    catalog: ParquetDataCatalog,
    csv_path: Path,
    inst: Instrument,
    bar_type: BarType,
    feed_idx: int,
    total_feeds: int,
    action: str,
) -> str:
    """从CSV更新Parquet数据"""
    try:
        catalog_loader(catalog, csv_path, inst, bar_type)
        return _format_status_message(feed_idx, total_feeds, "📖", bar_type.instrument_id, action)
    except (OSError, ValueError) as e:
        logger.warning(f"Failed to {action.lower()} Parquet for {bar_type.instrument_id}: {e}")
        return _format_status_message(
            feed_idx, total_feeds, "⚠️ ", bar_type.instrument_id, "Using Parquet"
        )


def _handle_csv_exists(
    catalog: ParquetDataCatalog,
    csv_path: Path,
    inst: Instrument,
    bar_type: BarType,
    feed_idx: int,
    total_feeds: int,
) -> str:
    """处理CSV文件存在的情况"""
    is_consistent = _verify_data_consistency(csv_path, catalog, bar_type)

    if not is_consistent:
        return _update_parquet_from_csv(
            catalog, csv_path, inst, bar_type, feed_idx, total_feeds, "Updated"
        )
    else:
        return _format_status_message(
            feed_idx, total_feeds, "⏩", bar_type.instrument_id, "Verified"
        )


def _handle_incomplete_parquet(
    catalog: ParquetDataCatalog,
    csv_path: Path,
    inst: Instrument,
    bar_type: BarType,
    data_cfg,
    cfg: BacktestConfig,
    feed_idx: int,
    total_feeds: int,
    coverage_pct: float,
) -> str:
    """处理Parquet数据不完整的情况"""
    download_success = _auto_download_missing_data(data_cfg, cfg)

    if download_success and csv_path.exists():
        return _update_parquet_from_csv(
            catalog, csv_path, inst, bar_type, feed_idx, total_feeds, "Completed"
        )
    else:
        return f"\r⚠️  [{feed_idx:3d}/{total_feeds}] Partial Parquet: {str(bar_type.instrument_id):<25} ({coverage_pct:.1f}%)"


def _handle_csv_missing(
    catalog: ParquetDataCatalog,
    csv_path: Path,
    inst: Instrument,
    bar_type: BarType,
    data_cfg,
    cfg: BacktestConfig,
    feed_idx: int,
    total_feeds: int,
) -> str:
    """处理CSV文件不存在的情况"""
    # 检查Parquet覆盖率
    parquet_exists, coverage_pct = _check_parquet_coverage(catalog, bar_type, cfg)

    if parquet_exists and coverage_pct < 95.0:
        return _handle_incomplete_parquet(
            catalog, csv_path, inst, bar_type, data_cfg, cfg, feed_idx, total_feeds, coverage_pct
        )
    else:
        # 尝试常规下载
        download_success = _auto_download_missing_data(data_cfg, cfg)

        if download_success and csv_path.exists():
            return _update_parquet_from_csv(
                catalog, csv_path, inst, bar_type, feed_idx, total_feeds, "Imported"
            )
        else:
            return f"\r⚠️  [{feed_idx:3d}/{total_feeds}] Partial Parquet: {str(bar_type.instrument_id):<25}"


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
        return _handle_csv_exists(catalog, csv_path, inst, bar_type, feed_idx, total_feeds)
    else:
        return _handle_csv_missing(
            catalog, csv_path, inst, bar_type, data_cfg, cfg, feed_idx, total_feeds
        )


def _import_csv_to_parquet(
    catalog: ParquetDataCatalog,
    csv_path: Path,
    inst: Instrument,
    bar_type: BarType,
    feed_idx: int,
    total_feeds: int,
) -> str:
    """导入CSV到Parquet"""
    catalog_loader(catalog, csv_path, inst, bar_type)
    return f"\r📖 [{feed_idx:3d}/{total_feeds}] Imported: {str(bar_type.instrument_id):<32}"


def _handle_csv_exists_for_missing_parquet(
    catalog: ParquetDataCatalog,
    csv_path: Path,
    inst: Instrument,
    bar_type: BarType,
    data_cfg,
    feed_idx: int,
    total_feeds: int,
) -> str:
    """处理CSV存在但Parquet缺失的情况"""
    try:
        return _import_csv_to_parquet(catalog, csv_path, inst, bar_type, feed_idx, total_feeds)
    except Exception as e:
        raise DataLoadError(f"Error loading {data_cfg.csv_file_name}: {e}", str(csv_path), e)


def _handle_csv_missing_for_missing_parquet(
    catalog: ParquetDataCatalog,
    csv_path: Path,
    inst: Instrument,
    bar_type: BarType,
    data_cfg,
    cfg: BacktestConfig,
    feed_idx: int,
    total_feeds: int,
) -> str:
    """处理CSV和Parquet都缺失的情况"""
    download_success = _auto_download_missing_data(data_cfg, cfg)

    if download_success and csv_path.exists():
        try:
            return _import_csv_to_parquet(catalog, csv_path, inst, bar_type, feed_idx, total_feeds)
        except (OSError, ValueError, KeyError) as e:
            logger.warning(f"Failed to import {bar_type.instrument_id}: {e}")

    # 数据完全缺失
    raise DataLoadError(
        f"Critical data missing for {bar_type.instrument_id}. "
        f"CSV file not found: {csv_path}, Parquet data not available, "
        f"and auto-download failed.",
        str(csv_path),
    )


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
        return _handle_csv_exists_for_missing_parquet(
            catalog, csv_path, inst, bar_type, data_cfg, feed_idx, total_feeds
        )
    else:
        return _handle_csv_missing_for_missing_parquet(
            catalog, csv_path, inst, bar_type, data_cfg, cfg, feed_idx, total_feeds
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
            return bool(csv_path.exists() and csv_path.stat().st_size > 1024)

        return False
    except (IOError, ImportError) as e:
        logger.error(f"Failed to auto-download data: {e}")
        return False


def _process_data_feed(
    feed_idx: int,
    total_feeds: int,
    data_cfg,
    cfg: BacktestConfig,
    loaded_instruments: Dict[str, Instrument],
    _catalog,
) -> Tuple[Optional[str], Optional[str], Optional[str], str]:
    """
    处理单个数据流的导入

    Returns
    -------
    Tuple[Optional[str], Optional[str], Optional[str], str]
        (inst_id, feed_bar_type_str, bar_type_str, status_msg)
    """
    inst_id = data_cfg.instrument_id or (cfg.instrument.instrument_id if cfg.instrument else None)
    if inst_id not in loaded_instruments:
        return None, None, None, ""

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

    return inst_id, feed_bar_type_str, str(bar_type), status_msg


def _categorize_data_feed(
    inst_id: str,
    feed_bar_type_str: str,
    data_cfg,
    global_feeds: Dict,
    feeds_by_inst: Dict,
):
    """将数据流归类到全局或按instrument分类"""
    if data_cfg.label == "benchmark":
        global_feeds[data_cfg.label] = feed_bar_type_str
    else:
        feeds_by_inst[inst_id][data_cfg.label] = feed_bar_type_str


def _update_data_config(
    inst_id_str: str,
    inst,
    bar_type_str: str,
    catalog_path: Path,
    data_config_by_inst: Dict,
):
    """更新instrument的数据配置"""
    if inst_id_str not in data_config_by_inst:
        data_config_by_inst[inst_id_str] = {
            "instrument_id": inst.id,
            "bar_types": [],
            "catalog_path": str(catalog_path),
        }

    if bar_type_str not in data_config_by_inst[inst_id_str]["bar_types"]:
        data_config_by_inst[inst_id_str]["bar_types"].append(bar_type_str)


def _import_data_to_catalog(
    cfg: BacktestConfig,
    loaded_instruments: Dict[str, Instrument],
    catalog_path: Path,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str], Dict[str, Dict[str, str]]]:
    """
    将CSV数据导入Parquet目录，并组织数据流

    智能数据处理：检查Parquet覆盖率，按需导入CSV或下载数据
    """
    _catalog = ParquetDataCatalog(catalog_path)
    data_config_by_inst: Dict[str, Dict[str, Any]] = {}
    feeds_by_inst: Dict[str, Dict[str, str]] = defaultdict(dict)
    global_feeds: Dict[str, str] = {}
    total_feeds = len(cfg.data_feeds)

    for feed_idx, data_cfg in enumerate(cfg.data_feeds, 1):
        inst_id, feed_bar_type_str, bar_type_str, status_msg = _process_data_feed(
            feed_idx, total_feeds, data_cfg, cfg, loaded_instruments, _catalog
        )

        if inst_id is None:
            continue

        sys.stdout.write(status_msg)
        sys.stdout.flush()

        # 归类数据流
        if feed_bar_type_str is not None:
            _categorize_data_feed(inst_id, feed_bar_type_str, data_cfg, global_feeds, feeds_by_inst)

        # 更新数据配置
        inst = loaded_instruments[inst_id]
        if bar_type_str is not None:
            _update_data_config(str(inst.id), inst, bar_type_str, catalog_path, data_config_by_inst)

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
            import os

            for root, dirs, files in os.walk(catalog_root):
                if instrument_id in root and any(f.endswith(".parquet") for f in files):
                    logger.info(f"   🗑️ Clearing found Parquet data: {root}")
                    shutil.rmtree(root)
                    break

    except Exception as e:
        logger.warning(f"   ⚠️ Warning: Could not clear Parquet data: {e}")
        # 不抛出异常，因为这不是致命错误


def _check_csv_file_validity(csv_path: Path) -> bool:
    """检查CSV文件基本有效性"""
    return csv_path.exists() and csv_path.stat().st_size >= 1024


def _get_parquet_intervals(catalog: ParquetDataCatalog, bar_type: BarType) -> list:
    """获取Parquet数据时间间隔"""
    try:
        existing_intervals = catalog.get_intervals(data_cls=Bar, identifier=str(bar_type))
        return existing_intervals if existing_intervals else []
    except (KeyError, AttributeError) as e:
        logger.warning(f"Failed to get intervals in verification: {e}")
        return []


def _get_parquet_mtime(catalog: ParquetDataCatalog, bar_type: BarType) -> float | None:
    """获取Parquet文件的最新修改时间"""
    catalog_root = Path(catalog.path)
    instrument_id = str(bar_type.instrument_id)
    parquet_dir = catalog_root / "data" / "crypto_perpetual" / instrument_id

    if parquet_dir.exists():
        parquet_files = list(parquet_dir.glob("*.parquet"))
        if parquet_files:
            return max(f.stat().st_mtime for f in parquet_files)
    return None


def _check_file_freshness(csv_mtime: float, parquet_mtime: float | None) -> bool:
    """检查文件新鲜度（CSV是否比Parquet新太多）"""
    if parquet_mtime is None:
        return True
    # 如果CSV文件比Parquet文件新超过1小时，认为不一致
    return csv_mtime - parquet_mtime <= 3600


def _count_csv_lines(csv_path: Path) -> int:
    """快速统计CSV行数"""
    try:
        with open(csv_path) as f:
            return sum(1 for _ in f) - 1  # 减去header
    except (IOError, ValueError):
        return 0


def _estimate_parquet_count(existing_intervals: list) -> int:
    """估算Parquet数据量"""
    if not existing_intervals:
        return 0
    interval = existing_intervals[0]
    # 假设1小时数据，估算数据点数量
    return int((interval[1] - interval[0]) // (3600 * 1_000_000_000))  # 纳秒转小时


def _check_data_count_consistency(csv_line_count: int, estimated_parquet_count: int) -> bool:
    """检查数据量一致性（允许20%差异）"""
    if csv_line_count == 0:
        return False
    diff_ratio = abs(csv_line_count - estimated_parquet_count) / max(csv_line_count, 1)
    return diff_ratio <= 0.2


def _calculate_csv_hash(csv_path: Path) -> str:
    """
    计算 CSV 文件的 MD5 哈希值

    使用分块读取以处理大文件，避免内存溢出。

    Args:
        csv_path: CSV 文件路径

    Returns:
        十六进制哈希字符串
    """
    hash_func = hashlib.md5()

    with open(csv_path, "rb") as f:
        while chunk := f.read(8192):  # 8KB 块
            hash_func.update(chunk)

    return hash_func.hexdigest()


def _get_hash_cache_path(catalog: ParquetDataCatalog) -> Path:
    """获取哈希缓存文件路径"""
    catalog_root = Path(catalog.path)
    return catalog_root / ".hash_cache.json"


def _load_hash_cache(cache_path: Path) -> Dict[str, Dict[str, Any]]:
    """加载哈希缓存"""
    if not cache_path.exists():
        return {}

    try:
        with open(cache_path, "r") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to load hash cache: {e}")
        return {}


def _save_hash_cache(cache_path: Path, cache_data: Dict[str, Dict[str, Any]]) -> None:
    """保存哈希缓存"""
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(cache_data, f, indent=2)
    except IOError as e:
        logger.warning(f"Failed to save hash cache: {e}")


def _get_cached_hash(csv_path: Path, catalog: ParquetDataCatalog) -> Optional[str]:
    """从缓存获取 CSV 文件的哈希值"""
    cache_path = _get_hash_cache_path(catalog)
    cache_data = _load_hash_cache(cache_path)

    csv_key = str(csv_path.absolute())
    if csv_key in cache_data:
        return cache_data[csv_key].get("hash")

    return None


def _update_hash_cache(csv_path: Path, csv_hash: str, catalog: ParquetDataCatalog) -> None:
    """更新缓存中的哈希值"""
    cache_path = _get_hash_cache_path(catalog)
    cache_data = _load_hash_cache(cache_path)

    csv_key = str(csv_path.absolute())
    cache_data[csv_key] = {
        "hash": csv_hash,
        "file_size": csv_path.stat().st_size,
        "last_updated": datetime.now().isoformat(),
    }

    _save_hash_cache(cache_path, cache_data)


def _verify_data_consistency(
    csv_path: Path, catalog: ParquetDataCatalog, bar_type: BarType
) -> bool:
    """
    验证 CSV 和 Parquet 数据的一致性（使用哈希校验）

    使用 MD5 哈希值比较 CSV 文件内容，确保 Parquet 数据是从当前 CSV 导入的。

    工作流程：
    1. 检查 CSV 文件和 Parquet 数据是否存在
    2. 计算当前 CSV 文件的哈希值
    3. 从缓存获取上次导入时的哈希值
    4. 比较哈希值判断是否一致

    Args:
        csv_path: CSV 文件路径
        catalog: Parquet 数据目录
        bar_type: 数据类型标识

    Returns:
        bool: 数据是否一致
        - True: CSV 内容未变化，Parquet 数据可用
        - False: CSV 已更新或首次导入，需要重新导入
    """
    try:
        # 1. 检查 CSV 文件基本信息
        if not _check_csv_file_validity(csv_path):
            return False

        # 2. 检查 Parquet 数据是否存在
        existing_intervals = _get_parquet_intervals(catalog, bar_type)
        if not existing_intervals:
            return False

        # 3. 计算当前 CSV 文件哈希
        current_hash = _calculate_csv_hash(csv_path)

        # 4. 从缓存获取上次导入时的哈希
        cached_hash = _get_cached_hash(csv_path, catalog)

        # 5. 比较哈希值
        if cached_hash is None:
            # 首次导入，没有缓存
            logger.debug(f"No cached hash for {csv_path.name}, will import")
            return False

        is_consistent = current_hash == cached_hash

        if not is_consistent:
            logger.info(
                f"CSV data changed for {csv_path.name}: "
                f"hash {cached_hash[:8]}... → {current_hash[:8]}..."
            )
        else:
            logger.debug(f"CSV data unchanged for {csv_path.name}, using cached Parquet")

        return is_consistent

    except (IOError, OSError) as e:
        logger.warning(f"Hash verification failed for {csv_path.name}: {e}")
        # 验证失败时，保守地返回 False，触发重新导入
        return False


# ============================================================
# 策略配置模块
# ============================================================


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


# ============================================================
# 回测执行模块
# ============================================================


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

        # 2. 加载交易标的（带数据可用性检查）
        loaded_instruments = _load_instruments(cfg, base_dir)
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


def _get_venue_name(cfg: BacktestConfig) -> str:
    """获取交易所名称"""
    if cfg.instrument:
        return cfg.instrument.venue_name
    return cfg.data_feeds[0].csv_file_name.split("/")[-1].split("-")[0]


def _load_oms_type_from_config(strategies: List, base_dir: Path) -> str:
    """从策略配置文件加载OMS类型"""
    if not strategies or not hasattr(strategies[0], "config_path"):
        return "HEDGING"

    try:
        config_path = base_dir / strategies[0].config_path
        if config_path.exists():
            with open(config_path, "r") as f:
                strategy_config = yaml.safe_load(f)
                if "parameters" in strategy_config and "oms_type" in strategy_config["parameters"]:
                    return str(strategy_config["parameters"]["oms_type"])
    except (IOError, yaml.YAMLError) as e:
        logger.debug(f"Failed to load OMS type from config, using default: {e}")

    return "HEDGING"


def _create_venue_configs(cfg: BacktestConfig, venue_name: str, oms_type: str) -> List:
    """创建交易所配置"""
    return [
        BacktestVenueConfig(
            name=venue_name,
            oms_type=oms_type,
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


def _create_logging_config(cfg: BacktestConfig, base_dir: Path) -> Optional[LoggingConfig]:
    """创建日志配置"""
    if not cfg.logging:
        return None

    return LoggingConfig(
        log_level=cfg.logging.log_level,
        log_level_file=cfg.logging.log_level_file,
        log_component_levels=cfg.logging.log_component_levels,
        log_components_only=cfg.logging.log_components_only,
        log_directory=str(base_dir / "log" / "backtest" / "high_level"),
    )


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
    venue_name = _get_venue_name(cfg)
    oms_type = _load_oms_type_from_config(strategies, base_dir)
    venue_configs = _create_venue_configs(cfg, venue_name, oms_type)

    # 配置日志
    logging_config = _create_logging_config(cfg, base_dir)

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


# ============================================================
# 自定义数据加载模块
# ============================================================


def _is_custom_data_type(data_type: str) -> bool:
    """检查是否为自定义数据类型"""
    return data_type in ["oi", "funding"]


def _check_dict_dependency(dep: dict) -> bool:
    """检查字典类型的依赖"""
    data_type = dep.get("data_type", "")
    return _is_custom_data_type(data_type)


def _check_object_dependency(dep) -> bool:
    """检查对象类型的依赖"""
    if hasattr(dep, "data_type"):
        return _is_custom_data_type(dep.data_type)
    return False


def _check_strategy_dependencies(strategy: ImportableStrategyConfig) -> bool:
    """检查单个策略的数据依赖"""
    if not (hasattr(strategy, "config") and isinstance(strategy.config, dict)):
        return False

    data_deps = strategy.config.get("data_dependencies", [])
    if not data_deps:
        return False

    for dep in data_deps:
        if isinstance(dep, dict):
            if _check_dict_dependency(dep):
                return True
        elif _check_object_dependency(dep):
            return True

    return False


def _check_if_needs_custom_data(strategies: List[ImportableStrategyConfig]) -> bool:
    """检查策略是否需要自定义数据（OI/Funding）"""
    return any(_check_strategy_dependencies(strategy) for strategy in strategies)


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

    # 注意：高级回测引擎暂不支持 OI/Funding 自定义数据加载
    # 这些数据的加载逻辑主要为低级回测引擎设计
    # 如需使用 OI/Funding 数据，请使用低级回测引擎 (--type low)
    logger.debug("📊 Custom data (OI, Funding Rate) loading skipped in high-level engine")


# ============================================================
# 结果处理模块
# ============================================================


def _process_backtest_results(cfg: BacktestConfig, base_dir: Path, results: List[BacktestResult]):
    """处理回测结果"""
    # 收集策略统计数据
    filter_stats = None
    trade_metrics = None

    try:
        from strategy.keltner_rs_breakout import KeltnerRSBreakoutStrategy

        filter_stats = KeltnerRSBreakoutStrategy.get_filter_stats_summary()
        trade_metrics = KeltnerRSBreakoutStrategy.get_trade_metrics()
        KeltnerRSBreakoutStrategy.print_filter_stats_report()
        KeltnerRSBreakoutStrategy.reset_class_stats()
    except (ImportError, AttributeError):
        pass  # 非Keltner RS Breakout策略时跳过

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


def _build_pnl_metrics(result: BacktestResult) -> Dict[str, Any]:
    """构建PnL指标"""
    pnl_dict = {}
    if result.stats_pnls:
        for currency, metrics in result.stats_pnls.items():
            pnl_dict[str(currency)] = {k: v if v == v else None for k, v in metrics.items()}
    return pnl_dict


def _build_returns_metrics(result: BacktestResult) -> Dict[str, Any]:
    """构建收益率指标"""
    returns_dict = {}
    if result.stats_returns:
        for currency, val in result.stats_returns.items():
            returns_dict[str(currency)] = val if val == val else None
    return returns_dict


def _build_filter_stats(filter_stats: Optional[Dict[str, Dict[str, int]]]) -> Dict[str, Any]:
    """构建过滤器统计"""
    if not filter_stats:
        return {}

    total_stats: Dict[str, Any] = {}
    for inst_id, stats in filter_stats.items():
        for key, value in stats.items():
            total_stats[key] = total_stats.get(key, 0) + value

    signal_checks = total_stats.get("signal_checks", 0)
    all_passed = total_stats.get("all_passed", 0)

    filter_rates = {}
    if signal_checks > 0:
        filter_rates = {
            "pass_rate": (all_passed / signal_checks * 100),
            "filter_rate": ((signal_checks - all_passed) / signal_checks * 100),
        }
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

    return {
        "by_instrument": filter_stats,
        "total": total_stats,
        "rates": filter_rates,
        "instrument_count": len(filter_stats),
    }


def _calculate_basic_stats(
    trade_metrics: List[Dict], winners: List[Dict], losers: List[Dict]
) -> Dict[str, Any]:
    """计算基础统计数据"""
    return {
        "total_trades": len(trade_metrics),
        "winning_trades": len(winners),
        "losing_trades": len(losers),
        "win_rate": len(winners) / len(trade_metrics) if trade_metrics else 0,
    }


def _calculate_pnl_stats(trade_metrics: List[Dict]) -> Dict[str, Any]:
    """计算PnL统计数据"""
    all_pnls = [t.get("pnl_pct", 0) for t in trade_metrics]
    return {
        "total_pnl_pct": sum(all_pnls),
        "avg_pnl_pct": sum(all_pnls) / len(all_pnls) if all_pnls else 0,
        "max_winning_trade": max(all_pnls) if all_pnls else 0,
        "max_losing_trade": min(all_pnls) if all_pnls else 0,
    }


def _calculate_winner_stats(winners: List[Dict]) -> Dict[str, Any]:
    """计算盈利交易统计"""
    if not winners:
        return {}

    winner_pnls = [t.get("pnl_pct", 0) for t in winners]
    return {
        "avg_winning_trade": sum(winner_pnls) / len(winners),
        "avg_winner_rs_score": sum(t.get("entry_rs_score", 0) for t in winners) / len(winners),
        "avg_winner_bb_width_pct": sum(t.get("entry_bb_width_pct", 0) for t in winners)
        / len(winners),
        "avg_winner_volume_mult": sum(t.get("entry_volume_mult", 0) for t in winners)
        / len(winners),
    }


def _calculate_loser_stats(losers: List[Dict]) -> Dict[str, Any]:
    """计算亏损交易统计"""
    if not losers:
        return {}

    loser_pnls = [t.get("pnl_pct", 0) for t in losers]
    return {
        "avg_losing_trade": sum(loser_pnls) / len(losers),
        "avg_loser_rs_score": sum(t.get("entry_rs_score", 0) for t in losers) / len(losers),
        "avg_loser_bb_width_pct": sum(t.get("entry_bb_width_pct", 0) for t in losers) / len(losers),
        "avg_loser_volume_mult": sum(t.get("entry_volume_mult", 0) for t in losers) / len(losers),
    }


def _calculate_profit_ratios(
    winners: List[Dict], losers: List[Dict], analysis: Dict[str, Any]
) -> Dict[str, Any]:
    """计算盈亏比和盈利因子"""
    if not winners or not losers or analysis.get("avg_losing_trade", 0) == 0:
        return {}

    ratios = {
        "profit_loss_ratio": abs(analysis["avg_winning_trade"] / analysis["avg_losing_trade"])
    }

    total_wins = sum([t.get("pnl_pct", 0) for t in winners])
    total_losses = abs(sum([t.get("pnl_pct", 0) for t in losers]))
    if total_losses > 0:
        ratios["profit_factor"] = total_wins / total_losses

    return ratios


def _calculate_trade_analysis(trade_metrics: List[Dict]) -> Dict[str, Any]:
    """计算交易基础分析"""
    winners = [t for t in trade_metrics if t.get("result") == "WINNER"]
    losers = [t for t in trade_metrics if t.get("result") == "LOSER"]

    # 合并所有统计数据
    analysis = {}
    analysis.update(_calculate_basic_stats(trade_metrics, winners, losers))
    analysis.update(_calculate_pnl_stats(trade_metrics))
    analysis.update(_calculate_winner_stats(winners))
    analysis.update(_calculate_loser_stats(losers))
    analysis.update(_calculate_profit_ratios(winners, losers, analysis))

    return analysis


def _build_detailed_analysis(trade_metrics: List[Dict], analysis: Dict[str, Any]) -> Dict[str, Any]:
    """构建详细交易分析"""
    winners = [t for t in trade_metrics if t.get("result") == "WINNER"]
    losers = [t for t in trade_metrics if t.get("result") == "LOSER"]

    if not (winners and losers):
        return {}

    return {
        "winners": {
            "count": len(winners),
            "avg_pnl_pct": analysis.get("avg_winning_trade", 0),
            "avg_rs_score": analysis.get("avg_winner_rs_score", 0),
            "avg_bb_width_pct": analysis.get("avg_winner_bb_width_pct", 0),
            "avg_volume_mult": analysis.get("avg_winner_volume_mult", 0),
        },
        "losers": {
            "count": len(losers),
            "avg_pnl_pct": analysis.get("avg_losing_trade", 0),
            "avg_rs_score": analysis.get("avg_loser_rs_score", 0),
            "avg_bb_width_pct": analysis.get("avg_loser_bb_width_pct", 0),
            "avg_volume_mult": analysis.get("avg_loser_volume_mult", 0),
        },
    }


def _extract_returns_metrics(result: BacktestResult) -> Dict[str, Any]:
    """从stats_returns提取关键指标"""
    metrics: Dict[str, Any] = {}

    if not result.stats_returns:
        return metrics

    for key, val in result.stats_returns.items():
        key_str = str(key)
        # 处理NaN值
        clean_val = val if val == val else None

        if "Sharpe Ratio" in key_str:
            metrics["sharpe_ratio"] = clean_val
        elif "Max Drawdown" in key_str:
            metrics["max_drawdown"] = clean_val
        elif "Total Return" in key_str:
            metrics["total_return"] = clean_val

    return metrics


def _extract_trade_analysis(result_dict: Dict[str, Any]) -> Dict[str, Any]:
    """从trade_metrics提取交易分析数据"""
    analysis = result_dict["trade_metrics"]["analysis"]
    return {
        "win_rate": analysis.get("win_rate", 0),
        "profit_loss_ratio": analysis.get("profit_loss_ratio", 0),
        "avg_winning_trade": analysis.get("avg_winning_trade", 0),
        "avg_losing_trade": analysis.get("avg_losing_trade", 0),
        "total_pnl_pct": analysis.get("total_pnl_pct", 0),
    }


def _extract_filter_statistics(result_dict: Dict[str, Any]) -> Dict[str, Any]:
    """从filter_stats提取过滤器统计数据"""
    filter_data = result_dict["filter_stats"]
    stats = {
        "total_signals": filter_data["total"].get("signal_checks", 0),
        "signals_passed": filter_data["total"].get("all_passed", 0),
    }

    if "rates" in filter_data:
        stats["signal_pass_rate"] = filter_data["rates"].get("pass_rate", 0)

    return stats


def _build_performance_summary(
    result: BacktestResult,
    result_dict: Dict[str, Any],
    trade_metrics: Optional[List[Dict]],
    filter_stats: Optional[Dict[str, Dict[str, int]]],
) -> Dict[str, Any]:
    """构建性能摘要"""
    performance_summary = {
        "total_trades": result.total_positions,
        "total_orders": result.total_orders,
        "elapsed_time_seconds": result.elapsed_time,
    }

    # 添加收益率指标
    performance_summary.update(_extract_returns_metrics(result))

    # 添加交易分析指标
    if trade_metrics:
        performance_summary.update(_extract_trade_analysis(result_dict))

    # 添加过滤器统计
    if filter_stats:
        performance_summary.update(_extract_filter_statistics(result_dict))

    return performance_summary


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
    - trade_metrics: 交易数据
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
        "pnl": _build_pnl_metrics(result),
        "returns": _build_returns_metrics(result),
        "strategy_config": strategy_config or {},
        "backtest_config": backtest_config or {},
        "filter_stats": _build_filter_stats(filter_stats),
        "trade_metrics": {
            "trades": trade_metrics or [],
            "analysis": {},
            "detailed_analysis": {},
        },
        "performance": {},
    }

    if trade_metrics:
        analysis = _calculate_trade_analysis(trade_metrics)
        tm_dict: Dict[str, Any] = result_dict["trade_metrics"]  # type: ignore[assignment]
        tm_dict["analysis"] = analysis
        tm_dict["detailed_analysis"] = _build_detailed_analysis(trade_metrics, analysis)

    result_dict["performance"] = _build_performance_summary(
        result, result_dict, trade_metrics, filter_stats
    )

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


# ============================================================
# 工具函数模块
# ============================================================


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
        pass
    elif "datetime" in sample_df.columns:
        pass
    else:
        raise ValueError(
            f"No valid time column found in {csv_path}. "
            f"Expected 'datetime' or 'timestamp', got: {list(sample_df.columns)}"
        )

    # 2. 高效加载 CSV（使用统一的数据加载器）
    from utils.data_management.data_loader import load_ohlcv_csv

    df: DataFrame = load_ohlcv_csv(csv_path=csv_path)

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

    # 5. 导入成功后，保存 CSV 文件哈希到缓存
    try:
        csv_hash = _calculate_csv_hash(csv_path)
        _update_hash_cache(csv_path, csv_hash, catalog)
        logger.debug(f"Saved hash for {csv_path.name}: {csv_hash[:8]}...")
    except Exception as e:
        logger.warning(f"Failed to save hash for {csv_path.name}: {e}")
        # 不抛出异常，因为这不是致命错误


# 注意：自定义数据（OI, Funding Rate）现在通过 OIFundingDataLoader 直接加载
# 不再需要序列化到 Parquet Catalog
