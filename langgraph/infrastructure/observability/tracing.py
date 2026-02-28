"""Distributed tracing for LangGraph workflows.

This module provides correlation ID generation and request chain tracking
for debugging and monitoring distributed workflow executions.
"""

import contextvars
import functools
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypeVar

from shared.logging import get_logger

logger = get_logger(__name__)
T = TypeVar("T")

# Context variable for trace context
_trace_context: contextvars.ContextVar["TraceContext | None"] = contextvars.ContextVar(
    "trace_context", default=None
)


@dataclass
class TraceContext:
    """Trace context for a workflow execution.

    Attributes:
        correlation_id: Unique identifier for the entire workflow execution
        parent_span_id: Parent span ID for nested operations
        span_id: Current span ID
        workflow_name: Name of the workflow being executed
        metadata: Additional metadata for the trace
    """

    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_span_id: str | None = None
    span_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_name: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def create_child_span(self, span_name: str) -> "TraceContext":
        """Create a child span context.

        Args:
            span_name: Name for the child span

        Returns:
            New TraceContext with current span as parent
        """
        return TraceContext(
            correlation_id=self.correlation_id,
            parent_span_id=self.span_id,
            span_id=str(uuid.uuid4()),
            workflow_name=self.workflow_name,
            metadata={**self.metadata, "span_name": span_name},
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert trace context to dictionary for logging.

        Returns:
            Dictionary representation of trace context
        """
        return {
            "correlation_id": self.correlation_id,
            "parent_span_id": self.parent_span_id,
            "span_id": self.span_id,
            "workflow_name": self.workflow_name,
            **self.metadata,
        }


def get_trace_context() -> TraceContext | None:
    """Get the current trace context from context variables.

    Returns:
        Current TraceContext or None if not set
    """
    return _trace_context.get()


def set_trace_context(context: TraceContext) -> None:
    """Set the current trace context.

    Args:
        context: TraceContext to set
    """
    _trace_context.set(context)


def clear_trace_context() -> None:
    """Clear the current trace context."""
    _trace_context.set(None)


def with_tracing(
    span_name: str | None = None, workflow_name: str | None = None, create_root: bool = False
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator to add tracing to a function.

    Args:
        span_name: Optional custom span name (defaults to function name)
        workflow_name: Optional workflow name (only used if create_root=True)
        create_root: Whether to create a root trace context if none exists

    Example:
        >>> @with_tracing(span_name="analyze_strategy", create_root=True)
        ... async def analyze_node(state: dict) -> dict:
        ...     # Node implementation
        ...     return {"result": "analyzed"}
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        name = span_name or func.__name__

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            # Get or create trace context
            parent_context = get_trace_context()

            if parent_context is None:
                if create_root:
                    # Create root trace context
                    context = TraceContext(
                        workflow_name=workflow_name or name,
                        metadata={"span_name": name},
                    )
                    logger.info(
                        f"Starting workflow: {name}",
                        **context.to_dict(),
                    )
                else:
                    # No tracing context and not creating root
                    return await func(*args, **kwargs)
            else:
                # Create child span
                context = parent_context.create_child_span(name)
                logger.debug(
                    f"Starting span: {name}",
                    **context.to_dict(),
                )

            # Set context for this execution
            token = _trace_context.set(context)

            try:
                result = await func(*args, **kwargs)
                logger.debug(
                    f"Completed span: {name}",
                    **context.to_dict(),
                )
                return result

            except Exception as e:
                logger.error(
                    f"Failed span: {name}",
                    error=str(e),
                    **context.to_dict(),
                )
                raise

            finally:
                # Restore previous context
                _trace_context.reset(token)

        return wrapper

    return decorator


def log_with_trace(message: str, **kwargs: Any) -> None:
    """Log a message with trace context if available.

    Args:
        message: Log message
        **kwargs: Additional log fields
    """
    context = get_trace_context()
    if context:
        logger.info(message, **context.to_dict(), **kwargs)
    else:
        logger.info(message, **kwargs)
