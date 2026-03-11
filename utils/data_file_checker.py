"""
数据文件存在性检查模块

提供数据文件验证功能。
"""

import re
from pathlib import Path
from typing import List, Tuple

from utils.instrument_helpers import normalize_symbol_to_internal


def _normalize_symbol_for_storage(symbol: str) -> str:
    """标准化 symbol，匹配 data/raw 与 parquet 目录命名。"""
    raw = (symbol or "").strip()
    if ":" in raw:
        raw = raw.split(":", 1)[0]
    if "." in raw:
        raw = raw.split(".", 1)[0]
    raw = raw.replace("/", "")

    try:
        return normalize_symbol_to_internal(raw)
    except Exception:
        # 回退：去掉常见永续后缀
        return raw.upper().replace("-PERP", "").replace("-SWAP", "")


def _normalize_timeframe_for_filename(timeframe: str) -> str:
    """将 1-DAY / 4-HOUR 等格式统一为 1d / 4h。"""
    tf = (timeframe or "").strip().lower()
    if not tf:
        return "1h"

    if "-" not in tf and tf[-1:] in {"m", "h", "d"}:
        return tf

    if "-" in tf:
        parts = [p for p in tf.split("-") if p]
        if len(parts) >= 2 and parts[0].isdigit():
            unit_map = {"minute": "m", "hour": "h", "day": "d"}
            unit = unit_map.get(parts[1])
            if unit:
                return f"{parts[0]}{unit}"

    return tf


def _find_matching_parquet_file(
    base_dir: Path, strategy_name: str, symbol: str, exchange: str, min_size_bytes: int
) -> str | None:
    """在新旧 parquet 目录结构中查找匹配文件。"""
    parquet_root = base_dir / "data" / "parquet" / strategy_name / "data"
    if not parquet_root.exists():
        return None

    symbol_key = re.sub(r"[^A-Z0-9]", "", symbol.upper())
    exchange_key = exchange.upper()

    # 兼容新结构: data/*/{INSTRUMENT_ID}/
    # 兼容旧结构: data/bar/{INSTRUMENT_ID-BAR_TYPE}/
    candidate_dirs = [p for p in parquet_root.glob("*/*") if p.is_dir()]

    matched_files: list[Path] = []
    for inst_dir in candidate_dirs:
        inst_name = inst_dir.name.upper()
        if exchange_key not in inst_name:
            continue

        inst_comp = re.sub(r"[^A-Z0-9]", "", inst_name)
        if symbol_key not in inst_comp:
            continue

        for parquet_file in inst_dir.glob("*.parquet"):
            if parquet_file.stat().st_size >= min_size_bytes:
                matched_files.append(parquet_file)

    if not matched_files:
        return None

    # 优先返回最近修改的文件，减少命中过期归档的概率。
    matched_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return str(matched_files[0])


def check_single_data_file(
    symbol: str,
    start_date: str,
    end_date: str,
    timeframe: str,
    exchange: str,
    base_dir: Path,
    min_size_bytes: int = 1 * 1024,  # 降低到 1KB，支持新币种短历史数据
    strategy_name: str = "KeltnerRSBreakoutStrategy",
) -> Tuple[bool, str]:
    """
    检查单个交易对的数据文件是否存在（支持 CSV 和 Parquet 格式）

    Args:
        symbol: 交易对符号
        start_date: 开始日期
        end_date: 结束日期
        timeframe: 时间周期
        exchange: 交易所
        base_dir: 基础目录
        min_size_bytes: 最小文件大小
        strategy_name: 策略名称（用于 Parquet 路径）

    Returns:
        Tuple[bool, str]: (是否存在, 文件路径)
    """
    safe_symbol = _normalize_symbol_for_storage(symbol)
    normalized_timeframe = _normalize_timeframe_for_filename(timeframe)

    # 首先检查 Parquet 格式（优先级更高）
    parquet_path = _find_matching_parquet_file(
        base_dir=base_dir,
        strategy_name=strategy_name,
        symbol=safe_symbol,
        exchange=exchange,
        min_size_bytes=min_size_bytes,
    )
    if parquet_path:
        return True, parquet_path

    # 如果 Parquet 不存在，回退到检查 CSV 格式
    filename = (
        f"{exchange.lower()}-{safe_symbol}-{normalized_timeframe}-{start_date}_{end_date}.csv"
    )
    filepath = base_dir / "data" / "raw" / safe_symbol / filename

    if not filepath.exists():
        return False, str(filepath)

    if filepath.stat().st_size < min_size_bytes:
        return False, str(filepath)

    return True, str(filepath)


def check_oi_data_exists(
    symbols: List[str], start_date: str, end_date: str, period: str, exchange: str, base_dir: Path
) -> Tuple[bool, List[str]]:
    """
    检查 OI 数据文件是否存在

    Args:
        symbols: 交易对列表
        start_date: 开始日期
        end_date: 结束日期
        period: 时间周期
        exchange: 交易所
        base_dir: 基础目录

    Returns:
        Tuple[bool, List[str]]: (全部存在, 缺失文件列表)
    """
    missing = []

    for symbol in symbols:
        safe_symbol = symbol.replace("/", "")
        filename = f"{exchange.lower()}-{safe_symbol}-oi-{period}-{start_date}_{end_date}.csv"
        filepath = base_dir / "data" / "raw" / safe_symbol / filename

        if not filepath.exists() or filepath.stat().st_size < 1024:
            missing.append(str(filepath))

    return len(missing) == 0, missing


def check_funding_data_exists(
    symbols: List[str], start_date: str, end_date: str, exchange: str, base_dir: Path
) -> Tuple[bool, List[str]]:
    """
    检查 Funding Rate 数据文件是否存在

    Args:
        symbols: 交易对列表
        start_date: 开始日期
        end_date: 结束日期
        exchange: 交易所
        base_dir: 基础目录

    Returns:
        Tuple[bool, List[str]]: (全部存在, 缺失文件列表)
    """
    missing = []

    for symbol in symbols:
        safe_symbol = symbol.replace("/", "")
        filename = f"{exchange.lower()}-{safe_symbol}-funding-{start_date}_{end_date}.csv"
        filepath = base_dir / "data" / "raw" / safe_symbol / filename

        if not filepath.exists() or filepath.stat().st_size < 1024:
            missing.append(str(filepath))

    return len(missing) == 0, missing
