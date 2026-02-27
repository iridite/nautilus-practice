"""Additional tests for backtest engine edge cases"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from langgraph.infrastructure.backtest.engine import BacktestEngine
from langgraph.domain.models.strategy import Strategy


class TestBacktestEngineEdgeCases:
    """Test edge cases and error paths in BacktestEngine"""

    def test_validate_code_with_syntax_error(self):
        """Test validation with syntax error"""
        engine = BacktestEngine()
        code = "def invalid syntax here"

        is_valid, errors = engine.validate_code(code)

        assert not is_valid
        assert len(errors) > 0
        assert "Syntax error" in errors[0]

    def test_validate_code_without_strategy_class(self):
        """Test validation without Strategy class"""
        engine = BacktestEngine()
        code = """
class NotAStrategy:
    pass
"""

        is_valid, errors = engine.validate_code(code)

        assert not is_valid
        assert len(errors) > 0
        assert "must define a class that inherits from Strategy" in errors[0]

    def test_extract_strategy_class_not_found(self):
        """Test _extract_strategy_class when no Strategy subclass exists"""
        engine = BacktestEngine()
        code = """
class NotAStrategy:
    pass
"""

        with pytest.raises(ValueError, match="No Strategy subclass found"):
            engine._extract_strategy_class(code)

    def test_extract_metrics_with_to_dict(self):
        """Test _extract_metrics with object that has to_dict method"""
        engine = BacktestEngine()

        mock_stats = Mock()
        mock_stats.to_dict.return_value = {"return": 0.15, "sharpe": 1.5}

        metrics = engine._extract_metrics(mock_stats)

        assert metrics == {"return": 0.15, "sharpe": 1.5}
        mock_stats.to_dict.assert_called_once()

    def test_extract_metrics_with_asdict(self):
        """Test _extract_metrics with object that has _asdict method"""
        engine = BacktestEngine()

        mock_stats = Mock()
        del mock_stats.to_dict  # Remove to_dict to test _asdict path
        mock_stats._asdict.return_value = {"return": 0.20, "sharpe": 2.0}

        metrics = engine._extract_metrics(mock_stats)

        assert metrics == {"return": 0.20, "sharpe": 2.0}
        mock_stats._asdict.assert_called_once()

    def test_extract_metrics_fallback(self):
        """Test _extract_metrics fallback path"""
        engine = BacktestEngine()

        # Create object without to_dict or _asdict
        class StatsObject:
            def __init__(self):
                self.return_value = 0.25
                self.sharpe_ratio = 2.5
                self._private = "hidden"

            def some_method(self):
                return "method"

        stats = StatsObject()
        metrics = engine._extract_metrics(stats)

        # Should include public attributes but not private or methods
        assert "return_value" in metrics
        assert "sharpe_ratio" in metrics
        assert "_private" not in metrics
        assert "some_method" not in metrics

    def test_extract_equity_curve_with_equity_curve_attr(self):
        """Test _extract_equity_curve with _equity_curve attribute"""
        engine = BacktestEngine()

        mock_equity = Mock()
        mock_equity.tolist.return_value = [10000, 10500, 11000]

        mock_stats = Mock()
        mock_stats._equity_curve = {"Equity": mock_equity}

        curve = engine._extract_equity_curve(mock_stats)

        assert curve == [10000, 10500, 11000]

    def test_extract_equity_curve_with_equity_attr(self):
        """Test _extract_equity_curve with Equity attribute"""
        engine = BacktestEngine()

        mock_equity = Mock()
        mock_equity.tolist.return_value = [10000, 10200, 10400]

        mock_stats = Mock()
        del mock_stats._equity_curve  # Remove _equity_curve to test Equity path
        mock_stats.Equity = mock_equity

        curve = engine._extract_equity_curve(mock_stats)

        assert curve == [10000, 10200, 10400]

    def test_extract_equity_curve_no_tolist(self):
        """Test _extract_equity_curve when equity doesn't have tolist"""
        engine = BacktestEngine()

        mock_stats = Mock()
        mock_stats._equity_curve = {"Equity": [10000, 10300, 10600]}

        curve = engine._extract_equity_curve(mock_stats)

        assert curve == [10000, 10300, 10600]

    def test_extract_equity_curve_not_found(self):
        """Test _extract_equity_curve when no equity data exists"""
        engine = BacktestEngine()

        mock_stats = Mock()
        del mock_stats._equity_curve
        del mock_stats.Equity

        curve = engine._extract_equity_curve(mock_stats)

        assert curve == []

    def test_run_with_invalid_code(self):
        """Test run method with invalid strategy code"""
        engine = BacktestEngine()
        strategy = Strategy(
            name="Invalid",
            description="Invalid strategy",
            code="def invalid syntax",
            config={}
        )

        with pytest.raises(ValueError, match="Invalid strategy code"):
            engine.run(strategy)

    def test_run_with_custom_parameters(self):
        """Test run method with custom cash and commission"""
        engine = BacktestEngine()

        valid_code = """
from backtesting import Strategy

class TestStrategy(Strategy):
    def init(self):
        pass

    def next(self):
        pass
"""

        strategy = Strategy(
            name="Test",
            description="Test strategy",
            code=valid_code,
            config={}
        )

        with patch('langgraph.infrastructure.backtest.engine.Backtest') as mock_backtest:
            mock_bt_instance = Mock()
            mock_stats = Mock()
            mock_stats.to_dict.return_value = {"return": 0.1}
            mock_stats._equity_curve = {"Equity": [10000, 11000]}
            mock_bt_instance.run.return_value = mock_stats
            mock_backtest.return_value = mock_bt_instance

            result = engine.run(strategy, cash=50000, commission=0.001)

            # Verify custom parameters were used
            mock_backtest.assert_called_once()
            call_kwargs = mock_backtest.call_args[1]
            assert call_kwargs['cash'] == 50000
            assert call_kwargs['commission'] == 0.001

    def test_default_parameters(self):
        """Test that default parameters are set correctly"""
        engine = BacktestEngine()

        assert engine.default_cash == 10000
        assert engine.default_commission == 0.002
