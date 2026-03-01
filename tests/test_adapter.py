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
        adapter.strategy_config = Mock()
        adapter.strategy_config.parameters = {}
        adapter.env_config = Mock()
        adapter.env_config.timeframes = {"main": "1h"}
        self.assertEqual(adapter.get_main_timeframe(), "1h")

    @patch("core.adapter.ConfigLoader")
    def test_get_trend_timeframe(self, mock_loader):
        adapter = ConfigAdapter()
        adapter.env_config = Mock()
        adapter.env_config.timeframes = {"trend": "4h"}
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
        adapter.env_config = Mock()
        adapter.env_config.backtest = Mock()
        adapter.env_config.backtest.start_date = "2024-01-01"
        adapter.env_config.backtest.end_date = "2024-12-31"
        universe_data = {"2024-01": ["BTCUSDT", "ETHUSDT"], "2024-02": ["BTCUSDT", "SOLUSDT"]}
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


class TestSymbolValidation(unittest.TestCase):
    """Test symbol validation in ConfigAdapter.create_instrument_config"""

    @patch("core.adapter.ConfigLoader")
    def setUp(self, mock_loader):
        from core.adapter import ConfigAdapter

        self.adapter = ConfigAdapter()
        # Mock env_config for create_instrument_config
        self.adapter.env_config = Mock()
        self.adapter.env_config.trading.venue = "BINANCE"
        self.adapter.env_config.trading.instrument_type = "SWAP"

    def test_valid_simple_symbol(self):
        """Test valid simple symbol like BTCUSDT"""
        # Should not raise - validation passes
        config = self.adapter.create_instrument_config("BTCUSDT")
        self.assertIsNotNone(config)

    def test_valid_slash_symbol(self):
        """Test valid symbol with slash like BTC/USDT"""
        # Should not raise - validation passes (slash is now allowed)
        config = self.adapter.create_instrument_config("BTC/USDT")
        self.assertIsNotNone(config)

    def test_valid_colon_symbol(self):
        """Test valid symbol with colon like BTC/USDT:USDT"""
        # Should not raise - validation passes
        config = self.adapter.create_instrument_config("BTC/USDT:USDT")
        self.assertIsNotNone(config)

    def test_valid_hyphen_symbol(self):
        """Test valid symbol with hyphen like BTC-USDT"""
        # Should not raise - validation passes
        config = self.adapter.create_instrument_config("BTC-USDT")
        self.assertIsNotNone(config)

    def test_empty_string_raises(self):
        """Test that empty string raises ValueError"""
        with self.assertRaises(ValueError) as cm:
            self.adapter.create_instrument_config("")
        self.assertIn("must be a non-empty string", str(cm.exception))

    def test_none_raises(self):
        """Test that None raises ValueError"""
        with self.assertRaises(ValueError) as cm:
            self.adapter.create_instrument_config(None)  # type: ignore
        self.assertIn("must be a non-empty string", str(cm.exception))

    def test_non_string_raises(self):
        """Test that non-string input raises ValueError"""
        with self.assertRaises(ValueError) as cm:
            self.adapter.create_instrument_config(123)  # type: ignore
        self.assertIn("must be a non-empty string", str(cm.exception))

    def test_invalid_characters_raises(self):
        """Test that invalid characters raise ValueError"""
        invalid_symbols = [
            "BTC;USDT",  # semicolon
            "BTC&USDT",  # ampersand
            "BTC|USDT",  # pipe
            "BTC`USDT",  # backtick
            "BTC$USDT",  # dollar sign
            "BTC(USDT",  # parenthesis
        ]

        for symbol in invalid_symbols:
            with self.assertRaises(ValueError) as cm:
                self.adapter.create_instrument_config(symbol)
            self.assertIn("only alphanumeric characters", str(cm.exception))

    def test_max_length_boundary(self):
        """Test symbol length validation at boundary (30 chars)"""
        # Exactly 30 chars - should pass
        valid_symbol = "A" * 26 + "USDT"  # 26 + 4 = 30
        config = self.adapter.create_instrument_config(valid_symbol)
        self.assertIsNotNone(config)

        # 31 chars - should fail
        invalid_symbol = "A" * 27 + "USDT"  # 27 + 4 = 31
        with self.assertRaises(ValueError) as cm:
            self.adapter.create_instrument_config(invalid_symbol)
        self.assertIn("exceeds maximum length of 30", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
