"""
网络工具模块

提供统一的网络请求重试机制和相关工具函数，主要用于处理与交易所API的网络交互。

功能包括：
- 带重试机制的函数调用包装器
- 网络错误分类和处理
- API限流和延迟处理
- 网络状态检测工具
"""

import time
from typing import Any, Callable, Type, Tuple
from functools import wraps

import ccxt


class NetworkError(Exception):
    """网络相关错误的基类"""
    pass


class RateLimitError(NetworkError):
    """API限流错误"""
    pass


class ConnectionError(NetworkError):
    """连接错误"""
    pass


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


def retry_on_error(
    retries: int = 3,
    delay: float = 5.0,
    exceptions: Tuple[Type[Exception], ...] = (ccxt.NetworkError, ccxt.ExchangeError)
):
    """
    装饰器版本的重试机制
    
    Parameters
    ----------
    retries : int, optional
        最大重试次数，默认 3
    delay : float, optional
        基础延迟时间（秒），默认 5.0
    exceptions : Tuple[Type[Exception], ...], optional
        要捕获并重试的异常类型
        
    Returns
    -------
    Callable
        装饰后的函数
        
    Examples
    --------
    >>> @retry_on_error(retries=5, delay=2.0)
    ... def fetch_market_data():
    ...     return exchange.fetch_ticker("BTC/USDT")
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return retry_fetch(func, *args, retries=retries, delay=delay, exceptions=exceptions, **kwargs)
        return wrapper
    return decorator


def safe_sleep(duration: float, min_sleep: float = 0.1) -> None:
    """
    安全的睡眠函数，确保最小睡眠时间
    
    Parameters
    ----------
    duration : float
        睡眠时长（秒）
    min_sleep : float, optional
        最小睡眠时长（秒），默认 0.1
        
    Examples
    --------
    >>> safe_sleep(0.05)  # 实际睡眠 0.1 秒
    >>> safe_sleep(2.5)   # 睡眠 2.5 秒
    """
    sleep_time = max(duration, min_sleep)
    time.sleep(sleep_time)


def calculate_rate_limit_delay(exchange: ccxt.Exchange, safety_factor: float = 1.2) -> float:
    """
    计算基于交易所限流的延迟时间
    
    Parameters
    ----------
    exchange : ccxt.Exchange
        CCXT交易所实例
    safety_factor : float, optional
        安全系数，默认 1.2（比官方限制多20%的延迟）
        
    Returns
    -------
    float
        建议的延迟时间（秒）
        
    Examples
    --------
    >>> exchange = ccxt.binance()
    >>> delay = calculate_rate_limit_delay(exchange)
    >>> time.sleep(delay)
    """
    if hasattr(exchange, 'rateLimit') and exchange.rateLimit:
        # rateLimit 通常以毫秒为单位
        base_delay = exchange.rateLimit / 1000.0
        return base_delay * safety_factor
    else:
        # 默认延迟
        return 1.0


def is_rate_limit_error(error: Exception) -> bool:
    """
    判断是否为API限流错误
    
    Parameters
    ----------
    error : Exception
        要检查的异常
        
    Returns
    -------
    bool
        如果是限流错误返回 True，否则 False
        
    Examples
    --------
    >>> try:
    ...     exchange.fetch_ticker("BTC/USDT")
    ... except Exception as e:
    ...     if is_rate_limit_error(e):
    ...         print("遇到限流，需要等待")
    """
    error_msg = str(error).lower()
    rate_limit_indicators = [
        "rate limit", "too many requests", "418", "-1003",
        "request weight", "too frequent", "exceeded"
    ]
    return any(indicator in error_msg for indicator in rate_limit_indicators)


def is_network_error(error: Exception) -> bool:
    """
    判断是否为网络连接错误
    
    Parameters
    ----------
    error : Exception
        要检查的异常
        
    Returns
    -------
    bool
        如果是网络错误返回 True，否则 False
    """
    if isinstance(error, (ccxt.NetworkError, ConnectionError)):
        return True
    
    error_msg = str(error).lower()
    network_indicators = [
        "timeout", "connection", "network", "dns", "socket",
        "connection reset", "connection refused", "unreachable"
    ]
    return any(indicator in error_msg for indicator in network_indicators)


def adaptive_retry_delay(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
    """
    自适应重试延迟计算
    
    使用指数退避策略，但限制最大延迟时间。
    
    Parameters
    ----------
    attempt : int
        当前重试次数（从 1 开始）
    base_delay : float, optional
        基础延迟时间（秒），默认 1.0
    max_delay : float, optional
        最大延迟时间（秒），默认 60.0
        
    Returns
    -------
    float
        计算出的延迟时间（秒）
        
    Examples
    --------
    >>> for i in range(1, 6):
    ...     delay = adaptive_retry_delay(i, base_delay=2.0)
    ...     print(f"第{i}次重试延迟: {delay}秒")
    """
    # 指数退避：base_delay * 2^(attempt-1)
    exponential_delay = base_delay * (2 ** (attempt - 1))
    # 限制最大延迟
    return min(exponential_delay, max_delay)


class RateLimiter:
    """
    简单的速率限制器
    
    用于控制API调用频率，避免触发交易所限流。
    """
    
    def __init__(self, max_calls: int, time_window: float):
        """
        初始化速率限制器
        
        Parameters
        ----------
        max_calls : int
            时间窗口内的最大调用次数
        time_window : float
            时间窗口长度（秒）
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []
    
    def can_call(self) -> bool:
        """
        检查是否可以进行新的调用
        
        Returns
        -------
        bool
            如果可以调用返回 True，否则 False
        """
        current_time = time.time()
        # 清除过期的调用记录
        self.calls = [call_time for call_time in self.calls 
                     if current_time - call_time <= self.time_window]
        
        return len(self.calls) < self.max_calls
    
    def wait_if_needed(self) -> None:
        """
        如果需要的话等待直到可以进行新的调用
        """
        while not self.can_call():
            time.sleep(0.1)
    
    def record_call(self) -> None:
        """
        记录一次API调用
        """
        self.calls.append(time.time())
    
    def __enter__(self):
        """上下文管理器入口"""
        self.wait_if_needed()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.record_call()


# 预定义的常用速率限制器
def create_binance_rate_limiter() -> RateLimiter:
    """
    创建适用于 Binance API 的速率限制器
    
    Returns
    -------
    RateLimiter
        配置好的速率限制器实例
    """
    # Binance: 1200请求/分钟
    return RateLimiter(max_calls=1200, time_window=60.0)


def create_okx_rate_limiter() -> RateLimiter:
    """
    创建适用于 OKX API 的速率限制器
    
    Returns
    -------
    RateLimiter
        配置好的速率限制器实例
    """
    # OKX: 一般较为保守，20请求/秒
    return RateLimiter(max_calls=20, time_window=1.0)