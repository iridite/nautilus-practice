"""Error handling decorators for LangGraph nodes.

This module provides retry and timeout decorators for robust node execution.
"""

import asyncio
import functools
from typing import Any, Awaitable, Callable, TypeVar

from infrastructure.observability.metrics import MetricsCollector, NodeMetrics
from infrastructure.observability.tracing import get_trace_context
from shared.logging import get_logger

logger = get_logger(__name__)
T = TypeVar('T')


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    exponential_base: float = 2.0
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Retry decorator with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff calculation
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Exception | None = None
            collector = MetricsCollector.get_instance()
            trace_ctx = get_trace_context()

            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    # Record retry metric
                    if trace_ctx:
                        metric = NodeMetrics(
                            node_name=f"{func.__name__}_retry",
                            execution_time=0.0,
                            success=False,
                            error=f"Attempt {attempt + 1}/{max_retries}: {str(e)}",
                        )
                        collector.record_metric(metric)

                    if attempt < max_retries - 1:
                        delay = min(base_delay * (exponential_base ** attempt), max_delay)
                        log_kwargs = {
                            "error": str(e),
                            "retry_delay": delay,
                        }
                        if trace_ctx:
                            log_kwargs.update(trace_ctx.to_dict())

                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries} failed for {func.__name__}",
                            **log_kwargs
                        )
                        await asyncio.sleep(delay)
                    else:
                        log_kwargs = {"error": str(e)}
                        if trace_ctx:
                            log_kwargs.update(trace_ctx.to_dict())

                        logger.error(
                            f"All {max_retries} attempts failed for {func.__name__}",
                            **log_kwargs
                        )
            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected: no exception but all retries failed")
        return wrapper
    return decorator


def with_timeout(timeout_seconds: float) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Timeout decorator for async functions.

    Args:
        timeout_seconds: Maximum execution time in seconds
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            trace_ctx = get_trace_context()

            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                log_kwargs = {"timeout_seconds": timeout_seconds}
                if trace_ctx:
                    log_kwargs.update(trace_ctx.to_dict())

                logger.error(
                    f"Timeout after {timeout_seconds}s for {func.__name__}",
                    **log_kwargs
                )
                raise
        return wrapper
    return decorator
