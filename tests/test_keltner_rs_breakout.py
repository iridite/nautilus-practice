"""
Tests for Keltner RS Breakout Strategy
"""
import unittest

from strategy.keltner_rs_breakout import KeltnerRSBreakoutConfig


class TestKeltnerRSBreakoutConfig(unittest.TestCase):
    def test_default_config(self):
        config = KeltnerRSBreakoutConfig()
        self.assertEqual(config.ema_period, 20)
        self.assertEqual(config.atr_period, 20)
        self.assertEqual(config.sma_period, 200)
        self.assertEqual(config.base_risk_pct, 0.01)

    def test_custom_config(self):
        config = KeltnerRSBreakoutConfig(
            symbol="ETHUSDT",
            timeframe="1h",
            ema_period=30,
            base_risk_pct=0.02
        )
        self.assertEqual(config.symbol, "ETHUSDT")
        self.assertEqual(config.ema_period, 30)
        self.assertEqual(config.base_risk_pct, 0.02)


if __name__ == "__main__":
    unittest.main()
