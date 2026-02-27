"""Performance metrics collection for LangGraph nodes.

This module provides decorators and collectors for tracking:
- Node execution time
- LLM token usage
- Success/failure rates
- Resource utilization
"""

import functools
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypeVar

from shared.logging import get_logger

logger = get_logger(__name__)
T = TypeVar('T')


@dataclass
class NodeMetrics:
    """Metrics for a single node execution."""

    node_name: str
    execution_time: float
    success: bool
    error: str | None = None
    llm_tokens_input: int = 0
    llm_tokens_output: int = 0
    timestamp: float = field(default_factory=time.time)

    @property
    def total_tokens(self) -> int:
        """Total tokens used (input + output)."""
        return self.llm_tokens_input + self.llm_tokens_output


@dataclass
class AggregatedMetrics:
    """Aggregated metrics for a node across multiple executions."""

    node_name: str
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    total_execution_time: float = 0.0
    min_execution_time: float = float('inf')
    max_execution_time: float = 0.0
    total_tokens: int = 0

    @property
    def success_rate(self) -> float:
        """Success rate as a percentage."""
        if self.total_executions == 0:
            return 0.0
        return (self.successful_executions / self.total_executions) * 100

    @property
    def avg_execution_time(self) -> float:
        """Average execution time in seconds."""
        if self.total_executions == 0:
            return 0.0
        return self.total_execution_time / self.total_executions


class MetricsCollector:
    """Centralized metrics collector for LangGraph workflows.

    This singleton class collects and aggregates metrics from all nodes
    in a workflow execution.

    Example:
        >>> collector = MetricsCollector.get_instance()
        >>> collector.record_metric(NodeMetrics(
        ...     node_name="analyze_strategy",
        ...     execution_time=1.5,
        ...     success=True,
        ...     llm_tokens_input=100,
        ...     llm_tokens_output=50
        ... ))
        >>> report = collector.generate_report()
    """

    _instance: "MetricsCollector | None" = None

    def __init__(self) -> None:
        """Initialize metrics collector."""
        self._metrics: list[NodeMetrics] = []
        self._aggregated: dict[str, AggregatedMetrics] = defaultdict(
            lambda: AggregatedMetrics(node_name="")
        )

    @classmethod
    def get_instance(cls) -> "MetricsCollector":
        """Get singleton instance of metrics collector."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (useful for testing)."""
        cls._instance = None

    def record_metric(self, metric: NodeMetrics) -> None:
        """Record a node execution metric.

        Args:
            metric: Node execution metrics to record
        """
        self._metrics.append(metric)

        # Update aggregated metrics
        agg = self._aggregated[metric.node_name]
        if not agg.node_name:
            agg.node_name = metric.node_name

        agg.total_executions += 1
        if metric.success:
            agg.successful_executions += 1
        else:
            agg.failed_executions += 1

        agg.total_execution_time += metric.execution_time
        agg.min_execution_time = min(agg.min_execution_time, metric.execution_time)
        agg.max_execution_time = max(agg.max_execution_time, metric.execution_time)
        agg.total_tokens += metric.total_tokens

        logger.debug(
            "Recorded metric",
            node_name=metric.node_name,
            execution_time=f"{metric.execution_time:.3f}s",
            success=metric.success,
            tokens=metric.total_tokens,
        )

    def get_metrics(self, node_name: str | None = None) -> list[NodeMetrics]:
        """Get recorded metrics, optionally filtered by node name.

        Args:
            node_name: Optional node name to filter by

        Returns:
            List of node metrics
        """
        if node_name is None:
            return self._metrics.copy()
        return [m for m in self._metrics if m.node_name == node_name]

    def get_aggregated_metrics(self, node_name: str | None = None) -> dict[str, AggregatedMetrics]:
        """Get aggregated metrics, optionally filtered by node name.

        Args:
            node_name: Optional node name to filter by

        Returns:
            Dictionary of aggregated metrics by node name
        """
        if node_name is None:
            return dict(self._aggregated)
        if node_name in self._aggregated:
            return {node_name: self._aggregated[node_name]}
        return {}

    def generate_report(self) -> str:
        """Generate a human-readable metrics report.

        Returns:
            Formatted metrics report string
        """
        if not self._metrics:
            return "No metrics recorded"

        lines = ["=" * 80, "LangGraph Execution Metrics Report", "=" * 80, ""]

        # Overall statistics
        total_time = sum(m.execution_time for m in self._metrics)
        total_tokens = sum(m.total_tokens for m in self._metrics)
        success_count = sum(1 for m in self._metrics if m.success)
        total_count = len(self._metrics)

        lines.extend([
            "Overall Statistics:",
            f"  Total Executions: {total_count}",
            f"  Successful: {success_count} ({success_count/total_count*100:.1f}%)",
            f"  Failed: {total_count - success_count}",
            f"  Total Time: {total_time:.2f}s",
            f"  Total Tokens: {total_tokens:,}",
            "",
        ])

        # Per-node statistics
        lines.append("Per-Node Statistics:")
        lines.append(f"{'Node':<30} {'Exec':<6} {'Success':<8} {'Avg Time':<10} {'Tokens':<10}")
        lines.append("-" * 80)

        for node_name in sorted(self._aggregated.keys()):
            agg = self._aggregated[node_name]
            lines.append(
                f"{node_name:<30} "
                f"{agg.total_executions:<6} "
                f"{agg.success_rate:>6.1f}% "
                f"{agg.avg_execution_time:>8.3f}s "
                f"{agg.total_tokens:>9,}"
            )

        lines.append("=" * 80)
        return "\n".join(lines)

    def clear(self) -> None:
        """Clear all recorded metrics."""
        self._metrics.clear()
        self._aggregated.clear()
        logger.debug("Cleared all metrics")


def with_metrics(
    node_name: str | None = None,
    track_tokens: bool = True
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator to collect metrics for a node function.

    Args:
        node_name: Optional custom node name (defaults to function name)
        track_tokens: Whether to track LLM token usage from response

    Example:
        >>> @with_metrics(node_name="analyze_strategy")
        ... async def analyze_node(state: dict) -> dict:
        ...     # Node implementation
        ...     return {"result": "analyzed"}
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        name = node_name or func.__name__

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            collector = MetricsCollector.get_instance()
            start_time = time.time()
            success = False
            error_msg: str | None = None
            tokens_input = 0
            tokens_output = 0

            try:
                result = await func(*args, **kwargs)
                success = True

                # Extract token usage if available
                if track_tokens and isinstance(result, dict):
                    usage = result.get("usage", {})
                    tokens_input = usage.get("input_tokens", 0)
                    tokens_output = usage.get("output_tokens", 0)

                return result

            except Exception as e:
                error_msg = str(e)
                raise

            finally:
                execution_time = time.time() - start_time
                metric = NodeMetrics(
                    node_name=name,
                    execution_time=execution_time,
                    success=success,
                    error=error_msg,
                    llm_tokens_input=tokens_input,
                    llm_tokens_output=tokens_output,
                )
                collector.record_metric(metric)

        return wrapper
    return decorator
