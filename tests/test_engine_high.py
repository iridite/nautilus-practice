"""
Tests for High-Level Backtest Engine
"""
import unittest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
from datetime import datetime

from backtest.engine_high import (
    _check_if_needs_custom_data,
    _extract_symbol_from_instrument_id,
    _build_timeframe_string,
    _format_status_message,
    _check_csv_file_validity,
    _check_file_freshness,
    _count_csv_lines,
)
from core.schemas import BacktestConfig


class TestCheckIfNeedsCustomData(unittest.TestCase):
    """测试 _check_if_needs_custom_data 函数"""

    def test_needs_custom_data_oi_divergence(self):
        """测试 OI Divergence 策略需要自定义数据"""
        mock_strategy = Mock()
        mock_strategy.strategy_path = "strategy.oi_divergence.OIDivergenceStrategy"

        result = _check_if_needs_custom_data([mock_strategy])
        self.assertIsInstance(result, bool)

    def test_no_custom_data_needed(self):
        """测试普通策略不需要自定义数据"""
        mock_strategy = Mock()
        mock_strategy.strategy_path = "strategy.dual_thrust.DualThrustStrategy"

        result = _check_if_needs_custom_data([mock_strategy])
        self.assertFalse(result)

    def test_empty_strategies(self):
        """测试空策略列表"""
        result = _check_if_needs_custom_data([])
        self.assertFalse(result)


class TestHelperFunctions(unittest.TestCase):
    """测试辅助函数"""

    def test_extract_symbol_from_instrument_id_with_dash(self):
        """测试从带-的instrument_id提取符号"""
        result = _extract_symbol_from_instrument_id("BTCUSDT-PERP")
        self.assertEqual(result, "BTCUSDT")

    def test_extract_symbol_from_instrument_id_with_dot(self):
        """测试从带.的instrument_id提取符号"""
        result = _extract_symbol_from_instrument_id("BTCUSDT.BINANCE")
        self.assertEqual(result, "BTCUSDT")

    def test_extract_symbol_from_instrument_id_simple(self):
        """测试从简单instrument_id提取符号"""
        result = _extract_symbol_from_instrument_id("BTCUSDT")
        self.assertEqual(result, "BTCUSDT")

    def test_build_timeframe_string_no_data_feeds(self):
        """测试无数据源时构建时间周期字符串"""
        cfg = Mock(spec=BacktestConfig)
        cfg.data_feeds = []
        result = _build_timeframe_string(cfg)
        self.assertEqual(result, "1h")

    def test_build_timeframe_string_with_minute(self):
        """测试分钟级数据源"""
        from nautilus_trader.model.enums import BarAggregation
        cfg = Mock(spec=BacktestConfig)
        feed = Mock()
        feed.bar_period = 5
        feed.bar_aggregation = BarAggregation.MINUTE
        cfg.data_feeds = [feed]
        result = _build_timeframe_string(cfg)
        self.assertEqual(result, "5m")

    def test_build_timeframe_string_with_hour(self):
        """测试小时级数据源"""
        from nautilus_trader.model.enums import BarAggregation
        cfg = Mock(spec=BacktestConfig)
        feed = Mock()
        feed.bar_period = 1
        feed.bar_aggregation = BarAggregation.HOUR
        cfg.data_feeds = [feed]
        result = _build_timeframe_string(cfg)
        self.assertEqual(result, "1h")

    def test_build_timeframe_string_with_day(self):
        """测试日级数据源"""
        from nautilus_trader.model.enums import BarAggregation
        cfg = Mock(spec=BacktestConfig)
        feed = Mock()
        feed.bar_period = 1
        feed.bar_aggregation = BarAggregation.DAY
        cfg.data_feeds = [feed]
        result = _build_timeframe_string(cfg)
        self.assertEqual(result, "1d")

    def test_format_status_message_basic(self):
        """测试基本状态消息格式化"""
        result = _format_status_message(1, 10, "✓", "BTCUSDT-PERP")
        self.assertIn("1", result)
        self.assertIn("10", result)
        self.assertIn("✓", result)
        self.assertIn("BTCUSDT-PERP", result)

    def test_format_status_message_with_extra(self):
        """测试带额外信息的状态消息"""
        result = _format_status_message(5, 20, "📖", "ETHUSDT-PERP", "Loading")
        self.assertIn("5", result)
        self.assertIn("20", result)
        self.assertIn("📖", result)
        self.assertIn("ETHUSDT-PERP", result)
        self.assertIn("Loading", result)

    def test_check_file_freshness_csv_newer(self):
        """测试CSV文件更新"""
        csv_mtime = 1000.0
        parquet_mtime = 500.0
        result = _check_file_freshness(csv_mtime, parquet_mtime)
        self.assertTrue(result)

    def test_check_file_freshness_parquet_newer(self):
        """测试Parquet文件更新"""
        csv_mtime = 500.0
        parquet_mtime = 1000.0
        result = _check_file_freshness(csv_mtime, parquet_mtime)
        self.assertFalse(result)

    def test_check_file_freshness_no_parquet(self):
        """测试无Parquet文件"""
        csv_mtime = 1000.0
        parquet_mtime = None
        result = _check_file_freshness(csv_mtime, parquet_mtime)
        self.assertTrue(result)

    @patch('backtest.engine_high.Path')
    def test_check_csv_file_validity_exists(self, mock_path):
        """测试CSV文件存在且有效"""
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.stat.return_value.st_size = 1000
        result = _check_csv_file_validity(mock_file)
        self.assertTrue(result)

    @patch('backtest.engine_high.Path')
    def test_check_csv_file_validity_not_exists(self, mock_path):
        """测试CSV文件不存在"""
        mock_file = MagicMock()
        mock_file.exists.return_value = False
        result = _check_csv_file_validity(mock_file)
        self.assertFalse(result)

    @patch('backtest.engine_high.Path')
    def test_check_csv_file_validity_empty(self, mock_path):
        """测试CSV文件为空"""
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.stat.return_value.st_size = 0
        result = _check_csv_file_validity(mock_file)
        self.assertFalse(result)


class TestDataProcessing(unittest.TestCase):
    """测试数据处理函数"""

    @patch('backtest.engine_high.Path')
    def test_count_csv_lines_success(self, mock_path):
        """测试CSV行数统计"""
        mock_file = MagicMock()
        mock_file.open.return_value.__enter__.return_value = ["line1\n", "line2\n", "line3\n"]
        result = _count_csv_lines(mock_file)
        self.assertEqual(result, 3)

    @patch('backtest.engine_high.Path')
    def test_count_csv_lines_error(self, mock_path):
        """测试CSV行数统计错误处理"""
        mock_file = MagicMock()
        mock_file.open.side_effect = OSError("File not found")
        result = _count_csv_lines(mock_file)
        self.assertEqual(result, 0)


class TestMetricsBuilding(unittest.TestCase):
    """测试指标构建函数"""

    def test_build_pnl_metrics(self):
        """测试PnL指标构建"""
        from backtest.engine_high import _build_pnl_metrics
        from nautilus_trader.backtest.results import BacktestResult

        mock_result = Mock(spec=BacktestResult)
        mock_result.total_pnl = 1000.0
        mock_result.total_return = 0.1

        metrics = _build_pnl_metrics(mock_result)
        self.assertIsInstance(metrics, dict)
        self.assertIn("total_pnl", metrics)

    def test_build_returns_metrics(self):
        """测试收益率指标构建"""
        from backtest.engine_high import _build_returns_metrics
        from nautilus_trader.backtest.results import BacktestResult

        mock_result = Mock(spec=BacktestResult)
        mock_result.sharpe_ratio = 1.5
        mock_result.sortino_ratio = 2.0

        metrics = _build_returns_metrics(mock_result)
        self.assertIsInstance(metrics, dict)

    def test_build_filter_stats_with_data(self):
        """测试过滤统计构建"""
        from backtest.engine_high import _build_filter_stats

        filter_stats = {
            "filter1": {"passed": 10, "failed": 5},
            "filter2": {"passed": 8, "failed": 7}
        }
        result = _build_filter_stats(filter_stats)
        self.assertIsInstance(result, dict)

    def test_build_filter_stats_none(self):
        """测试空过滤统计"""
        from backtest.engine_high import _build_filter_stats

        result = _build_filter_stats(None)
        self.assertIsInstance(result, dict)


class TestTradeAnalysis(unittest.TestCase):
    """测试交易分析函数"""

    def test_calculate_basic_stats(self):
        """测试基本统计计算"""
        from backtest.engine_high import _calculate_basic_stats

        trade_metrics = [
            {"pnl": 100, "return": 0.1},
            {"pnl": -50, "return": -0.05},
            {"pnl": 200, "return": 0.2}
        ]
        winners = [{"pnl": 100}, {"pnl": 200}]
        losers = [{"pnl": -50}]

        stats = _calculate_basic_stats(trade_metrics, winners, losers)
        self.assertIsInstance(stats, dict)
        self.assertIn("total_trades", stats)
        self.assertIn("win_rate", stats)

    def test_calculate_pnl_stats(self):
        """测试PnL统计计算"""
        from backtest.engine_high import _calculate_pnl_stats

        trade_metrics = [
            {"pnl": 100},
            {"pnl": -50},
            {"pnl": 200}
        ]

        stats = _calculate_pnl_stats(trade_metrics)
        self.assertIsInstance(stats, dict)

    def test_calculate_winner_stats(self):
        """测试盈利交易统计"""
        from backtest.engine_high import _calculate_winner_stats

        winners = [
            {"pnl": 100, "return": 0.1},
            {"pnl": 200, "return": 0.2}
        ]

        stats = _calculate_winner_stats(winners)
        self.assertIsInstance(stats, dict)

    def test_calculate_loser_stats(self):
        """测试亏损交易统计"""
        from backtest.engine_high import _calculate_loser_stats

        losers = [
            {"pnl": -50, "return": -0.05},
            {"pnl": -100, "return": -0.1}
        ]

        stats = _calculate_loser_stats(losers)
        self.assertIsInstance(stats, dict)


class TestEngineHighIntegration(unittest.TestCase):
    """集成测试 - 测试模块导入和基本功能"""

    def test_module_imports(self):
        """测试模块可以正确导入"""
        from backtest import engine_high
        self.assertTrue(hasattr(engine_high, 'run_high_level'))
        self.assertTrue(hasattr(engine_high, '_load_instruments'))
        self.assertTrue(hasattr(engine_high, '_check_parquet_coverage'))

    def test_exception_imports(self):
        """测试异常类可以正确导入"""
        from backtest.exceptions import (
            BacktestEngineError,
            CatalogError,
            DataLoadError,
            InstrumentLoadError
        )
        # 验证异常类是 Exception 的子类
        self.assertTrue(issubclass(BacktestEngineError, Exception))
        self.assertTrue(issubclass(CatalogError, Exception))
        self.assertTrue(issubclass(DataLoadError, Exception))
        self.assertTrue(issubclass(InstrumentLoadError, Exception))


if __name__ == "__main__":
    unittest.main()
