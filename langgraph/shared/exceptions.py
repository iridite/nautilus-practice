"""Domain exception hierarchy for LangGraph strategy automation system."""

from typing import Any


class LangGraphError(Exception):
    """Base exception for all LangGraph errors.

    Attributes:
        message: Error message describing what went wrong
        context: Optional dictionary with additional context information
    """

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        """Initialize the exception.

        Args:
            message: Error message
            context: Optional context dictionary with additional information
        """
        self.message = message
        self.context = context or {}
        super().__init__(message)

    def __str__(self) -> str:
        """Return string representation of the error."""
        return self.message


class StrategyError(LangGraphError):
    """Exception raised for strategy-related errors.

    Examples:
        - Invalid strategy configuration
        - Strategy execution failures
        - Strategy parameter validation errors
    """

    pass


class OptimizationError(LangGraphError):
    """Exception raised for parameter optimization errors.

    Examples:
        - Optimization convergence failures
        - Invalid optimization constraints
        - Optimization timeout
    """

    pass


class BacktestError(LangGraphError):
    """Exception raised for backtest execution errors.

    Examples:
        - Data loading failures
        - Backtest engine errors
        - Invalid backtest configuration
    """

    pass


class LLMError(LangGraphError):
    """Exception raised for LLM-related errors.

    Examples:
        - API call failures
        - Rate limiting
        - Invalid responses
        - Service unavailability
    """

    pass


class ParameterValidationError(LangGraphError):
    """Exception raised for parameter validation errors.

    This exception is raised when strategy parameters, optimization parameters,
    or other configuration values fail validation checks.

    Examples:
        >>> raise ParameterValidationError(
        ...     "ATR period must be positive",
        ...     context={"param": "atr_period", "value": -1}
        ... )
    """

    pass
