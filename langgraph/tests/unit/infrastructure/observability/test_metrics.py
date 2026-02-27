"""Tests for metrics collection."""

import asyncio
import unittest

from infrastructure.observability.metrics import (
    AggregatedMetrics,
    MetricsCollector,
    NodeMetrics,
    with_metrics,
)


class TestNodeMetrics(unittest.TestCase):
    """Test NodeMetrics dataclass."""

    def test_total_tokens(self):
        """Test total_tokens property."""
        metric = NodeMetrics(
            node_name="test_node",
            execution_time=1.5,
            success=True,
            llm_tokens_input=100,
            llm_tokens_output=50,
        )
        self.assertEqual(metric.total_tokens, 150)

    def test_failed_metric(self):
        """Test metric with error."""
        metric = NodeMetrics(
            node_name="test_node",
            execution_time=0.5,
            success=False,
            error="Test error",
        )
        self.assertFalse(metric.success)
        self.assertEqual(metric.error, "Test error")
        self.assertEqual(metric.total_tokens, 0)


class TestAggregatedMetrics(unittest.TestCase):
    """Test AggregatedMetrics dataclass."""

    def test_success_rate(self):
        """Test success rate calculation."""
        agg = AggregatedMetrics(
            node_name="test_node",
            total_executions=10,
            successful_executions=8,
            failed_executions=2,
        )
        self.assertEqual(agg.success_rate, 80.0)

    def test_success_rate_zero_executions(self):
        """Test success rate with zero executions."""
        agg = AggregatedMetrics(node_name="test_node")
        self.assertEqual(agg.success_rate, 0.0)

    def test_avg_execution_time(self):
        """Test average execution time calculation."""
        agg = AggregatedMetrics(
            node_name="test_node",
            total_executions=5,
            total_execution_time=10.0,
        )
        self.assertEqual(agg.avg_execution_time, 2.0)

    def test_avg_execution_time_zero_executions(self):
        """Test average execution time with zero executions."""
        agg = AggregatedMetrics(node_name="test_node")
        self.assertEqual(agg.avg_execution_time, 0.0)


class TestMetricsCollector(unittest.TestCase):
    """Test MetricsCollector class."""

    def setUp(self):
        """Reset metrics collector before each test."""
        MetricsCollector.reset()

    def test_singleton(self):
        """Test singleton pattern."""
        collector1 = MetricsCollector.get_instance()
        collector2 = MetricsCollector.get_instance()
        self.assertIs(collector1, collector2)

    def test_record_metric(self):
        """Test recording a metric."""
        collector = MetricsCollector.get_instance()
        metric = NodeMetrics(
            node_name="test_node",
            execution_time=1.5,
            success=True,
            llm_tokens_input=100,
            llm_tokens_output=50,
        )
        collector.record_metric(metric)

        metrics = collector.get_metrics()
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].node_name, "test_node")

    def test_aggregated_metrics(self):
        """Test aggregated metrics calculation."""
        collector = MetricsCollector.get_instance()

        # Record multiple metrics for same node
        for i in range(5):
            metric = NodeMetrics(
                node_name="test_node",
                execution_time=1.0 + i * 0.5,
                success=i < 4,  # 4 successes, 1 failure
                llm_tokens_input=100,
                llm_tokens_output=50,
            )
            collector.record_metric(metric)

        agg = collector.get_aggregated_metrics()
        self.assertIn("test_node", agg)

        node_agg = agg["test_node"]
        self.assertEqual(node_agg.total_executions, 5)
        self.assertEqual(node_agg.successful_executions, 4)
        self.assertEqual(node_agg.failed_executions, 1)
        self.assertEqual(node_agg.success_rate, 80.0)
        self.assertEqual(node_agg.total_tokens, 750)  # 150 * 5

    def test_get_metrics_filtered(self):
        """Test getting metrics filtered by node name."""
        collector = MetricsCollector.get_instance()

        collector.record_metric(NodeMetrics("node1", 1.0, True))
        collector.record_metric(NodeMetrics("node2", 2.0, True))
        collector.record_metric(NodeMetrics("node1", 1.5, True))

        node1_metrics = collector.get_metrics("node1")
        self.assertEqual(len(node1_metrics), 2)
        self.assertTrue(all(m.node_name == "node1" for m in node1_metrics))

    def test_generate_report(self):
        """Test report generation."""
        collector = MetricsCollector.get_instance()

        collector.record_metric(
            NodeMetrics("node1", 1.0, True, llm_tokens_input=100, llm_tokens_output=50)
        )
        collector.record_metric(
            NodeMetrics("node2", 2.0, False, error="Test error")
        )

        report = collector.generate_report()
        self.assertIn("LangGraph Execution Metrics Report", report)
        self.assertIn("node1", report)
        self.assertIn("node2", report)
        self.assertIn("Total Executions: 2", report)

    def test_generate_report_empty(self):
        """Test report generation with no metrics."""
        collector = MetricsCollector.get_instance()
        report = collector.generate_report()
        self.assertEqual(report, "No metrics recorded")

    def test_clear(self):
        """Test clearing metrics."""
        collector = MetricsCollector.get_instance()
        collector.record_metric(NodeMetrics("test_node", 1.0, True))

        collector.clear()
        self.assertEqual(len(collector.get_metrics()), 0)
        self.assertEqual(len(collector.get_aggregated_metrics()), 0)


class TestWithMetricsDecorator(unittest.IsolatedAsyncioTestCase):
    """Test with_metrics decorator."""

    def setUp(self):
        """Reset metrics collector before each test."""
        MetricsCollector.reset()

    async def test_successful_execution(self):
        """Test decorator with successful execution."""
        @with_metrics(node_name="test_node")
        async def test_func():
            await asyncio.sleep(0.1)
            return {"result": "success"}

        result = await test_func()
        self.assertEqual(result, {"result": "success"})

        collector = MetricsCollector.get_instance()
        metrics = collector.get_metrics()
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].node_name, "test_node")
        self.assertTrue(metrics[0].success)
        self.assertGreater(metrics[0].execution_time, 0.1)

    async def test_failed_execution(self):
        """Test decorator with failed execution."""
        @with_metrics(node_name="test_node")
        async def test_func():
            raise ValueError("Test error")

        with self.assertRaises(ValueError):
            await test_func()

        collector = MetricsCollector.get_instance()
        metrics = collector.get_metrics()
        self.assertEqual(len(metrics), 1)
        self.assertFalse(metrics[0].success)
        self.assertEqual(metrics[0].error, "Test error")

    async def test_token_tracking(self):
        """Test token tracking from response."""
        @with_metrics(node_name="test_node", track_tokens=True)
        async def test_func():
            return {
                "result": "success",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                }
            }

        await test_func()

        collector = MetricsCollector.get_instance()
        metrics = collector.get_metrics()
        self.assertEqual(metrics[0].llm_tokens_input, 100)
        self.assertEqual(metrics[0].llm_tokens_output, 50)

    async def test_default_node_name(self):
        """Test decorator with default node name."""
        @with_metrics()
        async def my_custom_function():
            return {"result": "success"}

        await my_custom_function()

        collector = MetricsCollector.get_instance()
        metrics = collector.get_metrics()
        self.assertEqual(metrics[0].node_name, "my_custom_function")


if __name__ == "__main__":
    unittest.main()
