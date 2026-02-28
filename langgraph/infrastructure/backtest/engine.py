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

    def _validate_code_safety(self, code: str) -> None:
        """
        Validate code doesn't contain dangerous operations

        Args:
            code: Python code to validate

        Raises:
            ValueError: If dangerous patterns detected
        """
        # List of dangerous patterns that could lead to arbitrary code execution
        dangerous_patterns = [
            ('import os', 'OS module access'),
            ('import sys', 'System module access'),
            ('import subprocess', 'Subprocess execution'),
            ('__import__', 'Dynamic imports'),
            ('eval(', 'Eval function'),
            ('exec(', 'Exec function'),
            ('compile(', 'Compile function'),
            ('open(', 'File operations'),
            ('file(', 'File operations'),
            ('input(', 'User input'),
            ('raw_input(', 'User input'),
            ('__builtins__', 'Builtins access'),
            ('globals(', 'Globals access'),
            ('locals(', 'Locals access'),
            ('vars(', 'Vars access'),
            ('dir(', 'Dir access'),
            ('delattr(', 'Attribute deletion'),
            ('__dict__', 'Dict access'),
            ('__class__', 'Class access'),
            ('__bases__', 'Bases access'),
            ('__subclasses__', 'Subclasses access'),
        ]

        for pattern, description in dangerous_patterns:
            if pattern in code:
                raise ValueError(
                    f"Dangerous pattern detected: {description} ({pattern}). "
                    "Strategy code must not contain system-level operations."
                )

    def _extract_strategy_class(self, code: str) -> type:
        """
        Extract strategy class from code

        Args:
            code: Python code containing strategy class

        Returns:
            Strategy class

        Raises:
            ValueError: If no strategy class found or code contains dangerous patterns
        """
        # Validate code safety before execution
        self._validate_code_safety(code)

        # Create restricted namespace for execution
        # Only allow safe builtins to prevent arbitrary code execution
        restricted_globals = {
            '__builtins__': {
                'range': range,
                'len': len,
                'str': str,
                'int': int,
                'float': float,
                'bool': bool,
                'list': list,
                'dict': dict,
                'tuple': tuple,
                'set': set,
                'min': min,
                'max': max,
                'sum': sum,
                'abs': abs,
                'round': round,
                'enumerate': enumerate,
                'zip': zip,
                'map': map,
                'filter': filter,
                'sorted': sorted,
                'reversed': reversed,
                'isinstance': isinstance,
                'issubclass': issubclass,
                'hasattr': hasattr,
                'getattr': getattr,
                'setattr': setattr,
                'type': type,
                'property': property,
                'staticmethod': staticmethod,
                'classmethod': classmethod,
                'super': super,
                'Exception': Exception,
                'ValueError': ValueError,
                'TypeError': TypeError,
                'AttributeError': AttributeError,
                'KeyError': KeyError,
                'IndexError': IndexError,
                'RuntimeError': RuntimeError,
            }
        }
        namespace = {}

        # Execute code in restricted environment
        exec(code, restricted_globals, namespace)

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
                    except (AttributeError, TypeError) as e:
                        # Log but continue - some attributes may not be accessible
                        import logging
                        logging.debug(f"Could not extract metric '{key}': {e}")
                        continue
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
