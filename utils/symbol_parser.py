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


class SymbolParsingError(Exception):
    """符号解析错误"""
    pass


class TimeframeParsingError(Exception):
    """时间周期解析错误"""
    pass


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
    if not input_symbol or not isinstance(input_symbol, str):
        raise SymbolParsingError("Symbol must be a non-empty string")

    input_symbol = input_symbol.strip().upper()

    # 已经是标准 CCXT 格式 (包含 "/")
    if "/" in input_symbol:
        if ":" in input_symbol:
            # BTC/USDT:USDT -> 永续合约
            return input_symbol, "swap"
        else:
            # BTC/USDT -> 现货
            return input_symbol, "spot"

    # 简化格式，需要解析
    if input_symbol.endswith("USDT"):
        # BTCUSDT -> BTC/USDT:USDT
        base = input_symbol[:-4]  # 去掉 USDT
        if len(base) < 2:
            raise SymbolParsingError(f"Invalid symbol format: {input_symbol}")
        ccxt_symbol = f"{base}/USDT:USDT"
        return ccxt_symbol, "swap"

    elif input_symbol.endswith("USD") and not input_symbol.endswith("USDT"):
        # BTCUSD -> BTC/USD:BTC
        base = input_symbol[:-3]  # 去掉 USD
        if len(base) < 2:
            raise SymbolParsingError(f"Invalid symbol format: {input_symbol}")
        ccxt_symbol = f"{base}/USD:{base}"
        return ccxt_symbol, "swap"

    elif input_symbol.endswith("BTC") and len(input_symbol) > 6:
        # ETHBTC -> ETH/BTC (现货)，但是 BTCBTC 这种情况除外
        base = input_symbol[:-3]  # 去掉 BTC
        if len(base) >= 2 and base != "BTC":  # 确保 base 有效且不等于 BTC
            ccxt_symbol = f"{base}/BTC"
            return ccxt_symbol, "spot"
        else:
            # 如果不符合条件，返回原始符号
            return input_symbol, "swap"

    elif input_symbol.endswith("ETH") and len(input_symbol) > 6:
        # LINKETH -> LINK/ETH (现货)，但是 BTCETH、ETHETH 这种情况除外
        base = input_symbol[:-3]  # 去掉 ETH
        if len(base) >= 2 and base not in ["BTC", "ETH"]:  # 确保 base 有效且不是常见基础币
            ccxt_symbol = f"{base}/ETH"
            return ccxt_symbol, "spot"
        else:
            # 对于 BTCETH 这种情况，返回原始符号
            return input_symbol, "swap"

    else:
        # 默认假设是永续合约格式，返回原始符号
        return input_symbol, "swap"


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
    # 对于空值或非字符串，返回默认值
    if not timeframe or not isinstance(timeframe, str):
        return BarAggregation.MINUTE, 1

    timeframe = timeframe.strip().lower()

    # 空字符串返回默认值
    if not timeframe:
        return BarAggregation.MINUTE, 1

    # 根据单位映射到 BarAggregation
    unit_mapping = {
        "m": BarAggregation.MINUTE,
        "h": BarAggregation.HOUR,
        "d": BarAggregation.DAY,
        "w": BarAggregation.WEEK,
    }

    # 处理单字符输入（如 "m", "h", "d", "w"）
    if len(timeframe) == 1:
        unit = timeframe
        if unit == "M":  # 特殊处理大写 M (月份)
            return BarAggregation.MONTH, 1
        elif unit in unit_mapping:
            return unit_mapping[unit], 1
        else:
            # 无效单位，返回默认值
            return BarAggregation.MINUTE, 1

    # 提取单位和周期数
    unit = timeframe[-1]
    period_str = timeframe[:-1]

    try:
        period = int(period_str) if period_str else 1
        if period <= 0:
            # 无效周期，返回默认值
            return BarAggregation.MINUTE, 1
    except ValueError:
        # 无效周期数字，返回默认值
        return BarAggregation.MINUTE, 1

    # 特殊处理大写 M (月份)
    if unit == "M":
        return BarAggregation.MONTH, period

    if unit in unit_mapping:
        return unit_mapping[unit], period
    else:
        # 无效单位，返回默认值
        return BarAggregation.MINUTE, 1


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
        raise TimeframeParsingError(f"Unsupported aggregation for seconds conversion: {aggregation}")

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
        "binance": ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"],
        "okx": ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "2d", "3d", "1w", "1M", "3M"],
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