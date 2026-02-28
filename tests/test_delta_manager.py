"""Tests for DeltaManager."""

import unittest
from decimal import Decimal

from strategy.common.arbitrage.delta_manager import DeltaManager


class TestDeltaManager(unittest.TestCase):
    """Test cases for DeltaManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.manager = DeltaManager()

    def test_calculate_notional_normal(self):
        """Test normal notional calculation."""
        quantity = Decimal("10.5")
        price = 50000.0
        expected = Decimal("525000.0")

        result = self.manager.calculate_notional(quantity, price)

        self.assertEqual(result, expected)

    def test_calculate_notional_zero_quantity(self):
        """Test notional calculation with zero quantity."""
        quantity = Decimal("0")
        price = 50000.0

        result = self.manager.calculate_notional(quantity, price)

        self.assertEqual(result, Decimal("0"))

    def test_calculate_notional_zero_price_raises(self):
        """Test that zero price raises ValueError."""
        quantity = Decimal("10")
        price = 0.0

        with self.assertRaises(ValueError) as context:
            self.manager.calculate_notional(quantity, price)

        self.assertIn("Price cannot be zero", str(context.exception))

    def test_calculate_delta_ratio_balanced(self):
        """Test delta ratio with balanced positions."""
        spot_notional = Decimal("100000")
        perp_notional = Decimal("100000")

        result = self.manager.calculate_delta_ratio(spot_notional, perp_notional)

        self.assertEqual(result, 0.0)

    def test_calculate_delta_ratio_imbalanced(self):
        """Test delta ratio with imbalanced positions."""
        spot_notional = Decimal("100000")
        perp_notional = Decimal("99000")

        result = self.manager.calculate_delta_ratio(spot_notional, perp_notional)

        self.assertAlmostEqual(result, 0.01, places=4)

    def test_calculate_delta_ratio_zero_spot_raises(self):
        """Test that zero spot notional raises ValueError."""
        spot_notional = Decimal("0")
        perp_notional = Decimal("100000")

        with self.assertRaises(ValueError) as context:
            self.manager.calculate_delta_ratio(spot_notional, perp_notional)

        self.assertIn("Spot notional cannot be zero", str(context.exception))

    def test_is_delta_neutral_within_tolerance(self):
        """Test delta neutral check within tolerance."""
        spot_notional = Decimal("100000")
        perp_notional = Decimal("99600")  # 0.4% difference

        result = self.manager.is_delta_neutral(spot_notional, perp_notional)

        self.assertTrue(result)

    def test_is_delta_neutral_exceeds_tolerance(self):
        """Test delta neutral check exceeding tolerance."""
        spot_notional = Decimal("100000")
        perp_notional = Decimal("99400")  # 0.6% difference

        result = self.manager.is_delta_neutral(spot_notional, perp_notional)

        self.assertFalse(result)

    def test_is_delta_neutral_custom_tolerance(self):
        """Test delta neutral check with custom tolerance."""
        spot_notional = Decimal("100000")
        perp_notional = Decimal("99000")  # 1% difference
        tolerance = 0.015  # 1.5%

        result = self.manager.is_delta_neutral(spot_notional, perp_notional, tolerance)

        self.assertTrue(result)

    def test_is_delta_neutral_zero_spot(self):
        """Test delta neutral check with zero spot notional."""
        spot_notional = Decimal("0")
        perp_notional = Decimal("100000")

        result = self.manager.is_delta_neutral(spot_notional, perp_notional)

        self.assertFalse(result)

    def test_calculate_hedge_ratio_normal(self):
        """Test normal hedge ratio calculation."""
        spot_price = 50000.0
        perp_price = 50100.0

        result = self.manager.calculate_hedge_ratio(spot_price, perp_price)

        expected = 50000.0 / 50100.0
        self.assertAlmostEqual(result, expected, places=6)

    def test_calculate_hedge_ratio_equal_prices(self):
        """Test hedge ratio with equal prices."""
        spot_price = 50000.0
        perp_price = 50000.0

        result = self.manager.calculate_hedge_ratio(spot_price, perp_price)

        self.assertEqual(result, 1.0)

    def test_calculate_hedge_ratio_zero_perp_raises(self):
        """Test that zero perpetual price raises ValueError."""
        spot_price = 50000.0
        perp_price = 0.0

        with self.assertRaises(ValueError) as context:
            self.manager.calculate_hedge_ratio(spot_price, perp_price)

        self.assertIn("Perpetual price cannot be zero", str(context.exception))

    def test_hedge_ratio_accuracy(self):
        """Test hedge ratio calculation accuracy < 0.1%."""
        spot_price = 50000.0
        perp_price = 50050.0

        result = self.manager.calculate_hedge_ratio(spot_price, perp_price)
        expected = 50000.0 / 50050.0

        error = abs(result - expected) / expected
        self.assertLess(error, 0.001)  # < 0.1%

    def test_delta_neutral_accuracy_100_percent(self):
        """Test delta neutral judgment accuracy is 100%."""
        test_cases = [
            # (spot, perp, tolerance, expected)
            (Decimal("100000"), Decimal("99600"), 0.005, True),  # 0.4%
            (Decimal("100000"), Decimal("99500"), 0.005, False),  # 0.5%
            (Decimal("100000"), Decimal("99400"), 0.005, False),  # 0.6%
            (Decimal("100000"), Decimal("100400"), 0.005, True),  # 0.4%
            (Decimal("100000"), Decimal("100600"), 0.005, False),  # 0.6%
        ]

        for spot, perp, tolerance, expected in test_cases:
            with self.subTest(spot=spot, perp=perp):
                result = self.manager.is_delta_neutral(spot, perp, tolerance)
                self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
