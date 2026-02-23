"""
Tests for Base Strategy
"""

import unittest

from strategy.core.base import BaseStrategyConfig


class TestBaseStrategyConfig(unittest.TestCase):
    def test_default_config(self):
        config = BaseStrategyConfig()
        self.assertEqual(config.oms_type, "NETTING")
        self.assertEqual(config.leverage, 1)
        self.assertEqual(config.max_positions, 1)

    def test_custom_config(self):
        config = BaseStrategyConfig(symbol="ETHUSDT", timeframe="1h", leverage=5, qty_percent=0.1)
        self.assertEqual(config.symbol, "ETHUSDT")
        self.assertEqual(config.leverage, 5)
        self.assertEqual(config.qty_percent, 0.1)

    def test_config_leverage(self):
        config = BaseStrategyConfig(leverage=10)
        self.assertEqual(config.leverage, 10)


if __name__ == "__main__":
    unittest.main()
