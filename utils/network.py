"""
网络工具模块

提供统一的网络请求重试机制，用于处理与交易所API的网络交互。
"""

import time
from typing import Any, Callable, Tuple, Type

import ccxt


def retry_fetch(
    func: Callable,
    *args,
    retries: int = 3,
    delay: float = 5.0,
    backoff_factor: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (ccxt.NetworkError, ccxt.ExchangeError),
    **kwargs
) -> Any:
    """
    带重试机制的函数调用包装器

    提供智能的重试策略，针对不同类型的网络错误使用不同的延迟时间。

    Parameters
    ----------
    func : Callable
        要执行的函数
    *args
        传递给函数的位置参数
    retries : int, optional
        最大重试次数，默认 3
    delay : float, optional
        基础延迟时间（秒），默认 5.0
    backoff_factor : float, optional
        指数退避因子，默认 2.0
    exceptions : Tuple[Type[Exception], ...], optional
        要捕获并重试的异常类型，默认 (ccxt.NetworkError, ccxt.ExchangeError)
    **kwargs
        传递给函数的关键字参数

    Returns
    -------
    Any
        函数执行结果

    Raises
    ------
    Exception
        当重试次数耗尽后，抛出最后一次的异常

    Examples
    --------
    >>> def fetch_data():
    ...     return exchange.fetch_ohlcv("BTC/USDT")
    >>> data = retry_fetch(fetch_data, retries=5, delay=2.0)

    >>> # 直接调用带参数的函数
    >>> data = retry_fetch(exchange.fetch_ohlcv, "BTC/USDT", "1h")
    """
    last_exception = None
    max_attempts = max(1, retries)  # 至少执行一次

    for attempt in range(1, max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except exceptions as e:
            last_exception = e
            err_msg = str(e).lower()

            # 计算延迟时间
            current_delay = delay

            # 针对特定错误类型调整延迟
            if any(code in err_msg for code in ["418", "-1003", "rate limit", "too many requests"]):
                # API限流错误，使用更长的延迟
                current_delay = delay * backoff_factor * 2
            elif any(code in err_msg for code in ["timeout", "connection", "network"]):
                # 网络连接错误，使用指数退避
                current_delay = delay * (backoff_factor ** (attempt - 1))

            if attempt == max_attempts:
                # 最后一次尝试失败，抛出异常
                raise last_exception

            # 等待后重试
            time.sleep(current_delay)

    # 理论上不会到达这里，但为了类型检查器
    if last_exception:
        raise last_exception
    return None
