"""
测试策略数据依赖检查模块
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from strategy.core.dependency_checker import (
    check_strategy_data_dependencies,
    extract_strategy_symbols,
)


class TestExtractStrategySymbols(unittest.TestCase):
    """测试提取策略符号功能"""

    def test_extract_from_data_feeds(self):
        """测试从 data_feeds 提取符号"""
        strategy_config = MagicMock()
        feed1 = MagicMock()
        feed1.csv_file_name = "BTCUSDT/binance-BTCUSDT-PERP-1h.csv"
        feed2 = MagicMock()
        feed2.csv_file_name = "ETHUSDT/binance-ETHUSDT-PERP-1h.csv"
        strategy_config.data_feeds = [feed1, feed2]
        strategy_config.instrument_id = None  # 明确设置为 None

        symbols = extract_strategy_symbols(strategy_config)

        self.assertEqual(len(symbols), 2)
        self.assertIn("BTCUSDT", symbols)
        self.assertIn("ETHUSDT", symbols)

    def test_extract_from_universe_symbols(self):
        """测试从 universe_symbols 提取符号"""
        strategy_config = MagicMock()
        strategy_config.data_feeds = None
        strategy_config.instrument_id = None  # 明确设置为 None

        universe_symbols = {"BTCUSDT:BINANCE", "ETHUSDT:BINANCE"}

        symbols = extract_strategy_symbols(strategy_config, universe_symbols)

        self.assertEqual(len(symbols), 2)
        self.assertIn("BTCUSDT", symbols)
        self.assertIn("ETHUSDT", symbols)

    def test_extract_from_instrument_id(self):
        """测试从 instrument_id 提取符号"""
        strategy_config = MagicMock()
        strategy_config.data_feeds = None
        strategy_config.instrument_id = "BINANCE.BTCUSDT-PERP.BINANCE"

        symbols = extract_strategy_symbols(strategy_config)

        self.assertEqual(len(symbols), 1)
        self.assertIn("BTCUSDT", symbols)

    def test_extract_combined_sources(self):
        """测试从多个来源提取符号"""
        strategy_config = MagicMock()

        feed1 = MagicMock()
        feed1.csv_file_name = "BTCUSDT/binance-BTCUSDT-PERP-1h.csv"
        strategy_config.data_feeds = [feed1]
        strategy_config.instrument_id = "BINANCE.ETHUSDT-PERP.BINANCE"

        universe_symbols = {"SOLUSDT:BINANCE"}

        symbols = extract_strategy_symbols(strategy_config, universe_symbols)

        self.assertEqual(len(symbols), 3)
        self.assertIn("BTCUSDT", symbols)
        self.assertIn("ETHUSDT", symbols)
        self.assertIn("SOLUSDT", symbols)

    def test_extract_with_invalid_data_feeds(self):
        """测试处理无效的 data_feeds"""
        strategy_config = MagicMock()

        feed1 = MagicMock()
        feed1.csv_file_name = "invalid_format"
        strategy_config.data_feeds = [feed1]

        # 不应该抛出异常
        symbols = extract_strategy_symbols(strategy_config)

        # 可能为空或包含 "invalid_format"
        self.assertIsInstance(symbols, set)

    def test_extract_with_no_sources(self):
        """测试没有任何数据源"""
        strategy_config = MagicMock()
        strategy_config.data_feeds = None
        strategy_config.instrument_id = None

        symbols = extract_strategy_symbols(strategy_config)

        self.assertEqual(len(symbols), 0)

    def test_extract_with_empty_data_feeds(self):
        """测试空的 data_feeds"""
        strategy_config = MagicMock()
        strategy_config.data_feeds = []
        strategy_config.instrument_id = None  # 明确设置为 None

        symbols = extract_strategy_symbols(strategy_config)

        self.assertEqual(len(symbols), 0)


class TestCheckStrategyDataDependencies(unittest.TestCase):
    """测试策略数据依赖检查功能"""

    def setUp(self):
        """设置测试环境"""
        self.base_dir = Path("/tmp/test_data")
        self.start_date = "2024-01-01"
        self.end_date = "2024-01-10"

    @patch('strategy.core.dependency_checker.check_oi_data_exists')
    @patch('strategy.core.dependency_checker.check_funding_data_exists')
    def test_no_data_types(self, mock_funding, mock_oi):
        """测试没有数据类型要求"""
        strategy_config = MagicMock()
        strategy_config.data_types = []

        tasks = check_strategy_data_dependencies(
            strategy_config, self.start_date, self.end_date, self.base_dir
        )

        self.assertEqual(tasks["missing_count"], 0)
        self.assertEqual(len(tasks["oi_tasks"]), 0)
        self.assertEqual(len(tasks["funding_tasks"]), 0)
        mock_oi.assert_not_called()
        mock_funding.assert_not_called()

    @patch('strategy.core.dependency_checker.check_oi_data_exists')
    def test_check_oi_data_all_exists(self, mock_check_oi):
        """测试 OI 数据全部存在"""
        mock_check_oi.return_value = (True, [])

        strategy_config = MagicMock()
        strategy_config.data_types = ["oi"]
        feed1 = MagicMock()
        feed1.csv_file_name = "BTCUSDT/binance-BTCUSDT-PERP-1h.csv"
        strategy_config.data_feeds = [feed1]

        tasks = check_strategy_data_dependencies(
            strategy_config, self.start_date, self.end_date, self.base_dir
        )

        self.assertEqual(tasks["missing_count"], 0)
        self.assertEqual(len(tasks["oi_tasks"]), 0)
        mock_check_oi.assert_called_once()

    @patch('strategy.core.dependency_checker.check_oi_data_exists')
    def test_check_oi_data_missing(self, mock_check_oi):
        """测试 OI 数据缺失"""
        mock_check_oi.return_value = (
            False,
            ["data/raw/BTCUSDT/oi_binance_BTCUSDT_1h.csv"]
        )

        strategy_config = MagicMock()
        strategy_config.data_types = ["oi"]
        feed1 = MagicMock()
        feed1.csv_file_name = "BTCUSDT/binance-BTCUSDT-PERP-1h.csv"
        strategy_config.data_feeds = [feed1]

        tasks = check_strategy_data_dependencies(
            strategy_config, self.start_date, self.end_date, self.base_dir
        )

        self.assertGreater(tasks["missing_count"], 0)
        self.assertGreater(len(tasks["oi_tasks"]), 0)

    @patch('strategy.core.dependency_checker.check_funding_data_exists')
    def test_check_funding_data_all_exists(self, mock_check_funding):
        """测试 Funding Rate 数据全部存在"""
        mock_check_funding.return_value = (True, [])

        strategy_config = MagicMock()
        strategy_config.data_types = ["funding"]
        feed1 = MagicMock()
        feed1.csv_file_name = "BTCUSDT/binance-BTCUSDT-PERP-1h.csv"
        strategy_config.data_feeds = [feed1]

        tasks = check_strategy_data_dependencies(
            strategy_config, self.start_date, self.end_date, self.base_dir
        )

        self.assertEqual(tasks["missing_count"], 0)
        self.assertEqual(len(tasks["funding_tasks"]), 0)
        mock_check_funding.assert_called_once()

    @patch('strategy.core.dependency_checker.check_funding_data_exists')
    def test_check_funding_data_missing(self, mock_check_funding):
        """测试 Funding Rate 数据缺失"""
        mock_check_funding.return_value = (
            False,
            ["data/raw/BTCUSDT/funding_binance_BTCUSDT.csv"]
        )

        strategy_config = MagicMock()
        strategy_config.data_types = ["funding"]
        feed1 = MagicMock()
        feed1.csv_file_name = "BTCUSDT/binance-BTCUSDT-PERP-1h.csv"
        strategy_config.data_feeds = [feed1]

        tasks = check_strategy_data_dependencies(
            strategy_config, self.start_date, self.end_date, self.base_dir
        )

        self.assertGreater(tasks["missing_count"], 0)
        self.assertGreater(len(tasks["funding_tasks"]), 0)

    @patch('strategy.core.dependency_checker.check_oi_data_exists')
    @patch('strategy.core.dependency_checker.check_funding_data_exists')
    def test_check_multiple_data_types(self, mock_funding, mock_oi):
        """测试检查多种数据类型"""
        mock_oi.return_value = (False, ["data/raw/BTCUSDT/oi_binance_BTCUSDT_1h.csv"])
        mock_funding.return_value = (False, ["data/raw/BTCUSDT/funding_binance_BTCUSDT.csv"])

        strategy_config = MagicMock()
        strategy_config.data_types = ["oi", "funding"]
        feed1 = MagicMock()
        feed1.csv_file_name = "BTCUSDT/binance-BTCUSDT-PERP-1h.csv"
        strategy_config.data_feeds = [feed1]

        tasks = check_strategy_data_dependencies(
            strategy_config, self.start_date, self.end_date, self.base_dir
        )

        self.assertGreater(tasks["missing_count"], 0)
        self.assertGreater(len(tasks["oi_tasks"]), 0)
        self.assertGreater(len(tasks["funding_tasks"]), 0)
        mock_oi.assert_called_once()
        mock_funding.assert_called_once()

    def test_no_symbols_extracted(self):
        """测试没有提取到符号"""
        strategy_config = MagicMock()
        strategy_config.data_types = ["oi"]
        strategy_config.data_feeds = None
        strategy_config.instrument_id = None

        tasks = check_strategy_data_dependencies(
            strategy_config, self.start_date, self.end_date, self.base_dir
        )

        self.assertEqual(tasks["missing_count"], 0)
        self.assertEqual(len(tasks["oi_tasks"]), 0)

    @patch('strategy.core.dependency_checker.check_oi_data_exists')
    def test_with_universe_symbols(self, mock_check_oi):
        """测试使用 universe_symbols"""
        mock_check_oi.return_value = (True, [])

        strategy_config = MagicMock()
        strategy_config.data_types = ["oi"]
        strategy_config.data_feeds = None
        strategy_config.instrument_id = None  # 明确设置为 None

        universe_symbols = {"BTCUSDT:BINANCE", "ETHUSDT:BINANCE"}

        check_strategy_data_dependencies(
            strategy_config, self.start_date, self.end_date,
            self.base_dir, universe_symbols
        )

        # 应该检查 universe 中的符号
        mock_check_oi.assert_called_once()
        call_args = mock_check_oi.call_args[0]
        symbols_checked = call_args[0]
        self.assertEqual(len(symbols_checked), 2)

    @patch('strategy.core.dependency_checker.check_oi_data_exists')
    def test_invalid_file_path_handling(self, mock_check_oi):
        """测试处理无效的文件路径"""
        mock_check_oi.return_value = (
            False,
            ["invalid_path"]  # 无法从中提取符号
        )

        strategy_config = MagicMock()
        strategy_config.data_types = ["oi"]
        feed1 = MagicMock()
        feed1.csv_file_name = "BTCUSDT/binance-BTCUSDT-PERP-1h.csv"
        strategy_config.data_feeds = [feed1]

        # 不应该抛出异常
        tasks = check_strategy_data_dependencies(
            strategy_config, self.start_date, self.end_date, self.base_dir
        )

        # 应该有 oi_tasks 但 missing_count 可能为 0（因为路径无效）
        self.assertIsInstance(tasks, dict)


if __name__ == "__main__":
    unittest.main()
