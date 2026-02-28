"""Tests for strategy code generator"""

from langgraph.infrastructure.code_gen.strategy_generator import StrategyCodeGenerator
from langgraph.domain.models.strategy import Strategy, StrategyStatus


class TestStrategyCodeGenerator:
    """Test strategy code generator"""

    def test_generator_initialization(self):
        """Test generator can be initialized"""
        generator = StrategyCodeGenerator()
        assert generator is not None

    def test_generate_strategy_code(self):
        """Test generating strategy code from domain model"""
        strategy = Strategy(
            strategy_id="test-001",
            name="TestStrategy",
            description="A test strategy",
            code="# placeholder",
            config={
                "indicators": ["SMA", "RSI"],
                "timeframe": "1h",
                "parameters": {"sma_period": 20, "rsi_period": 14},
            },
            status=StrategyStatus.DRAFT,
        )

        generator = StrategyCodeGenerator()
        code = generator.generate(strategy)

        # Verify generated code structure
        assert "class TestStrategy" in code
        assert "def init(self)" in code
        assert "def next(self)" in code
        assert "SMA" in code or "sma" in code.lower()
        assert "RSI" in code or "rsi" in code.lower()

    def test_generate_with_indicators(self):
        """Test code generation includes indicator initialization"""
        strategy = Strategy(
            strategy_id="test-002",
            name="IndicatorStrategy",
            description="Strategy with multiple indicators",
            code="# placeholder",
            config={
                "indicators": ["SMA", "EMA", "MACD"],
                "timeframe": "4h",
                "parameters": {"sma_period": 50, "ema_period": 20},
            },
            status=StrategyStatus.DRAFT,
        )

        generator = StrategyCodeGenerator()
        code = generator.generate(strategy)

        assert "SMA" in code or "sma" in code.lower()
        assert "EMA" in code or "ema" in code.lower()
        assert "MACD" in code or "macd" in code.lower()

    def test_generate_with_parameters(self):
        """Test code generation includes parameter definitions"""
        strategy = Strategy(
            strategy_id="test-003",
            name="ParamStrategy",
            description="Strategy with parameters",
            code="# placeholder",
            config={
                "indicators": ["ATR"],
                "timeframe": "1d",
                "parameters": {
                    "atr_period": 14,
                    "stop_loss_multiplier": 2.0,
                    "take_profit_multiplier": 3.0,
                },
            },
            status=StrategyStatus.DRAFT,
        )

        generator = StrategyCodeGenerator()
        code = generator.generate(strategy)

        # Check parameters are defined
        assert "atr_period" in code
        assert "stop_loss_multiplier" in code
        assert "take_profit_multiplier" in code

    def test_generate_valid_python_syntax(self):
        """Test generated code has valid Python syntax"""
        strategy = Strategy(
            strategy_id="test-004",
            name="SyntaxTestStrategy",
            description="Test syntax validation",
            code="# placeholder",
            config={"indicators": ["SMA"], "timeframe": "1h", "parameters": {"period": 20}},
            status=StrategyStatus.DRAFT,
        )

        generator = StrategyCodeGenerator()
        code = generator.generate(strategy)

        # Try to compile the code
        try:
            compile(code, "<string>", "exec")
            syntax_valid = True
        except SyntaxError:
            syntax_valid = False

        assert syntax_valid, "Generated code should have valid Python syntax"

    def test_generate_includes_backtesting_imports(self):
        """Test generated code includes necessary imports"""
        strategy = Strategy(
            strategy_id="test-005",
            name="ImportTestStrategy",
            description="Test imports",
            code="# placeholder",
            config={"indicators": ["SMA"], "timeframe": "1h", "parameters": {"period": 20}},
            status=StrategyStatus.DRAFT,
        )

        generator = StrategyCodeGenerator()
        code = generator.generate(strategy)

        # Check for backtesting.py imports
        assert "from backtesting import Strategy" in code or "import backtesting" in code
        assert "from backtesting.lib import crossover" in code or "import" in code

    def test_generate_with_empty_indicators(self):
        """Test code generation with no indicators"""
        strategy = Strategy(
            strategy_id="test-006",
            name="NoIndicatorStrategy",
            description="Strategy without indicators",
            code="# placeholder",
            config={"indicators": [], "timeframe": "1h", "parameters": {}},
            status=StrategyStatus.DRAFT,
        )

        generator = StrategyCodeGenerator()
        code = generator.generate(strategy)

        # Should still generate valid strategy structure
        assert "class NoIndicatorStrategy" in code
        assert "def init(self)" in code
        assert "def next(self)" in code

    def test_validate_generated_code(self):
        """Test code validation method"""
        strategy = Strategy(
            strategy_id="test-007",
            name="ValidationStrategy",
            description="Test validation",
            code="# placeholder",
            config={"indicators": ["SMA"], "timeframe": "1h", "parameters": {"period": 20}},
            status=StrategyStatus.DRAFT,
        )

        generator = StrategyCodeGenerator()
        code = generator.generate(strategy)

        # Validate the generated code
        is_valid, errors = generator.validate(code)

        assert is_valid, f"Generated code should be valid, errors: {errors}"
        assert len(errors) == 0
