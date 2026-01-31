"""
时间处理工具模块

提供统一的时间转换、格式化和解析功能，支持多种时间戳格式。
用于量化交易项目中的时间数据处理。

功能包括：
- 日期字符串转换为毫秒/纳秒时间戳
- 时间戳格式化输出
- 日期范围解析和验证
- 时区处理工具
"""

from datetime import datetime, timezone
from typing import Tuple

import pandas as pd
from nautilus_trader.core.nautilus_pyo3 import millis_to_nanos


def get_ms_timestamp(date_str: str) -> int:
    """
    将 YYYY-MM-DD 格式的日期字符串转换为毫秒级时间戳 (UTC)

    Parameters
    ----------
    date_str : str
        日期字符串，格式为 "YYYY-MM-DD"

    Returns
    -------
    int
        UTC毫秒级时间戳

    Examples
    --------
    >>> get_ms_timestamp("2024-01-01")
    1704067200000

    Raises
    ------
    ValueError
        当日期字符串格式不正确时
    """
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except ValueError as e:
        raise ValueError(f"Invalid date format '{date_str}'. Expected YYYY-MM-DD format.") from e


def get_ns_timestamp(date_str: str) -> int:
    """
    将 YYYY-MM-DD 格式的日期字符串转换为纳秒级时间戳 (UTC)

    Parameters
    ----------
    date_str : str
        日期字符串，格式为 "YYYY-MM-DD"

    Returns
    -------
    int
        UTC纳秒级时间戳

    Examples
    --------
    >>> get_ns_timestamp("2024-01-01")
    1704067200000000000
    """
    ms_timestamp = get_ms_timestamp(date_str)
    return millis_to_nanos(ms_timestamp)


def format_timestamp(timestamp: int, format_str: str = "%Y-%m-%d %H:%M:%S", is_ms: bool = True) -> str:
    """
    将时间戳格式化为字符串

    Parameters
    ----------
    timestamp : int
        时间戳（毫秒或纳秒）
    format_str : str, optional
        输出格式字符串，默认 "%Y-%m-%d %H:%M:%S"
    is_ms : bool, optional
        是否为毫秒时间戳，默认 True。False 表示纳秒时间戳

    Returns
    -------
    str
        格式化后的时间字符串

    Examples
    --------
    >>> format_timestamp(1704067200000)
    "2024-01-01 00:00:00"
    """
    if is_ms:
        dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
    else:
        dt = datetime.fromtimestamp(timestamp / 1_000_000_000, tz=timezone.utc)
    return dt.strftime(format_str)


def parse_date_to_timestamp(date_str: str, tz_aware: bool = False) -> pd.Timestamp:
    """
    将日期字符串转换为 pandas Timestamp 对象

    Parameters
    ----------
    date_str : str
        日期字符串（YYYY-MM-DD 格式）
    tz_aware : bool, optional
        是否保留时区信息，默认 False（移除时区）

    Returns
    -------
    pd.Timestamp
        pandas Timestamp 对象

    Examples
    --------
    >>> ts = parse_date_to_timestamp("2024-01-01")
    >>> ts = parse_date_to_timestamp("2024-01-01", tz_aware=True)
    """
    ts = pd.Timestamp(date_str)
    if not tz_aware and ts.tz is not None:
        ts = ts.tz_localize(None)
    return ts


def parse_datetime_range(start_date: str, end_date: str) -> Tuple[pd.Timestamp, pd.Timestamp]:
    """
    解析日期范围，返回 pandas Timestamp 对象

    Parameters
    ----------
    start_date : str
        开始日期字符串 (YYYY-MM-DD)
    end_date : str
        结束日期字符串 (YYYY-MM-DD)

    Returns
    -------
    Tuple[pd.Timestamp, pd.Timestamp]
        开始和结束时间的 pandas Timestamp 对象（UTC时区）

    Raises
    ------
    ValueError
        当开始日期晚于结束日期时

    Examples
    --------
    >>> start_ts, end_ts = parse_datetime_range("2024-01-01", "2024-01-31")
    """
    start_ts = pd.Timestamp(start_date).tz_localize('UTC')
    end_ts = pd.Timestamp(end_date).tz_localize('UTC')

    if start_ts > end_ts:
        raise ValueError(f"Start date ({start_date}) cannot be later than end date ({end_date})")

    return start_ts, end_ts


def validate_date_string(date_str: str, date_format: str = "%Y-%m-%d") -> bool:
    """
    验证日期字符串格式是否正确

    Parameters
    ----------
    date_str : str
        待验证的日期字符串
    date_format : str, optional
        期望的日期格式，默认 "%Y-%m-%d"

    Returns
    -------
    bool
        如果格式正确返回 True，否则返回 False

    Examples
    --------
    >>> validate_date_string("2024-01-01")
    True
    >>> validate_date_string("01/01/2024")
    False
    """
    try:
        datetime.strptime(date_str, date_format)
        return True
    except ValueError:
        return False


def normalize_timestamp_to_utc(timestamp: int, is_ms: bool = True) -> int:
    """
    将时间戳标准化为UTC时间戳

    Parameters
    ----------
    timestamp : int
        输入时间戳
    is_ms : bool, optional
        是否为毫秒时间戳，默认 True

    Returns
    -------
    int
        UTC时间戳（保持原格式）

    Note
    ----
    这个函数主要用于确保时间戳是UTC格式，避免时区问题
    """
    if is_ms:
        dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
        return int(dt.timestamp() * 1000)
    else:
        dt = datetime.fromtimestamp(timestamp / 1_000_000_000, tz=timezone.utc)
        return int(dt.timestamp() * 1_000_000_000)
