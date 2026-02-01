"""
Tests for Dual Thrust Strategy
"""
import unittest

from strategy.dual_thrust import DualThrustConfig


class TestDualThrustConfig(unittest.TestCase):
    def test_default_config(self):
        config = DualThrustConfig()
        self.assertEqual(config.lookback_period, 4)
        self.assertEqual(config.k1, 0.5)
        self.assertEqual(config.k2, 0.5)

    def test_custom_config(self):
        config = DualThrustConfig(
            symbol="ETHUSDT",
            lookback_period=5,
            k1=0.6,
            k2=0.4
        )
        self.assertEqual(config.lookback_period, 5)
        self.assertEqual(config.k1, 0.6)
        self.assertEqual(config.k2, 0.4)


if __name__ == "__main__":
    unittest.main()
