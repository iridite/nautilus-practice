"""Tests for backtest engine wrapper"""
import pytest
from unittest.mock import Mock, patch
from langgraph.infrastructure.backtest.engine import BacktestEngine
from langgraph.domain.models.strategy import Strategy, StrategyStatus


class TestBacktestEngine:
    """Test backtest engine wrapper"""

    def test_engine_initialization(self):
        """Test engine can be initialized"""
        engine = BacktestEngine()
        assert engine is not None

    def test_run_backtest_with_valid_strategy(self):
        """Test running backtest with valid strategy code"""
        strategy = Strategy(
            strategy_id="test-001",
            name="TestStrategy",
            description="A test strategy",
            code="""
from backtesting import Strategy
from backtesting.lib import crossover
from backtesting.test import SMA

class TestStrategy(Strategy):
    def init(self):
        self.sma = self.I(SMA, self.data.Close, 20)

    def next(self):
        if crossover(self.data.Close, self.sma):
            self.buy()
        elif crossover(self.sma, self.data.Close):
            self.position.close()
""",
            config={"indicators": ["SMA"], "parameters": {"sma_period": 20}},
            status=StrategyStatus.DRAFT
        )

        engine = BacktestEngine()
        result = engine.run(strategy)

        # Verify result structure
        assert result is not None
        assert "metrics" in result
        assert "equity_curve" in result
        assert isinstance(result["metrics"], dict)

    def test_run_backtest_with_custom_data(self):
        """Test running backtest with custom data"""
        strategy = Strategy(
            strategy_id="test-002",
            name="CustomDataStrategy",
            description="Strategy with custom data",
            code="""
from backtesting import Strategy

class CustomDataStrategy(Strategy):
    def init(self):
        pass

    def next(self):
        pass
""",
            config={},
            status=StrategyStatus.DRAFT
        )

        engine = BacktestEngine()

        # Use default GOOG data (testing that data parameter works)
        from backtesting.test import GOOG
        result = engine.run(strategy, data=GOOG)
        assert result is not None

    def test_run_backtest_with_parameters(self):
        """Test running backtest with custom parameters"""
        strategy = Strategy(
            strategy_id="test-003",
            name="ParamStrategy",
            description="Strategy with parameters",
            code="""
from backtesting import Strategy

class ParamStrategy(Strategy):
    def init(self):
        pass

    def next(self):
        pass
""",
            config={},
            status=StrategyStatus.DRAFT
        )

        engine = BacktestEngine()
        result = engine.run(
            strategy,
            cash=100000,
            commission=0.002
        )

        assert result is not None
        assert "metrics" in result

    def test_extract_metrics_from_result(self):
        """Test extracting metrics from backtest result"""
        strategy = Strategy(
            strategy_id="test-004",
            name="MetricsStrategy",
            description="Test metrics extraction",
            code="""
from backtesting import Strategy

class MetricsStrategy(Strategy):
    def init(self):
        pass

    def next(self):
        pass
""",
            config={},
            status=StrategyStatus.DRAFT
        )

        engine = BacktestEngine()
        result = engine.run(strategy)

        metrics = result["metrics"]

        # Check for common metrics
        assert "Return [%]" in metrics or "return" in str(metrics).lower()
        assert isinstance(metrics, dict)

    def test_run_backtest_with_invalid_code(self):
        """Test running backtest with invalid strategy code"""
        strategy = Strategy(
            strategy_id="test-005",
            name="InvalidStrategy",
            description="Invalid strategy code",
            code="invalid python code !!!",
            config={},
            status=StrategyStatus.DRAFT
        )

        engine = BacktestEngine()

        with pytest.raises(Exception):
            engine.run(strategy)

    def test_run_backtest_with_missing_strategy_class(self):
        """Test running backtest with code missing Strategy class"""
        strategy = Strategy(
            strategy_id="test-006",
            name="NoClassStrategy",
            description="Code without Strategy class",
            code="""
def some_function():
    pass
""",
            config={},
            status=StrategyStatus.DRAFT
        )

        engine = BacktestEngine()

        with pytest.raises(Exception):
            engine.run(strategy)

    def test_validate_strategy_code(self):
        """Test strategy code validation"""
        valid_code = """
from backtesting import Strategy

class TestStrategy(Strategy):
    def init(self):
        pass

    def next(self):
        pass
"""

        engine = BacktestEngine()
        is_valid, errors = engine.validate_code(valid_code)

        assert is_valid
        assert len(errors) == 0

    def test_validate_invalid_strategy_code(self):
        """Test validation of invalid strategy code"""
        invalid_code = "invalid python code"

        engine = BacktestEngine()
        is_valid, errors = engine.validate_code(invalid_code)

        assert not is_valid
        assert len(errors) > 0
