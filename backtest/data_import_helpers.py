"""
Data import helper functions for backtest engine

Extracted from engine_high.py to improve maintainability
"""

from pathlib import Path
from typing import Optional, Tuple

from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from backtest.exceptions import DataLoadError
from core.models import BackTestConfig
from utils.filename_parser import FilenameParser


def check_parquet_coverage(
    catalog: ParquetDataCatalog,
    bar_type: BarType,
    cfg: BackTestConfig,
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

    from utils.validation import check_parquet_data_coverage

    symbol_str = str(bar_type.instrument_id).split("-")[0]
    _, _, stats = check_parquet_data_coverage(
        symbol_str,
        cfg.start_date,
        cfg.end_date,
        "1h",
        "binance",
        Path(__file__).parent.parent,
        "RSSqueezeStrategy",
    )

    return True, stats.get("coverage_percentage", 0.0)


def handle_parquet_exists(
    catalog: ParquetDataCatalog,
    csv_path: Path,
    inst: Instrument,
    bar_type: BarType,
    data_cfg,
    cfg: BackTestConfig,
    feed_idx: int,
    total_feeds: int,
) -> str:
    """
    处理Parquet数据已存在的情况

    Returns:
        str: 状态消息（用于日志）
    """
    from backtest.engine_high import (
        _auto_download_missing_data,
        _verify_data_consistency,
        catalog_loader,
    )

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
        parquet_exists, coverage_pct = check_parquet_coverage(catalog, bar_type, cfg)

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


def handle_parquet_missing(
    catalog: ParquetDataCatalog,
    csv_path: Path,
    inst: Instrument,
    bar_type: BarType,
    data_cfg,
    cfg: BackTestConfig,
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
    from backtest.engine_high import _auto_download_missing_data, catalog_loader

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


def auto_download_data(data_cfg, cfg: BackTestConfig) -> bool:
    """
    自动下载缺失的数据文件

    Returns:
        bool: 下载是否成功
    """
    try:
        from utils.data_retrival import batch_fetch_ohlcv

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
