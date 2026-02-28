"""Tests for domain exception hierarchy."""


from langgraph.shared.exceptions import (
    BacktestError,
    LangGraphError,
    LLMError,
    OptimizationError,
    ParameterValidationError,
    StrategyError,
)


class TestLangGraphError:
    """Test base exception class."""

    def test_basic_error(self):
        """Test basic error creation."""
        error = LangGraphError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"
        assert error.context == {}

    def test_error_with_context(self):
        """Test error with context information."""
        context = {"file": "test.yaml", "line": 42}
        error = LangGraphError("Parse error", context=context)
        assert error.message == "Parse error"
        assert error.context == context
        assert "Parse error" in str(error)

    def test_error_inheritance(self):
        """Test that LangGraphError inherits from Exception."""
        error = LangGraphError("Test")
        assert isinstance(error, Exception)


class TestStrategyError:
    """Test strategy-related exceptions."""

    def test_strategy_error(self):
        """Test strategy error creation."""
        error = StrategyError("Invalid strategy configuration")
        assert str(error) == "Invalid strategy configuration"
        assert isinstance(error, LangGraphError)

    def test_strategy_error_with_context(self):
        """Test strategy error with context."""
        context = {"strategy": "keltner_rs_breakout", "param": "atr_period"}
        error = StrategyError("Invalid parameter", context=context)
        assert error.context == context


class TestOptimizationError:
    """Test optimization-related exceptions."""

    def test_optimization_error(self):
        """Test optimization error creation."""
        error = OptimizationError("Optimization failed")
        assert str(error) == "Optimization failed"
        assert isinstance(error, LangGraphError)

    def test_optimization_error_with_context(self):
        """Test optimization error with context."""
        context = {"iteration": 10, "reason": "convergence_failed"}
        error = OptimizationError("Failed to converge", context=context)
        assert error.context == context


class TestBacktestError:
    """Test backtest-related exceptions."""

    def test_backtest_error(self):
        """Test backtest error creation."""
        error = BacktestError("Backtest execution failed")
        assert str(error) == "Backtest execution failed"
        assert isinstance(error, LangGraphError)

    def test_backtest_error_with_context(self):
        """Test backtest error with context."""
        context = {"engine": "high", "symbols": ["BTC/USDT"]}
        error = BacktestError("Data loading failed", context=context)
        assert error.context == context


class TestLLMError:
    """Test LLM-related exceptions."""

    def test_llm_error(self):
        """Test LLM error creation."""
        error = LLMError("API call failed")
        assert str(error) == "API call failed"
        assert isinstance(error, LangGraphError)

    def test_llm_error_with_context(self):
        """Test LLM error with context."""
        context = {"model": "claude-opus-4", "status_code": 503}
        error = LLMError("Service unavailable", context=context)
        assert error.context == context


class TestParameterValidationError:
    """Test parameter validation-related exceptions."""

    def test_parameter_validation_error(self):
        """Test parameter validation error creation."""
        error = ParameterValidationError("Invalid configuration")
        assert str(error) == "Invalid configuration"
        assert isinstance(error, LangGraphError)

    def test_parameter_validation_error_with_context(self):
        """Test parameter validation error with context."""
        context = {"field": "atr_period", "value": -1, "constraint": "must be positive"}
        error = ParameterValidationError("Validation failed", context=context)
        assert error.context == context


class TestExceptionHierarchy:
    """Test exception inheritance relationships."""

    def test_all_inherit_from_base(self):
        """Test that all domain exceptions inherit from LangGraphError."""
        exceptions = [
            StrategyError("test"),
            OptimizationError("test"),
            BacktestError("test"),
            LLMError("test"),
            ParameterValidationError("test"),
        ]
        for exc in exceptions:
            assert isinstance(exc, LangGraphError)
            assert isinstance(exc, Exception)

    def test_exception_types_are_distinct(self):
        """Test that exception types can be distinguished."""
        strategy_err = StrategyError("test")
        optimization_err = OptimizationError("test")

        assert type(strategy_err) is not type(optimization_err)
        assert not isinstance(strategy_err, OptimizationError)
        assert not isinstance(optimization_err, StrategyError)
