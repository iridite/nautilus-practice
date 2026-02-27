"""
数据文件存在性检查模块

提供数据文件验证功能。
"""

from pathlib import Path
from typing import List, Tuple


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
    safe_symbol = symbol.replace("/", "")

    # 首先检查 Parquet 格式（优先级更高）
    # Parquet 路径格式: data/parquet/{strategy_name}/data/bar/{INSTRUMENT_ID}/
    # 文件名格式: {start_date}T00-00-00-000000000Z_{end_date}T00-00-00-000000000Z.parquet
    parquet_dir = base_dir / "data" / "parquet" / strategy_name / "data" / "bar"

    # 构建 instrument_id（格式：SYMBOL-PERP.EXCHANGE-1-DAY-LAST-EXTERNAL）
    instrument_id = f"{safe_symbol}-PERP.{exchange.upper()}-1-DAY-LAST-EXTERNAL"
    parquet_instrument_dir = parquet_dir / instrument_id

    if parquet_instrument_dir.exists():
        # 查找匹配的 parquet 文件
        parquet_files = list(parquet_instrument_dir.glob("*.parquet"))
        if parquet_files:
            # 取第一个文件（通常只有一个）
            parquet_file = parquet_files[0]
            if parquet_file.stat().st_size >= min_size_bytes:
                return True, str(parquet_file)

    # 如果 Parquet 不存在，回退到检查 CSV 格式
    filename = f"{exchange.lower()}-{safe_symbol}-{timeframe}-{start_date}_{end_date}.csv"
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
