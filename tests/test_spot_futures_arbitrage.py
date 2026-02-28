"""
Unit tests for SpotFuturesArbitrageStrategy

Tests focus on configuration, data structures, and strategy logic components.
Full strategy integration is tested separately in integration tests.
"""

import unittest
from decimal import Decimal

from strategy.spot_futures_arbitrage import (
    PendingPair,
    SpotFuturesArbitrageConfig,
)
from strategy.common.arbitrage import (
    ArbitragePairTracker,
    BasisCalculator,
    DeltaManager,
)
from utils.custom_data import FundingRateData
from nautilus_trader.model.identifiers import InstrumentId


class TestSpotFuturesArbitrageConfig(unittest.TestCase):
    """Test SpotFuturesArbitrageConfig."""

    def test_default_initialization(self):
        """Test config initialization with default values."""
        config = SpotFuturesArbitrageConfig()

        self.assertEqual(config.venue, "BINANCE")
        self.assertEqual(config.spot_symbol, "BTCUSDT")
        self.assertEqual(config.perp_symbol, "BTCUSDT-PERP")
        self.assertEqual(config.timeframe, "1h")
        self.assertEqual(config.entry_basis_annual, 15.0)
        self.assertEqual(config.exit_basis_annual, 5.0)
        self.assertEqual(config.delta_tolerance, 0.005)
        self.assertEqual(config.position_size_pct, 0.2)
        self.assertEqual(config.max_positions, 3)
        self.assertEqual(config.min_holding_days, 7)
        self.assertEqual(config.max_holding_days, 90)
        self.assertEqual(config.negative_funding_threshold, 3)
        self.assertEqual(config.order_timeout_seconds, 5.0)

    def test_custom_initialization(self):
        """Test config initialization with custom values."""
        config = SpotFuturesArbitrageConfig(
            venue="OKX",
            spot_symbol="ETHUSDT",
            perp_symbol="ETHUSDT-PERP",
            entry_basis_annual=20.0,
            exit_basis_annual=8.0,
            delta_tolerance=0.01,
            max_positions=5,
        )

        self.assertEqual(config.venue, "OKX")
        self.assertEqual(config.spot_symbol, "ETHUSDT")
        self.assertEqual(config.perp_symbol, "ETHUSDT-PERP")
        self.assertEqual(config.entry_basis_annual, 20.0)
        self.assertEqual(config.exit_basis_annual, 8.0)
        self.assertEqual(config.delta_tolerance, 0.01)
        self.assertEqual(config.max_positions, 5)

    def test_risk_parameters(self):
        """Test risk management parameters."""
        config = SpotFuturesArbitrageConfig(
            min_margin_ratio=0.6,
            emergency_margin_ratio=0.4,
        )

        self.assertEqual(config.min_margin_ratio, 0.6)
        self.assertEqual(config.emergency_margin_ratio, 0.4)

    def test_time_parameters(self):
        """Test time-related parameters."""
        config = SpotFuturesArbitrageConfig(
            min_holding_days=14,
            max_holding_days=60,
            negative_funding_threshold=5,
        )

        self.assertEqual(config.min_holding_days, 14)
        self.assertEqual(config.max_holding_days, 60)
        self.assertEqual(config.negative_funding_threshold, 5)


class TestPendingPair(unittest.TestCase):
    """Test PendingPair dataclass."""

    def test_initialization(self):
        """Test PendingPair initialization."""
        pending = PendingPair(
            spot_order_id="spot_order_1",
            perp_order_id="perp_order_1",
            submit_time=1000000000000,
        )

        self.assertEqual(pending.spot_order_id, "spot_order_1")
        self.assertEqual(pending.perp_order_id, "perp_order_1")
        self.assertEqual(pending.submit_time, 1000000000000)
        self.assertFalse(pending.spot_filled)
        self.assertFalse(pending.perp_filled)

    def test_fill_tracking(self):
        """Test fill status tracking."""
        pending = PendingPair(
            spot_order_id="spot_order_1",
            perp_order_id="perp_order_1",
            submit_time=1000000000000,
        )

        pending.spot_filled = True
        self.assertTrue(pending.spot_filled)
        self.assertFalse(pending.perp_filled)

        pending.perp_filled = True
        self.assertTrue(pending.spot_filled)
        self.assertTrue(pending.perp_filled)

    def test_both_filled_check(self):
        """Test checking if both orders are filled."""
        pending = PendingPair(
            spot_order_id="spot_order_1",
            perp_order_id="perp_order_1",
            submit_time=1000000000000,
        )

        # Neither filled
        self.assertFalse(pending.spot_filled and pending.perp_filled)

        # Only spot filled
        pending.spot_filled = True
        self.assertFalse(pending.spot_filled and pending.perp_filled)

        # Both filled
        pending.perp_filled = True
        self.assertTrue(pending.spot_filled and pending.perp_filled)


class TestStrategyComponents(unittest.TestCase):
    """Test strategy component integration."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = SpotFuturesArbitrageConfig()
        self.basis_calc = BasisCalculator()
        self.delta_mgr = DeltaManager()
        self.pair_tracker = ArbitragePairTracker(max_pairs=self.config.max_positions)

    def test_component_initialization(self):
        """Test that all components initialize correctly."""
        self.assertIsNotNone(self.basis_calc)
        self.assertIsNotNone(self.delta_mgr)
        self.assertIsNotNone(self.pair_tracker)
        self.assertEqual(self.pair_tracker._max_pairs, 3)

    def test_entry_signal_logic(self):
        """Test entry signal generation logic."""
        # Calculate basis and annual return
        spot_price = 50000.0
        perp_price = 50500.0

        basis = self.basis_calc.calculate_basis(spot_price, perp_price)
        annual_return = self.basis_calc.calculate_annual_return(
            basis, holding_days=self.config.min_holding_days
        )

        # Check if should open position
        should_open = self.basis_calc.should_open_position(
            annual_return, threshold=self.config.entry_basis_annual
        )

        # With 1% basis over 7 days, annual return should be ~156%
        self.assertGreater(annual_return, 100.0)
        self.assertTrue(should_open)

    def test_exit_signal_logic_basis_converged(self):
        """Test exit signal when basis converges."""
        spot_price = 50000.0
        perp_price = 50050.0  # Small premium

        basis = self.basis_calc.calculate_basis(spot_price, perp_price)
        annual_return = self.basis_calc.calculate_annual_return(
            basis, holding_days=self.config.min_holding_days
        )

        should_close = self.basis_calc.should_close_position(
            annual_return, threshold=self.config.exit_basis_annual
        )

        # With 0.1% basis, annual return should be ~15.6%, above 5% threshold
        self.assertFalse(should_close)

        # Test with even smaller basis
        perp_price = 50010.0  # Very small premium
        basis = self.basis_calc.calculate_basis(spot_price, perp_price)
        annual_return = self.basis_calc.calculate_annual_return(
            basis, holding_days=self.config.min_holding_days
        )

        should_close = self.basis_calc.should_close_position(
            annual_return, threshold=self.config.exit_basis_annual
        )

        # With 0.02% basis, annual return should be ~3.1%, below 5% threshold
        self.assertTrue(should_close)

    def test_delta_neutral_validation(self):
        """Test delta neutral position validation."""
        spot_price = 50000.0
        perp_price = 50100.0

        # Calculate hedge ratio
        hedge_ratio = self.delta_mgr.calculate_hedge_ratio(spot_price, perp_price)

        # Calculate quantities
        spot_qty = Decimal("10.0")
        perp_qty = spot_qty * Decimal(str(hedge_ratio))

        # Calculate notionals
        spot_notional = self.delta_mgr.calculate_notional(spot_qty, spot_price)
        perp_notional = self.delta_mgr.calculate_notional(perp_qty, perp_price)

        # Check delta neutral
        is_neutral = self.delta_mgr.is_delta_neutral(
            spot_notional, perp_notional, self.config.delta_tolerance
        )

        self.assertTrue(is_neutral)

        # Calculate delta ratio
        delta_ratio = self.delta_mgr.calculate_delta_ratio(spot_notional, perp_notional)
        self.assertLess(abs(delta_ratio), self.config.delta_tolerance)

    def test_position_tracking(self):
        """Test arbitrage pair tracking."""
        # Link positions
        pair_id = self.pair_tracker.link_positions(
            spot_position_id="spot_1",
            perp_position_id="perp_1",
            entry_basis=0.01,
            entry_annual_return=156.0,
            entry_time=1000000000000000000,
        )

        self.assertEqual(pair_id, "spot_1_perp_1")

        # Get pair
        pair = self.pair_tracker.get_pair(pair_id)
        self.assertIsNotNone(pair)
        self.assertEqual(pair.entry_basis, 0.01)
        self.assertEqual(pair.entry_annual_return, 156.0)

        # Check can open new pair
        self.assertTrue(self.pair_tracker.can_open_new_pair())

        # Add more pairs until max
        self.pair_tracker.link_positions(
            spot_position_id="spot_2",
            perp_position_id="perp_2",
            entry_basis=0.01,
            entry_annual_return=156.0,
            entry_time=1000000000000000000,
        )
        self.pair_tracker.link_positions(
            spot_position_id="spot_3",
            perp_position_id="perp_3",
            entry_basis=0.01,
            entry_annual_return=156.0,
            entry_time=1000000000000000000,
        )

        # Should not be able to open new pair
        self.assertFalse(self.pair_tracker.can_open_new_pair())

    def test_funding_rate_tracking(self):
        """Test funding rate collection tracking."""
        # Link position
        pair_id = self.pair_tracker.link_positions(
            spot_position_id="spot_1",
            perp_position_id="perp_1",
            entry_basis=0.01,
            entry_annual_return=156.0,
            entry_time=1000000000000000000,
        )

        # Update funding rate
        self.pair_tracker.update_funding_rate(pair_id, Decimal("10.5"))
        pair = self.pair_tracker.get_pair(pair_id)
        self.assertEqual(pair.funding_rate_collected, Decimal("10.5"))

        # Update again
        self.pair_tracker.update_funding_rate(pair_id, Decimal("8.3"))
        pair = self.pair_tracker.get_pair(pair_id)
        self.assertEqual(pair.funding_rate_collected, Decimal("18.8"))

    def test_negative_funding_tracking(self):
        """Test negative funding rate tracking."""
        # Link position
        pair_id = self.pair_tracker.link_positions(
            spot_position_id="spot_1",
            perp_position_id="perp_1",
            entry_basis=0.01,
            entry_annual_return=156.0,
            entry_time=1000000000000000000,
        )

        # Increment negative funding
        self.pair_tracker.increment_negative_funding(pair_id)
        pair = self.pair_tracker.get_pair(pair_id)
        self.assertEqual(pair.negative_funding_count, 1)

        # Increment again
        self.pair_tracker.increment_negative_funding(pair_id)
        self.pair_tracker.increment_negative_funding(pair_id)
        pair = self.pair_tracker.get_pair(pair_id)
        self.assertEqual(pair.negative_funding_count, 3)

        # Check should close
        should_close = self.pair_tracker.should_close_by_funding(
            pair_id, threshold=self.config.negative_funding_threshold
        )
        self.assertTrue(should_close)

        # Reset
        self.pair_tracker.reset_negative_funding(pair_id)
        pair = self.pair_tracker.get_pair(pair_id)
        self.assertEqual(pair.negative_funding_count, 0)

    def test_time_based_exit(self):
        """Test time-based exit conditions."""
        entry_time = 1000000000000000000
        pair_id = self.pair_tracker.link_positions(
            spot_position_id="spot_1",
            perp_position_id="perp_1",
            entry_basis=0.01,
            entry_annual_return=156.0,
            entry_time=entry_time,
        )

        one_day_ns = 24 * 60 * 60 * int(1e9)

        # Test before min holding days
        current_time = entry_time + (5 * one_day_ns)
        should_close, reason = self.pair_tracker.should_close_by_time(
            pair_id,
            current_time,
            min_days=self.config.min_holding_days,
            max_days=self.config.max_holding_days,
        )
        self.assertFalse(should_close)

        # Test after max holding days
        current_time = entry_time + (91 * one_day_ns)
        should_close, reason = self.pair_tracker.should_close_by_time(
            pair_id,
            current_time,
            min_days=self.config.min_holding_days,
            max_days=self.config.max_holding_days,
        )
        self.assertTrue(should_close)
        self.assertIn("max_holding_days_reached", reason)

    def test_holding_days_calculation(self):
        """Test holding days calculation."""
        entry_time = 1000000000000000000
        pair_id = self.pair_tracker.link_positions(
            spot_position_id="spot_1",
            perp_position_id="perp_1",
            entry_basis=0.01,
            entry_annual_return=156.0,
            entry_time=entry_time,
        )

        one_day_ns = 24 * 60 * 60 * int(1e9)

        # Test 1 day
        current_time = entry_time + one_day_ns
        holding_days = self.pair_tracker.get_holding_days(pair_id, current_time)
        self.assertAlmostEqual(holding_days, 1.0, places=5)

        # Test 7 days
        current_time = entry_time + (7 * one_day_ns)
        holding_days = self.pair_tracker.get_holding_days(pair_id, current_time)
        self.assertAlmostEqual(holding_days, 7.0, places=5)

        # Test 30 days
        current_time = entry_time + (30 * one_day_ns)
        holding_days = self.pair_tracker.get_holding_days(pair_id, current_time)
        self.assertAlmostEqual(holding_days, 30.0, places=5)


class TestFundingRateData(unittest.TestCase):
    """Test FundingRateData integration."""

    def test_funding_rate_data_creation(self):
        """Test creating FundingRateData."""
        instrument_id = InstrumentId.from_str("BTCUSDT-PERP.BINANCE")
        funding_data = FundingRateData(
            instrument_id=instrument_id,
            funding_rate=Decimal("0.0001"),
            next_funding_time=None,
            ts_event=1000000000000000000,
            ts_init=1000000000000000000,
        )

        self.assertEqual(funding_data.instrument_id, instrument_id)
        self.assertEqual(funding_data.funding_rate, Decimal("0.0001"))
        self.assertIsNotNone(funding_data.funding_rate_annual)

    def test_funding_rate_annual_calculation(self):
        """Test annual funding rate calculation."""
        instrument_id = InstrumentId.from_str("BTCUSDT-PERP.BINANCE")

        # Positive funding rate
        funding_data = FundingRateData(
            instrument_id=instrument_id,
            funding_rate=Decimal("0.0001"),
            next_funding_time=None,
            ts_event=1000000000000000000,
            ts_init=1000000000000000000,
        )

        # 0.0001 * 3 * 365 * 100 = 10.95%
        expected_annual = Decimal("0.0001") * Decimal("3") * Decimal("365") * Decimal("100")
        self.assertEqual(funding_data.funding_rate_annual, expected_annual)

        # Negative funding rate
        funding_data_neg = FundingRateData(
            instrument_id=instrument_id,
            funding_rate=Decimal("-0.0001"),
            next_funding_time=None,
            ts_event=1000000000000000000,
            ts_init=1000000000000000000,
        )

        expected_annual_neg = Decimal("-0.0001") * Decimal("3") * Decimal("365") * Decimal("100")
        self.assertEqual(funding_data_neg.funding_rate_annual, expected_annual_neg)


class TestOrderTimeout(unittest.TestCase):
    """Test order timeout logic."""

    def test_pending_pair_timeout_detection(self):
        """Test detecting order timeout."""
        config = SpotFuturesArbitrageConfig(order_timeout_seconds=5.0)
        timeout_ns = int(config.order_timeout_seconds * 1_000_000_000)

        # Create pending pair
        submit_time = 1000000000000
        pending = PendingPair(
            spot_order_id="spot_1",
            perp_order_id="perp_1",
            submit_time=submit_time,
        )

        # Check before timeout
        current_time = submit_time + (timeout_ns - 1_000_000_000)  # 4 seconds
        elapsed = current_time - pending.submit_time
        self.assertLess(elapsed, timeout_ns)

        # Check after timeout
        current_time = submit_time + (timeout_ns + 1_000_000_000)  # 6 seconds
        elapsed = current_time - pending.submit_time
        self.assertGreater(elapsed, timeout_ns)

    def test_partial_fill_scenarios(self):
        """Test different partial fill scenarios."""
        # Scenario 1: Spot filled, perp not filled
        pending1 = PendingPair(
            spot_order_id="spot_1",
            perp_order_id="perp_1",
            submit_time=1000000000000,
            spot_filled=True,
            perp_filled=False,
        )
        self.assertTrue(pending1.spot_filled and not pending1.perp_filled)

        # Scenario 2: Perp filled, spot not filled
        pending2 = PendingPair(
            spot_order_id="spot_2",
            perp_order_id="perp_2",
            submit_time=1000000000000,
            spot_filled=False,
            perp_filled=True,
        )
        self.assertTrue(pending2.perp_filled and not pending2.spot_filled)

        # Scenario 3: Neither filled
        pending3 = PendingPair(
            spot_order_id="spot_3",
            perp_order_id="perp_3",
            submit_time=1000000000000,
            spot_filled=False,
            perp_filled=False,
        )
        self.assertFalse(pending3.spot_filled or pending3.perp_filled)


if __name__ == "__main__":
    unittest.main()
