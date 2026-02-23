"""
符号解析工具模块

提供统一的交易对符号解析和时间周期转换功能，用于处理不同交易所的符号格式。

功能包括：
- 交易对符号格式解析和转换
- 时间周期格式解析和转换
- 符号标准化和验证
- 市场类型识别
- CCXT 格式与 NautilusTrader 格式转换
"""

from typing import Tuple

from nautilus_trader.model.enums import BarAggregation

from core.exceptions import SymbolParsingError, TimeframeParsingError


def _parse_standard_ccxt_format(symbol: str) -> Tuple[str, str]:
    """解析标准 CCXT 格式 (包含 "/")"""
    if ":" in symbol:
        # BTC/USDT:USDT -> 永续合约
        return symbol, "swap"
    else:
        # BTC/USDT -> 现货
        return symbol, "spot"


def _parse_usdt_suffix(symbol: str) -> Tuple[str, str]:
    """解析 USDT 后缀格式 (BTCUSDT -> BTC/USDT:USDT)"""
    base = symbol[:-4]  # 去掉 USDT
    if len(base) < 2:
        raise SymbolParsingError(f"Invalid symbol format: {symbol}")
    ccxt_symbol = f"{base}/USDT:USDT"
    return ccxt_symbol, "swap"


def _parse_usd_suffix(symbol: str) -> Tuple[str, str]:
    """解析 USD 后缀格式 (BTCUSD -> BTC/USD:BTC)"""
    base = symbol[:-3]  # 去掉 USD
    if len(base) < 2:
        raise SymbolParsingError(f"Invalid symbol format: {symbol}")
    ccxt_symbol = f"{base}/USD:{base}"
    return ccxt_symbol, "swap"


def _parse_btc_suffix(symbol: str) -> Tuple[str, str]:
    """解析 BTC 后缀格式 (ETHBTC -> ETH/BTC)"""
    base = symbol[:-3]  # 去掉 BTC
    if len(base) >= 2 and base != "BTC":  # 确保 base 有效且不等于 BTC
        ccxt_symbol = f"{base}/BTC"
        return ccxt_symbol, "spot"
    else:
        # 如果不符合条件，返回原始符号
        return symbol, "swap"


def _parse_eth_suffix(symbol: str) -> Tuple[str, str]:
    """解析 ETH 后缀格式 (LINKETH -> LINK/ETH)"""
    base = symbol[:-3]  # 去掉 ETH
    if len(base) >= 2 and base not in ["BTC", "ETH"]:  # 确保 base 有效且不是常见基础币
        ccxt_symbol = f"{base}/ETH"
        return ccxt_symbol, "spot"
    else:
        # 对于 BTCETH 这种情况，返回原始符号
        return symbol, "swap"


def _validate_symbol_input(input_symbol: str) -> str:
    """验证并标准化输入符号"""
    if not input_symbol or not isinstance(input_symbol, str):
        raise SymbolParsingError("Symbol must be a non-empty string")
    return input_symbol.strip().upper()


def _parse_simplified_format(symbol: str) -> Tuple[str, str]:
    """解析简化格式的符号（不含"/"）"""
    if symbol.endswith("USDT"):
        return _parse_usdt_suffix(symbol)

    if symbol.endswith("USD"):
        return _parse_usd_suffix(symbol)

    if symbol.endswith("BTC") and len(symbol) > 6:
        return _parse_btc_suffix(symbol)

    if symbol.endswith("ETH") and len(symbol) > 6:
        return _parse_eth_suffix(symbol)

    # 默认假设是永续合约格式
    return symbol, "swap"


def resolve_symbol_and_type(input_symbol: str) -> Tuple[str, str]:
    """
    解析输入的交易对符号，返回 CCXT 统一格式符号和市场类型

    支持多种输入格式：
    - BTCUSDT -> BTC/USDT:USDT (永续合约)
    - BTC/USDT -> BTC/USDT (现货)
    - BTCUSD -> BTC/USD:BTC (合约)

    Parameters
    ----------
    input_symbol : str
        输入的交易对符号

    Returns
    -------
    Tuple[str, str]
        (CCXT统一符号格式, 市场类型)
        市场类型: "spot" 现货, "swap" 永续合约, "future" 期货

    Examples
    --------
    >>> symbol, market_type = resolve_symbol_and_type("BTCUSDT")
    >>> print(symbol, market_type)  # BTC/USDT:USDT swap

    >>> symbol, market_type = resolve_symbol_and_type("BTC/USDT")
    >>> print(symbol, market_type)  # BTC/USDT spot

    Raises
    ------
    SymbolParsingError
        当符号格式无法识别时
    """
    normalized_symbol = _validate_symbol_input(input_symbol)

    # 已经是标准 CCXT 格式 (包含 "/")
    if "/" in normalized_symbol:
        return _parse_standard_ccxt_format(normalized_symbol)

    # 简化格式，需要解析
    return _parse_simplified_format(normalized_symbol)


def _get_unit_mapping() -> dict:
    """获取时间单位映射"""
    return {
        "m": BarAggregation.MINUTE,
        "h": BarAggregation.HOUR,
        "d": BarAggregation.DAY,
        "w": BarAggregation.WEEK,
    }


def _validate_timeframe_input(timeframe: str) -> str | None:
    """验证并标准化时间周期输入"""
    if not timeframe or not isinstance(timeframe, str):
        return None

    timeframe = timeframe.strip().lower()
    if not timeframe:
        return None

    return timeframe


def _parse_single_char_timeframe(timeframe: str) -> Tuple[BarAggregation, int] | None:
    """解析单字符时间周期（如 'm', 'h', 'd', 'w', 'M'）"""
    if len(timeframe) != 1:
        return None

    unit = timeframe
    if unit == "M":  # 特殊处理大写 M (月份)
        return BarAggregation.MONTH, 1

    unit_mapping = _get_unit_mapping()
    if unit in unit_mapping:
        return unit_mapping[unit], 1

    return None


def _extract_period_and_unit(timeframe: str) -> Tuple[int, str] | None:
    """提取周期数和单位"""
    unit = timeframe[-1]
    period_str = timeframe[:-1]

    try:
        period = int(period_str) if period_str else 1
        if period <= 0:
            return None
        return period, unit
    except ValueError:
        return None


def _map_unit_to_aggregation(unit: str, period: int) -> Tuple[BarAggregation, int] | None:
    """将单位映射到BarAggregation"""
    if unit == "M":  # 特殊处理大写 M (月份)
        return BarAggregation.MONTH, period

    unit_mapping = _get_unit_mapping()
    if unit in unit_mapping:
        return unit_mapping[unit], period

    return None


def parse_timeframe(timeframe: str) -> Tuple[BarAggregation, int]:
    """
    将 CCXT 时间周期格式转换为 NautilusTrader BarAggregation 和周期数

    支持的格式：
    - 分钟: 1m, 5m, 15m, 30m, m (单字符默认为1)
    - 小时: 1h, 2h, 4h, 6h, 12h, h (单字符默认为1)
    - 天数: 1d, 3d, 7d, d (单字符默认为1)
    - 周数: 1w, w (单字符默认为1)
    - 月份: 1M, M (单字符默认为1)

    对于无效输入，返回默认值 (BarAggregation.MINUTE, 1)

    Parameters
    ----------
    timeframe : str
        CCXT 格式的时间周期字符串

    Returns
    -------
    Tuple[BarAggregation, int]
        (NautilusTrader BarAggregation 枚举, 周期数)

    Examples
    --------
    >>> aggregation, period = parse_timeframe("5m")
    >>> print(aggregation, period)  # BarAggregation.MINUTE 5

    >>> aggregation, period = parse_timeframe("m")
    >>> print(aggregation, period)  # BarAggregation.MINUTE 1

    >>> aggregation, period = parse_timeframe("invalid")
    >>> print(aggregation, period)  # BarAggregation.MINUTE 1 (默认值)
    """
    # 默认返回值
    default_result = (BarAggregation.MINUTE, 1)

    # 验证输入
    timeframe = _validate_timeframe_input(timeframe)
    if timeframe is None:
        return default_result

    # 处理单字符输入
    result = _parse_single_char_timeframe(timeframe)
    if result is not None:
        return result

    # 提取周期数和单位
    extracted = _extract_period_and_unit(timeframe)
    if extracted is None:
        return default_result

    period, unit = extracted

    # 映射单位到BarAggregation
    result = _map_unit_to_aggregation(unit, period)
    if result is None:
        return default_result

    return result


def normalize_symbol(symbol: str, exchange: str = "binance") -> str:
    """
    标准化交易对符号为指定交易所格式

    Parameters
    ----------
    symbol : str
        输入的交易对符号
    exchange : str, optional
        目标交易所名称，默认 "binance"

    Returns
    -------
    str
        标准化后的符号

    Examples
    --------
    >>> normalized = normalize_symbol("BTC/USDT:USDT", "binance")
    >>> print(normalized)  # BTCUSDT

    >>> normalized = normalize_symbol("BTCUSDT", "okx")
    >>> print(normalized)  # BTC-USDT-SWAP
    """
    ccxt_symbol, market_type = resolve_symbol_and_type(symbol)

    if exchange.lower() == "binance":
        if market_type == "spot":
            # BTC/USDT -> BTCUSDT
            return ccxt_symbol.replace("/", "")
        elif market_type == "swap":
            # BTC/USDT:USDT -> BTCUSDT
            return ccxt_symbol.split("/")[0] + ccxt_symbol.split("/")[1].split(":")[0]
        else:
            return ccxt_symbol.replace("/", "")

    elif exchange.lower() == "okx":
        if market_type == "spot":
            # BTC/USDT -> BTC-USDT
            return ccxt_symbol.replace("/", "-")
        elif market_type == "swap":
            # BTC/USDT:USDT -> BTC-USDT-SWAP
            base_quote = ccxt_symbol.split(":")[0].replace("/", "-")
            return f"{base_quote}-SWAP"
        else:
            return ccxt_symbol.replace("/", "-")

    else:
        # 默认返回 CCXT 格式
        return ccxt_symbol


def extract_base_quote(symbol: str) -> Tuple[str, str]:
    """
    从交易对符号中提取基础货币和计价货币

    Parameters
    ----------
    symbol : str
        交易对符号

    Returns
    -------
    Tuple[str, str]
        (基础货币, 计价货币)

    Examples
    --------
    >>> base, quote = extract_base_quote("BTCUSDT")
    >>> print(base, quote)  # BTC USDT

    >>> base, quote = extract_base_quote("BTC/USDT:USDT")
    >>> print(base, quote)  # BTC USDT
    """
    ccxt_symbol, _ = resolve_symbol_and_type(symbol)

    # 处理 CCXT 格式
    if ":" in ccxt_symbol:
        # BTC/USDT:USDT -> BTC, USDT
        base_quote_part = ccxt_symbol.split(":")[0]
    else:
        # BTC/USDT -> BTC, USDT
        base_quote_part = ccxt_symbol

    if "/" in base_quote_part:
        base, quote = base_quote_part.split("/", 1)
        return base.strip(), quote.strip()
    else:
        raise SymbolParsingError(f"Cannot extract base/quote from symbol: {symbol}")


def is_perpetual_contract(symbol: str) -> bool:
    """
    判断交易对是否为永续合约

    Parameters
    ----------
    symbol : str
        交易对符号

    Returns
    -------
    bool
        是否为永续合约

    Examples
    --------
    >>> is_perpetual_contract("BTCUSDT")
    True
    >>> is_perpetual_contract("BTC/USDT")
    False
    """
    try:
        _, market_type = resolve_symbol_and_type(symbol)
        return market_type == "swap"
    except SymbolParsingError:
        return False


def convert_timeframe_to_seconds(timeframe: str) -> int:
    """
    将时间周期转换为秒数

    Parameters
    ----------
    timeframe : str
        时间周期字符串

    Returns
    -------
    int
        对应的秒数

    Examples
    --------
    >>> seconds = convert_timeframe_to_seconds("5m")
    >>> print(seconds)  # 300

    >>> seconds = convert_timeframe_to_seconds("1h")
    >>> print(seconds)  # 3600
    """
    aggregation, period = parse_timeframe(timeframe)

    # 基础秒数映射
    base_seconds = {
        BarAggregation.MINUTE: 60,
        BarAggregation.HOUR: 3600,
        BarAggregation.DAY: 86400,
        BarAggregation.WEEK: 604800,
        BarAggregation.MONTH: 2592000,  # 30天近似
    }

    if aggregation not in base_seconds:
        raise TimeframeParsingError(
            f"Unsupported aggregation for seconds conversion: {aggregation}"
        )

    return base_seconds[aggregation] * period


def convert_nautilus_to_ccxt_timeframe(aggregation: BarAggregation, period: int) -> str:
    """
    将 NautilusTrader BarAggregation 转换为 CCXT 时间周期格式

    Parameters
    ----------
    aggregation : BarAggregation
        NautilusTrader BarAggregation 枚举
    period : int
        周期数

    Returns
    -------
    str
        CCXT 格式的时间周期字符串

    Examples
    --------
    >>> timeframe = convert_nautilus_to_ccxt_timeframe(BarAggregation.MINUTE, 5)
    >>> print(timeframe)  # 5m

    >>> timeframe = convert_nautilus_to_ccxt_timeframe(BarAggregation.HOUR, 1)
    >>> print(timeframe)  # 1h
    """
    unit_mapping = {
        BarAggregation.MINUTE: "m",
        BarAggregation.HOUR: "h",
        BarAggregation.DAY: "d",
        BarAggregation.WEEK: "w",
        BarAggregation.MONTH: "M",
    }

    if aggregation not in unit_mapping:
        raise TimeframeParsingError(f"Unsupported aggregation: {aggregation}")

    return f"{period}{unit_mapping[aggregation]}"


def get_supported_timeframes(exchange: str) -> list[str]:
    """
    获取指定交易所支持的时间周期列表

    Parameters
    ----------
    exchange : str
        交易所名称

    Returns
    -------
    list[str]
        支持的时间周期列表

    Examples
    --------
    >>> timeframes = get_supported_timeframes("binance")
    >>> print(timeframes)  # ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M']
    """
    # 常见交易所支持的时间周期
    exchange_timeframes = {
        "binance": [
            "1m",
            "3m",
            "5m",
            "15m",
            "30m",
            "1h",
            "2h",
            "4h",
            "6h",
            "8h",
            "12h",
            "1d",
            "3d",
            "1w",
            "1M",
        ],
        "okx": [
            "1m",
            "3m",
            "5m",
            "15m",
            "30m",
            "1h",
            "2h",
            "4h",
            "6h",
            "12h",
            "1d",
            "2d",
            "3d",
            "1w",
            "1M",
            "3M",
        ],
        "bybit": ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w", "1M"],
        "huobi": ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"],
    }

    exchange_key = exchange.lower()
    if exchange_key in exchange_timeframes:
        return exchange_timeframes[exchange_key].copy()
    else:
        # 默认返回通用支持的时间周期
        return ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]


def validate_symbol_for_exchange(symbol: str, exchange: str) -> Tuple[bool, str | None]:
    """
    验证交易对符号是否适用于指定交易所

    Parameters
    ----------
    symbol : str
        交易对符号
    exchange : str
        交易所名称

    Returns
    -------
    Tuple[bool, str | None]
        (是否有效, 错误信息)
    """
    try:
        ccxt_symbol, market_type = resolve_symbol_and_type(symbol)
        base, quote = extract_base_quote(symbol)

        # 基本格式检查
        if len(base) < 2 or len(quote) < 2:
            return (False, f"Invalid base ({base}) or quote ({quote}) currency")

        # 特定交易所的规则检查
        exchange_lower = exchange.lower()

        if exchange_lower == "binance":
            # Binance 不支持某些特殊符号
            if any(char in base + quote for char in ["-", "_", "."]):
                return (False, f"Binance does not support special characters in symbol: {symbol}")

        elif exchange_lower == "okx":
            # OKX 的一些特定规则
            pass

        return (True, None)

    except SymbolParsingError as e:
        return (False, str(e))
