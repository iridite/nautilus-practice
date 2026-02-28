"""Tests for distributed tracing."""

import unittest

from infrastructure.observability.tracing import (
    TraceContext,
    clear_trace_context,
    get_trace_context,
    log_with_trace,
    set_trace_context,
    with_tracing,
)


class TestTraceContext(unittest.TestCase):
    """Test TraceContext dataclass."""

    def test_default_values(self):
        """Test default values are generated."""
        ctx = TraceContext()
        self.assertIsNotNone(ctx.correlation_id)
        self.assertIsNotNone(ctx.span_id)
        self.assertIsNone(ctx.parent_span_id)
        self.assertEqual(ctx.workflow_name, "unknown")
        self.assertEqual(ctx.metadata, {})

    def test_create_child_span(self):
        """Test creating child span."""
        parent = TraceContext(
            correlation_id="parent-corr-id",
            span_id="parent-span-id",
            workflow_name="test_workflow",
            metadata={"key": "value"},
        )

        child = parent.create_child_span("child_span")

        # Child inherits correlation_id and workflow_name
        self.assertEqual(child.correlation_id, "parent-corr-id")
        self.assertEqual(child.workflow_name, "test_workflow")

        # Child has parent's span_id as parent_span_id
        self.assertEqual(child.parent_span_id, "parent-span-id")

        # Child has new span_id
        self.assertNotEqual(child.span_id, parent.span_id)

        # Child metadata includes span_name
        self.assertIn("span_name", child.metadata)
        self.assertEqual(child.metadata["span_name"], "child_span")

    def test_to_dict(self):
        """Test converting to dictionary."""
        ctx = TraceContext(
            correlation_id="test-corr-id",
            span_id="test-span-id",
            parent_span_id="parent-span-id",
            workflow_name="test_workflow",
            metadata={"key": "value"},
        )

        result = ctx.to_dict()

        self.assertEqual(result["correlation_id"], "test-corr-id")
        self.assertEqual(result["span_id"], "test-span-id")
        self.assertEqual(result["parent_span_id"], "parent-span-id")
        self.assertEqual(result["workflow_name"], "test_workflow")
        self.assertEqual(result["key"], "value")


class TestTraceContextManagement(unittest.TestCase):
    """Test trace context management functions."""

    def setUp(self):
        """Clear trace context before each test."""
        clear_trace_context()

    def tearDown(self):
        """Clear trace context after each test."""
        clear_trace_context()

    def test_get_set_clear(self):
        """Test get/set/clear trace context."""
        # Initially None
        self.assertIsNone(get_trace_context())

        # Set context
        ctx = TraceContext(correlation_id="test-id")
        set_trace_context(ctx)

        # Get returns same context
        retrieved = get_trace_context()
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.correlation_id, "test-id")

        # Clear removes context
        clear_trace_context()
        self.assertIsNone(get_trace_context())


class TestWithTracingDecorator(unittest.IsolatedAsyncioTestCase):
    """Test with_tracing decorator."""

    def setUp(self):
        """Clear trace context before each test."""
        clear_trace_context()

    def tearDown(self):
        """Clear trace context after each test."""
        clear_trace_context()

    async def test_create_root_context(self):
        """Test creating root trace context."""
        @with_tracing(span_name="root_span", workflow_name="test_workflow", create_root=True)
        async def test_func():
            ctx = get_trace_context()
            self.assertIsNotNone(ctx)
            self.assertEqual(ctx.workflow_name, "test_workflow")
            self.assertIsNone(ctx.parent_span_id)
            return "success"

        result = await test_func()
        self.assertEqual(result, "success")

        # Context should be cleared after execution
        self.assertIsNone(get_trace_context())

    async def test_create_child_span(self):
        """Test creating child span from parent context."""
        parent_ctx = TraceContext(
            correlation_id="parent-corr-id",
            span_id="parent-span-id",
            workflow_name="test_workflow",
        )
        set_trace_context(parent_ctx)

        @with_tracing(span_name="child_span")
        async def test_func():
            ctx = get_trace_context()
            self.assertIsNotNone(ctx)
            self.assertEqual(ctx.correlation_id, "parent-corr-id")
            self.assertEqual(ctx.parent_span_id, "parent-span-id")
            self.assertNotEqual(ctx.span_id, "parent-span-id")
            return "success"

        result = await test_func()
        self.assertEqual(result, "success")

        # Parent context should be restored
        ctx = get_trace_context()
        self.assertEqual(ctx.span_id, "parent-span-id")

    async def test_no_tracing_without_root(self):
        """Test function executes normally without trace context."""
        @with_tracing(span_name="test_span", create_root=False)
        async def test_func():
            # Should execute without creating context
            self.assertIsNone(get_trace_context())
            return "success"

        result = await test_func()
        self.assertEqual(result, "success")

    async def test_default_span_name(self):
        """Test using function name as default span name."""
        @with_tracing(create_root=True)
        async def my_custom_function():
            ctx = get_trace_context()
            self.assertEqual(ctx.workflow_name, "my_custom_function")
            return "success"

        await my_custom_function()

    async def test_exception_handling(self):
        """Test trace context is cleaned up on exception."""
        @with_tracing(span_name="test_span", create_root=True)
        async def test_func():
            raise ValueError("Test error")

        with self.assertRaises(ValueError):
            await test_func()

        # Context should be cleared even after exception
        self.assertIsNone(get_trace_context())

    async def test_nested_spans(self):
        """Test nested span creation."""
        correlation_ids = []
        span_ids = []

        @with_tracing(span_name="inner_span")
        async def inner_func():
            ctx = get_trace_context()
            correlation_ids.append(ctx.correlation_id)
            span_ids.append(ctx.span_id)
            return "inner"

        @with_tracing(span_name="outer_span", create_root=True)
        async def outer_func():
            ctx = get_trace_context()
            correlation_ids.append(ctx.correlation_id)
            span_ids.append(ctx.span_id)
            return await inner_func()

        result = await outer_func()
        self.assertEqual(result, "inner")

        # Both spans should have same correlation_id
        self.assertEqual(len(set(correlation_ids)), 1)

        # Spans should have different span_ids
        self.assertEqual(len(set(span_ids)), 2)


class TestLogWithTrace(unittest.TestCase):
    """Test log_with_trace function."""

    def setUp(self):
        """Clear trace context before each test."""
        clear_trace_context()

    def tearDown(self):
        """Clear trace context after each test."""
        clear_trace_context()

    def test_log_with_context(self):
        """Test logging with trace context."""
        ctx = TraceContext(correlation_id="test-id")
        set_trace_context(ctx)

        # Should not raise exception
        log_with_trace("Test message", extra_field="value")

    def test_log_without_context(self):
        """Test logging without trace context."""
        # Should not raise exception
        log_with_trace("Test message", extra_field="value")


if __name__ == "__main__":
    unittest.main()
