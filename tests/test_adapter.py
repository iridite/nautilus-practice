"""
Tests for Config Adapter
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from core.adapter import ConfigAdapter


class TestConfigAdapter(unittest.TestCase):
    @patch("core.adapter.ConfigLoader")
    def setUp(self, mock_loader):
        self.adapter = ConfigAdapter()

    def test_initialization(self):
        self.assertIsNotNone(self.adapter.loader)

    @patch("core.adapter.ConfigLoader")
    def test_get_venue(self, mock_loader):
        adapter = ConfigAdapter()
        adapter.env_config = Mock()
        adapter.env_config.trading.venue = "BINANCE"
        self.assertEqual(adapter.get_venue(), "BINANCE")

    @patch("core.adapter.ConfigLoader")
    def test_get_start_date(self, mock_loader):
        adapter = ConfigAdapter()
        adapter.env_config = Mock()
        adapter.env_config.backtest.start_date = "2024-01-01"
        self.assertEqual(adapter.get_start_date(), "2024-01-01")

    @patch("core.adapter.ConfigLoader")
    def test_get_end_date(self, mock_loader):
        adapter = ConfigAdapter()
        adapter.env_config = Mock()
        adapter.env_config.backtest.end_date = "2024-12-31"
        self.assertEqual(adapter.get_end_date(), "2024-12-31")

    @patch("core.adapter.ConfigLoader")
    def test_get_initial_balances(self, mock_loader):
        adapter = ConfigAdapter()
        adapter.env_config = Mock()
        adapter.env_config.trading.initial_balance = 10000
        balances = adapter.get_initial_balances()
        self.assertEqual(len(balances), 1)
        self.assertEqual(str(balances[0].as_decimal()), "10000")

    @patch("core.adapter.ConfigLoader")
    def test_get_main_timeframe(self, mock_loader):
        adapter = ConfigAdapter()
        adapter.active_config = Mock()
        adapter.active_config.timeframe = None
        adapter.env_config = Mock()
        adapter.env_config.trading = Mock()
        adapter.env_config.trading.main_timeframe = "1h"
        self.assertEqual(adapter.get_main_timeframe(), "1h")

    @patch("core.adapter.ConfigLoader")
    def test_get_trend_timeframe(self, mock_loader):
        adapter = ConfigAdapter()
        adapter.env_config = Mock()
        adapter.env_config.trading = Mock()
        adapter.env_config.trading.trend_timeframe = "4h"
        self.assertEqual(adapter.get_trend_timeframe(), "4h")

    @patch("core.adapter.ConfigLoader")
    def test_get_primary_symbol(self, mock_loader):
        adapter = ConfigAdapter()
        adapter.active_config = Mock()
        adapter.active_config.primary_symbol = "BTCUSDT"
        self.assertEqual(adapter.get_primary_symbol(), "BTCUSDT")

    @patch("core.adapter.ConfigLoader")
    def test_get_strategy_name(self, mock_loader):
        adapter = ConfigAdapter()
        adapter.strategy_config = Mock()
        adapter.strategy_config.name = "DualThrust"
        self.assertEqual(adapter.get_strategy_name(), "DualThrust")

    @patch("core.adapter.ConfigLoader")
    def test_get_strategy_module_path(self, mock_loader):
        adapter = ConfigAdapter()
        adapter.strategy_config = Mock()
        adapter.strategy_config.module_path = "strategy.dual_thrust"
        self.assertEqual(adapter.get_strategy_module_path(), "strategy.dual_thrust")

    @patch("core.adapter.ConfigLoader")
    def test_get_strategy_config_class(self, mock_loader):
        adapter = ConfigAdapter()
        adapter.strategy_config = Mock()
        adapter.strategy_config.config_class = "DualThrustConfig"
        self.assertEqual(adapter.get_strategy_config_class(), "DualThrustConfig")

    @patch("core.adapter.ConfigLoader")
    def test_get_strategy_parameters(self, mock_loader):
        adapter = ConfigAdapter()
        adapter.strategy_config = Mock()
        adapter.strategy_config.parameters = {"k1": 0.5, "k2": 0.5}
        params = adapter.get_strategy_parameters()
        self.assertEqual(params["k1"], 0.5)
        self.assertEqual(params["k2"], 0.5)


class TestAdapterHelperMethods(unittest.TestCase):
    """测试适配器辅助方法"""

    @patch("core.adapter.ConfigLoader")
    def test_extract_symbols_from_universe(self, mock_loader):
        adapter = ConfigAdapter()
        universe_data = {"2024-01-01": ["BTCUSDT", "ETHUSDT"], "2024-01-02": ["BTCUSDT", "SOLUSDT"]}
        symbols = adapter._extract_symbols_from_universe(universe_data)
        self.assertIsInstance(symbols, set)
        self.assertIn("BTCUSDT", symbols)
        self.assertIn("ETHUSDT", symbols)
        self.assertIn("SOLUSDT", symbols)

    @patch("core.adapter.ConfigLoader")
    def test_get_universe_file_path(self, mock_loader):
        adapter = ConfigAdapter()
        path = adapter._get_universe_file_path(10, "1d")
        self.assertIsInstance(path, Path)
        self.assertIn("universe_10_1d", str(path))

    @patch("core.adapter.ConfigLoader")
    def test_restore_instrument_id(self, mock_loader):
        adapter = ConfigAdapter()
        adapter.env_config = Mock()
        adapter.env_config.trading = Mock()
        adapter.env_config.trading.venue = "BINANCE"
        adapter.env_config.trading.instrument_type = "SWAP"

        result = adapter._restore_instrument_id("BTCUSDT")
        # 格式应该是 BTC-USDT-SWAP.BINANCE
        self.assertIn("BTC", result)
        self.assertIn("USDT", result)
        self.assertIn("BINANCE", result)

    @patch("core.adapter.ConfigLoader")
    def test_get_required_timeframes(self, mock_loader):
        adapter = ConfigAdapter()
        adapter.strategy_config = Mock()
        adapter.strategy_config.parameters = {"timeframes": ["1h", "4h"]}

        timeframes = adapter.get_required_timeframes()
        self.assertIsInstance(timeframes, list)
        self.assertIn("1h", timeframes)


if __name__ == "__main__":
    unittest.main()
