"""Backtest engine wrapper for backtesting.py framework"""
import ast
from typing import Any, Tuple
from backtesting import Backtest
from backtesting.test import GOOG
from langgraph.domain.models.strategy import Strategy


class BacktestEngine:
    """Wrapper for backtesting.py framework"""

    def __init__(self):
        """Initialize the backtest engine"""
        self.default_cash = 10000
        self.default_commission = 0.002

    def run(
        self,
        strategy: Strategy,
        data: Any = None,
        cash: float = None,
        commission: float = None
    ) -> dict[str, Any]:
        """
        Run backtest for a strategy

        Args:
            strategy: Strategy domain model with code
            data: Optional pandas DataFrame with OHLCV data
            cash: Initial cash (default: 10000)
            commission: Commission rate (default: 0.002)

        Returns:
            Dictionary with metrics and equity curve

        Raises:
            Exception: If strategy code is invalid or execution fails
        """
        # Validate code first
        is_valid, errors = self.validate_code(strategy.code)
        if not is_valid:
            raise ValueError(f"Invalid strategy code: {errors}")

        # Use default data if not provided
        if data is None:
            data = GOOG

        # Use default parameters if not provided
        if cash is None:
            cash = self.default_cash
        if commission is None:
            commission = self.default_commission

        # Extract strategy class from code
        strategy_class = self._extract_strategy_class(strategy.code)

        # Run backtest
        bt = Backtest(
            data,
            strategy_class,
            cash=cash,
            commission=commission
        )

        stats = bt.run()

        # Convert stats to dictionary
        result = {
            "metrics": self._extract_metrics(stats),
            "equity_curve": self._extract_equity_curve(stats)
        }

        return result

    def validate_code(self, code: str) -> Tuple[bool, list[str]]:
        """
        Validate strategy code

        Args:
            code: Python code to validate

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []

        # Check syntax
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            errors.append(f"Syntax error: {e}")
            return False, errors

        # Check for Strategy class
        has_strategy_class = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Check if class inherits from Strategy
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id == "Strategy":
                        has_strategy_class = True
                        break

        if not has_strategy_class:
            errors.append("Code must define a class that inherits from Strategy")

        is_valid = len(errors) == 0
        return is_valid, errors

    def _extract_strategy_class(self, code: str) -> type:
        """
        Extract strategy class from code

        Args:
            code: Python code containing strategy class

        Returns:
            Strategy class

        Raises:
            ValueError: If no strategy class found
        """
        # Create namespace for execution
        namespace = {}

        # Execute code to get class definition
        exec(code, namespace)

        # Find Strategy subclass
        from backtesting import Strategy as BaseStrategy

        for name, obj in namespace.items():
            if isinstance(obj, type) and issubclass(obj, BaseStrategy) and obj != BaseStrategy:
                return obj

        raise ValueError("No Strategy subclass found in code")

    def _extract_metrics(self, stats: Any) -> dict[str, Any]:
        """
        Extract metrics from backtest stats

        Args:
            stats: Backtest statistics object

        Returns:
            Dictionary of metrics
        """
        # Convert stats Series to dict
        if hasattr(stats, "to_dict"):
            return stats.to_dict()
        elif hasattr(stats, "_asdict"):
            return stats._asdict()
        else:
            # Fallback: convert to dict manually
            metrics = {}
            for key in dir(stats):
                if not key.startswith("_"):
                    try:
                        value = getattr(stats, key)
                        if not callable(value):
                            metrics[key] = value
                    except:
                        pass
            return metrics

    def _extract_equity_curve(self, stats: Any) -> list[float]:
        """
        Extract equity curve from backtest stats

        Args:
            stats: Backtest statistics object

        Returns:
            List of equity values
        """
        # Try to get equity curve
        if hasattr(stats, "_equity_curve"):
            equity = stats._equity_curve["Equity"]
            return equity.tolist() if hasattr(equity, "tolist") else list(equity)
        elif hasattr(stats, "Equity"):
            equity = stats.Equity
            return equity.tolist() if hasattr(equity, "tolist") else list(equity)
        else:
            return []
