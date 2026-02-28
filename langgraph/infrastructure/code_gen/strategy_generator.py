"""Strategy code generator for backtesting.py framework"""

import ast
from typing import Tuple
from langgraph.domain.models.strategy import Strategy


class StrategyCodeGenerator:
    """Generates Python code for trading strategies"""

    def __init__(self):
        """Initialize the code generator"""
        pass

    def generate(self, strategy: Strategy) -> str:
        """
        Generate Python code for a strategy

        Args:
            strategy: Strategy domain model

        Returns:
            Generated Python code as string
        """
        # Build imports
        imports = self._generate_imports()

        # Build class definition
        class_def = self._generate_class_definition(strategy)

        # Build init method
        init_method = self._generate_init_method(strategy)

        # Build next method
        next_method = self._generate_next_method(strategy)

        # Combine all parts
        code_parts = [imports, "", "", class_def, init_method, "", next_method]

        return "\n".join(code_parts)

    def _generate_imports(self) -> str:
        """Generate import statements"""
        return """from backtesting import Strategy
from backtesting.lib import crossover
from backtesting.test import SMA, GOOG"""

    def _generate_class_definition(self, strategy: Strategy) -> str:
        """Generate class definition"""
        return f"class {strategy.name}(Strategy):"

    def _generate_init_method(self, strategy: Strategy) -> str:
        """Generate init method with indicators and parameters"""
        lines = ["    def init(self):"]
        lines.append('        """Initialize strategy indicators"""')

        # Get config data
        indicators = strategy.config.get("indicators", [])
        parameters = strategy.config.get("parameters", {})

        # Add parameters as class attributes
        if parameters:
            for param_name, param_value in parameters.items():
                lines.append(f"        self.{param_name} = {param_value}")

        # Add indicator initialization
        if indicators:
            for indicator in indicators:
                indicator_lower = indicator.lower()

                if indicator_lower == "sma":
                    period = parameters.get("sma_period", 20)
                    lines.append(f"        self.sma = self.I(SMA, self.data.Close, {period})")

                elif indicator_lower == "ema":
                    period = parameters.get("ema_period", 20)
                    lines.append(
                        f"        self.ema = self.I(SMA, self.data.Close, {period})  # Using SMA as placeholder"
                    )

                elif indicator_lower == "rsi":
                    period = parameters.get("rsi_period", 14)
                    lines.append(f"        # RSI indicator (period={period})")
                    lines.append(f"        self.rsi_period = {period}")

                elif indicator_lower == "macd":
                    lines.append("        # MACD indicator")
                    lines.append("        self.macd_fast = 12")
                    lines.append("        self.macd_slow = 26")

                elif indicator_lower == "atr":
                    period = parameters.get("atr_period", 14)
                    lines.append(f"        # ATR indicator (period={period})")
                    lines.append(f"        self.atr_period = {period}")

        # If no indicators, add pass
        if len(lines) == 2:
            lines.append("        pass")

        return "\n".join(lines)

    def _generate_next_method(self, strategy: Strategy) -> str:
        """Generate next method with trading logic"""
        lines = ["    def next(self):"]
        lines.append('        """Execute trading logic on each bar"""')

        # Get indicators from config
        indicators = strategy.config.get("indicators", [])

        # Add basic trading logic based on indicators
        if indicators:
            indicators_lower = [ind.lower() for ind in indicators]

            if "sma" in indicators_lower:
                lines.append("        # Simple moving average crossover logic")
                lines.append("        if crossover(self.data.Close, self.sma):")
                lines.append("            self.buy()")
                lines.append("        elif crossover(self.sma, self.data.Close):")
                lines.append("            self.position.close()")

            elif "rsi" in indicators_lower:
                lines.append("        # RSI-based logic (placeholder)")
                lines.append("        # if rsi < 30: self.buy()")
                lines.append("        # elif rsi > 70: self.position.close()")
                lines.append("        pass")

            else:
                lines.append("        # Trading logic placeholder")
                lines.append("        pass")
        else:
            lines.append("        # No indicators defined")
            lines.append("        pass")

        return "\n".join(lines)

    def validate(self, code: str) -> Tuple[bool, list[str]]:
        """
        Validate generated code

        Args:
            code: Python code to validate

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []

        # Check syntax
        try:
            ast.parse(code)
        except SyntaxError as e:
            errors.append(f"Syntax error: {e}")
            return False, errors

        # Check required components
        if "class" not in code:
            errors.append("Missing class definition")

        if "def init(self)" not in code:
            errors.append("Missing init method")

        if "def next(self)" not in code:
            errors.append("Missing next method")

        if "from backtesting import Strategy" not in code:
            errors.append("Missing backtesting imports")

        is_valid = len(errors) == 0
        return is_valid, errors
