"""
数据限制检查模块

检查不同交易所的数据可用性限制。
"""

from datetime import datetime, timedelta
from typing import Dict, Tuple

# 交易所数据限制配置
EXCHANGE_DATA_LIMITS: Dict[str, Dict[str, int]] = {
    "binance": {
        "oi": 21,  # Binance OI 数据仅提供最近 21 天
        "funding": 90,  # Funding Rate 数据约 90 天
        "ohlcv": 365 * 3,  # OHLCV 数据约 3 年
    },
    "okx": {
        "oi": 90,  # OKX OI 数据约 90 天
        "funding": 90,  # Funding Rate 数据约 90 天
        "ohlcv": 365 * 3,  # OHLCV 数据约 3 年
    },
}


def check_data_availability(
    start_date: str,
    end_date: str,
    exchange: str,
    data_type: str = "oi",
) -> Tuple[bool, str | None]:
    """
    检查数据是否在交易所限制范围内

    Args:
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        exchange: 交易所名称 (binance/okx)
        data_type: 数据类型 (oi/funding/ohlcv)

    Returns:
        Tuple[bool, str | None]: (是否可用, 警告信息)
    """
    exchange = exchange.lower()
    data_type = data_type.lower()

    if exchange not in EXCHANGE_DATA_LIMITS:
        return True, f"未知交易所 '{exchange}'，无法验证数据限制"

    if data_type not in EXCHANGE_DATA_LIMITS[exchange]:
        return True, f"未知数据类型 '{data_type}'，无法验证数据限制"

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        now = datetime.now()

        # 检查日期范围
        date_range_days = (end_dt - start_dt).days
        max_days = EXCHANGE_DATA_LIMITS[exchange][data_type]

        # 检查是否超过最大范围
        if date_range_days > max_days:
            warning = (
                f"⚠️ 数据范围 {date_range_days} 天超过 {exchange.upper()} "
                f"{data_type.upper()} 数据限制 ({max_days} 天)。\n"
                f"建议：\n"
                f"  1. 缩短日期范围至 {max_days} 天以内\n"
                f"  2. 使用 OKX 交易所（限制更宽松）\n"
                f"  3. 分段获取数据"
            )
            return False, warning

        # 检查结束日期是否太旧
        days_from_now = (now - end_dt).days
        if days_from_now > max_days:
            warning = (
                f"⚠️ 结束日期 {end_date} 距今 {days_from_now} 天，"
                f"超过 {exchange.upper()} {data_type.upper()} 数据保留期限 ({max_days} 天)。\n"
                f"该时间段的数据可能不可用。"
            )
            return False, warning

        return True, None

    except ValueError as e:
        return False, f"日期格式错误: {e}"


def get_recommended_date_range(
    exchange: str,
    data_type: str = "oi",
    days: int | None = None,
) -> Tuple[str, str]:
    """
    获取推荐的日期范围

    Args:
        exchange: 交易所名称
        data_type: 数据类型
        days: 希望的天数（如果超过限制会自动调整）

    Returns:
        Tuple[str, str]: (开始日期, 结束日期)
    """
    exchange = exchange.lower()
    data_type = data_type.lower()

    max_days = EXCHANGE_DATA_LIMITS.get(exchange, {}).get(data_type, 30)

    if days is None or days > max_days:
        days = max_days

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    return (
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d"),
    )


def validate_strategy_data_requirements(
    start_date: str,
    end_date: str,
    exchange: str,
    data_types: list[str],
) -> Dict[str, Tuple[bool, str | None]]:
    """
    验证策略的所有数据需求

    Args:
        start_date: 开始日期
        end_date: 结束日期
        exchange: 交易所
        data_types: 数据类型列表

    Returns:
        Dict[str, Tuple[bool, str | None]]: 每种数据类型的验证结果
    """
    results = {}

    for data_type in data_types:
        is_available, warning = check_data_availability(
            start_date, end_date, exchange, data_type
        )
        results[data_type] = (is_available, warning)

    return results
