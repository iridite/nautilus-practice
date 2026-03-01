"""
Unit tests for BasisCalculator
"""

import unittest

from strategy.common.arbitrage.basis_calculator import BasisCalculator


class TestBasisCalculator(unittest.TestCase):
    """Test cases for BasisCalculator"""

    def setUp(self):
        """Set up test fixtures"""
        self.calculator = BasisCalculator()

    def test_calculate_basis_positive(self):
        """Test basis calculation with perp > spot (positive basis)"""
        basis = self.calculator.calculate_basis(spot_price=100.0, perp_price=101.0)
        self.assertAlmostEqual(basis, 0.01, places=4)

    def test_calculate_basis_negative(self):
        """Test basis calculation with perp < spot (negative basis)"""
        basis = self.calculator.calculate_basis(spot_price=100.0, perp_price=99.0)
        self.assertAlmostEqual(basis, -0.01, places=4)

    def test_calculate_basis_zero(self):
        """Test basis calculation with equal prices"""
        basis = self.calculator.calculate_basis(spot_price=100.0, perp_price=100.0)
        self.assertAlmostEqual(basis, 0.0, places=4)

    def test_calculate_basis_precision(self):
        """Test basis calculation precision < 0.01%"""
        basis = self.calculator.calculate_basis(spot_price=100.0, perp_price=100.005)
        self.assertAlmostEqual(basis, 0.00005, places=6)

    def test_calculate_basis_invalid_spot_price_zero(self):
        """Test that zero spot price raises ValueError"""
        with self.assertRaises(ValueError) as context:
            self.calculator.calculate_basis(spot_price=0.0, perp_price=100.0)
        self.assertIn("Spot price must be positive", str(context.exception))

    def test_calculate_basis_invalid_spot_price_negative(self):
        """Test that negative spot price raises ValueError"""
        with self.assertRaises(ValueError) as context:
            self.calculator.calculate_basis(spot_price=-100.0, perp_price=100.0)
        self.assertIn("Spot price must be positive", str(context.exception))

    def test_calculate_basis_invalid_perp_price_zero(self):
        """Test that zero perp price raises ValueError"""
        with self.assertRaises(ValueError) as context:
            self.calculator.calculate_basis(spot_price=100.0, perp_price=0.0)
        self.assertIn("Perpetual price must be positive", str(context.exception))

    def test_calculate_basis_invalid_perp_price_negative(self):
        """Test that negative perp price raises ValueError"""
        with self.assertRaises(ValueError) as context:
            self.calculator.calculate_basis(spot_price=100.0, perp_price=-100.0)
        self.assertIn("Perpetual price must be positive", str(context.exception))

    def test_calculate_annual_return_default_holding_days(self):
        """Test annual return calculation with default 7 days"""
        basis = 0.01  # 1% basis
        annual_return = self.calculator.calculate_annual_return(basis)
        # 0.01 * (365 / 7) * 3 * 100 = 156.43%
        expected = 0.01 * (365 / 7) * 3 * 100
        self.assertAlmostEqual(annual_return, expected, places=2)

    def test_calculate_annual_return_custom_holding_days(self):
        """Test annual return calculation with custom holding days"""
        basis = 0.01  # 1% basis
        annual_return = self.calculator.calculate_annual_return(basis, holding_days=30)
        # 0.01 * (365 / 30) * 3 * 100 = 36.5%
        expected = 0.01 * (365 / 30) * 3 * 100
        self.assertAlmostEqual(annual_return, expected, places=2)

    def test_calculate_annual_return_negative_basis(self):
        """Test annual return calculation with negative basis"""
        basis = -0.01  # -1% basis
        annual_return = self.calculator.calculate_annual_return(basis, holding_days=7)
        expected = -0.01 * (365 / 7) * 3 * 100
        self.assertAlmostEqual(annual_return, expected, places=2)

    def test_calculate_annual_return_invalid_holding_days_zero(self):
        """Test that zero holding days raises ValueError"""
        with self.assertRaises(ValueError) as context:
            self.calculator.calculate_annual_return(0.01, holding_days=0)
        self.assertIn("Holding days must be positive", str(context.exception))

    def test_calculate_annual_return_invalid_holding_days_negative(self):
        """Test that negative holding days raises ValueError"""
        with self.assertRaises(ValueError) as context:
            self.calculator.calculate_annual_return(0.01, holding_days=-7)
        self.assertIn("Holding days must be positive", str(context.exception))

    def test_should_open_position_above_threshold(self):
        """Test open position signal when return > threshold"""
        should_open = self.calculator.should_open_position(annual_return=20.0, threshold=15.0)
        self.assertTrue(should_open)

    def test_should_open_position_below_threshold(self):
        """Test no open position signal when return < threshold"""
        should_open = self.calculator.should_open_position(annual_return=10.0, threshold=15.0)
        self.assertFalse(should_open)

    def test_should_open_position_equal_threshold(self):
        """Test no open position signal when return = threshold"""
        should_open = self.calculator.should_open_position(annual_return=15.0, threshold=15.0)
        self.assertFalse(should_open)

    def test_should_close_position_below_threshold(self):
        """Test close position signal when return < threshold"""
        should_close = self.calculator.should_close_position(annual_return=3.0, threshold=5.0)
        self.assertTrue(should_close)

    def test_should_close_position_above_threshold(self):
        """Test no close position signal when return > threshold"""
        should_close = self.calculator.should_close_position(annual_return=10.0, threshold=5.0)
        self.assertFalse(should_close)

    def test_should_close_position_equal_threshold(self):
        """Test no close position signal when return = threshold"""
        should_close = self.calculator.should_close_position(annual_return=5.0, threshold=5.0)
        self.assertFalse(should_close)

    def test_full_workflow_open_signal(self):
        """Test complete workflow: calculate basis -> annual return -> open signal"""
        # Scenario: perp at premium, high annual return
        basis = self.calculator.calculate_basis(spot_price=100.0, perp_price=101.0)
        annual_return = self.calculator.calculate_annual_return(basis, holding_days=7)
        should_open = self.calculator.should_open_position(annual_return, threshold=15.0)

        self.assertAlmostEqual(basis, 0.01, places=4)
        self.assertGreater(annual_return, 150.0)  # Should be ~156%
        self.assertTrue(should_open)

    def test_full_workflow_close_signal(self):
        """Test complete workflow: calculate basis -> annual return -> close signal"""
        # Scenario: perp at small premium, low annual return
        basis = self.calculator.calculate_basis(spot_price=100.0, perp_price=100.1)
        annual_return = self.calculator.calculate_annual_return(basis, holding_days=7)
        should_close = self.calculator.should_close_position(annual_return, threshold=5.0)

        self.assertAlmostEqual(basis, 0.001, places=4)
        self.assertLess(annual_return, 20.0)  # Should be ~15.6%
        self.assertFalse(should_close)  # 15.6% > 5% threshold, so don't close


if __name__ == "__main__":
    unittest.main()
