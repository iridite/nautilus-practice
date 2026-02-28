"""Example demonstrating observability features.

This example shows how to use metrics collection and distributed tracing
in LangGraph workflows.
"""

import asyncio

from infrastructure.observability import (
    MetricsCollector,
    get_trace_context,
    with_metrics,
    with_tracing,
)
from shared.config import LangGraphConfig
from shared.logging import get_logger, setup_logging

logger = get_logger(__name__)


@with_metrics(node_name="analyze_strategy")
@with_tracing(span_name="analyze_strategy")
async def analyze_strategy_node(state: dict) -> dict:
    """Example node with metrics and tracing."""
    _ = get_trace_context()  # Get trace context for observability
    logger.info("Analyzing strategy", strategy_name=state.get("strategy_name"))

    # Simulate work
    await asyncio.sleep(0.5)

    # Simulate LLM response with token usage
    return {
        "analysis": "Strategy looks good",
        "usage": {
            "input_tokens": 150,
            "output_tokens": 75,
        },
    }


@with_metrics(node_name="generate_code")
@with_tracing(span_name="generate_code")
async def generate_code_node(state: dict) -> dict:
    """Example node with metrics and tracing."""
    logger.info("Generating code", strategy_name=state.get("strategy_name"))

    # Simulate work
    await asyncio.sleep(1.0)

    return {
        "code": "class MyStrategy: pass",
        "usage": {
            "input_tokens": 200,
            "output_tokens": 300,
        },
    }


@with_tracing(span_name="workflow", workflow_name="strategy_generation", create_root=True)
async def run_workflow(strategy_name: str) -> dict:
    """Example workflow with multiple nodes."""
    logger.info("Starting workflow", strategy_name=strategy_name)

    state = {"strategy_name": strategy_name}

    # Run nodes sequentially
    state = await analyze_strategy_node(state)
    state = await generate_code_node(state)

    logger.info("Workflow completed", strategy_name=strategy_name)
    return state


async def main():
    """Run example workflow and display metrics."""
    # Setup logging (in real usage, this would be done at application startup)
    config = LangGraphConfig(
        claude_api_key="sk-ant-test-key-for-example",
        log_level="INFO",
    )
    setup_logging(config)

    # Reset metrics collector
    MetricsCollector.reset()

    # Run workflow
    print("=" * 80)
    print("Running example workflow with observability...")
    print("=" * 80)
    print()

    await run_workflow("keltner_breakout")

    print()
    print("Workflow completed!")
    print()

    # Display metrics report
    collector = MetricsCollector.get_instance()
    report = collector.generate_report()
    print(report)

    # Display individual metrics
    print()
    print("Detailed Metrics:")
    print("-" * 80)
    for metric in collector.get_metrics():
        print(f"Node: {metric.node_name}")
        print(f"  Execution Time: {metric.execution_time:.3f}s")
        print(f"  Success: {metric.success}")
        print(f"  Tokens: {metric.total_tokens}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
