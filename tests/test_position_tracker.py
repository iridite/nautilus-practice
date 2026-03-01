"""Tests for ArbitragePairTracker."""

import unittest
from decimal import Decimal

from strategy.common.arbitrage.position_tracker import ArbitragePair, ArbitragePairTracker


class TestArbitragePair(unittest.TestCase):
    """Test ArbitragePair dataclass."""

    def test_initialization(self):
        """Test basic initialization."""
        pair = ArbitragePair(
            pair_id="test_pair",
            spot_position_id="spot_1",
            perp_position_id="perp_1",
            entry_time=1000000000000,
            entry_basis=0.05,
            entry_annual_return=15.0,
        )

        self.assertEqual(pair.pair_id, "test_pair")
        self.assertEqual(pair.spot_position_id, "spot_1")
        self.assertEqual(pair.perp_position_id, "perp_1")
        self.assertEqual(pair.entry_time, 1000000000000)
        self.assertEqual(pair.entry_basis, 0.05)
        self.assertEqual(pair.entry_annual_return, 15.0)
        self.assertEqual(pair.funding_rate_collected, Decimal("0"))
        self.assertEqual(pair.negative_funding_count, 0)


class TestArbitragePairTracker(unittest.TestCase):
    """Test ArbitragePairTracker."""

    def setUp(self):
        """Set up test fixtures."""
        self.tracker = ArbitragePairTracker(max_pairs=3)

    def test_link_positions(self):
        """Test linking positions."""
        pair_id = self.tracker.link_positions(
            spot_position_id="spot_1",
            perp_position_id="perp_1",
            entry_basis=0.05,
            entry_annual_return=15.0,
            entry_time=1000000000000,
        )

        self.assertEqual(pair_id, "spot_1_perp_1")
        pair = self.tracker.get_pair(pair_id)
        self.assertIsNotNone(pair)
        self.assertEqual(pair.spot_position_id, "spot_1")
        self.assertEqual(pair.perp_position_id, "perp_1")

    def test_unlink_pair(self):
        """Test unlinking pair."""
        pair_id = self.tracker.link_positions(
            spot_position_id="spot_1",
            perp_position_id="perp_1",
            entry_basis=0.05,
            entry_annual_return=15.0,
            entry_time=1000000000000,
        )

        removed_pair = self.tracker.unlink_pair(pair_id)
        self.assertIsNotNone(removed_pair)
        self.assertEqual(removed_pair.pair_id, pair_id)

        # Verify pair is removed
        self.assertIsNone(self.tracker.get_pair(pair_id))

    def test_get_pair_by_position_id(self):
        """Test getting pair by position ID."""
        pair_id = self.tracker.link_positions(
            spot_position_id="spot_1",
            perp_position_id="perp_1",
            entry_basis=0.05,
            entry_annual_return=15.0,
            entry_time=1000000000000,
        )

        # Find by spot position ID
        pair = self.tracker.get_pair_by_position_id("spot_1")
        self.assertIsNotNone(pair)
        self.assertEqual(pair.pair_id, pair_id)

        # Find by perp position ID
        pair = self.tracker.get_pair_by_position_id("perp_1")
        self.assertIsNotNone(pair)
        self.assertEqual(pair.pair_id, pair_id)

        # Not found
        pair = self.tracker.get_pair_by_position_id("nonexistent")
        self.assertIsNone(pair)

    def test_update_funding_rate(self):
        """Test updating funding rate."""
        pair_id = self.tracker.link_positions(
            spot_position_id="spot_1",
            perp_position_id="perp_1",
            entry_basis=0.05,
            entry_annual_return=15.0,
            entry_time=1000000000000,
        )

        self.tracker.update_funding_rate(pair_id, Decimal("10.5"))
        pair = self.tracker.get_pair(pair_id)
        self.assertEqual(pair.funding_rate_collected, Decimal("10.5"))

        self.tracker.update_funding_rate(pair_id, Decimal("5.3"))
        pair = self.tracker.get_pair(pair_id)
        self.assertEqual(pair.funding_rate_collected, Decimal("15.8"))

    def test_negative_funding_count(self):
        """Test negative funding count management."""
        pair_id = self.tracker.link_positions(
            spot_position_id="spot_1",
            perp_position_id="perp_1",
            entry_basis=0.05,
            entry_annual_return=15.0,
            entry_time=1000000000000,
        )

        # Increment
        self.tracker.increment_negative_funding(pair_id)
        pair = self.tracker.get_pair(pair_id)
        self.assertEqual(pair.negative_funding_count, 1)

        self.tracker.increment_negative_funding(pair_id)
        pair = self.tracker.get_pair(pair_id)
        self.assertEqual(pair.negative_funding_count, 2)

        # Reset
        self.tracker.reset_negative_funding(pair_id)
        pair = self.tracker.get_pair(pair_id)
        self.assertEqual(pair.negative_funding_count, 0)

    def test_get_holding_days(self):
        """Test holding days calculation."""
        entry_time = 1000000000000000000  # 纳秒时间戳
        pair_id = self.tracker.link_positions(
            spot_position_id="spot_1",
            perp_position_id="perp_1",
            entry_basis=0.05,
            entry_annual_return=15.0,
            entry_time=entry_time,
        )

        # 1 day later (24 * 60 * 60 * 1e9 nanoseconds)
        one_day_ns = 24 * 60 * 60 * int(1e9)
        current_time = entry_time + one_day_ns
        holding_days = self.tracker.get_holding_days(pair_id, current_time)
        self.assertAlmostEqual(holding_days, 1.0, places=5)

        # 7 days later
        current_time = entry_time + (7 * one_day_ns)
        holding_days = self.tracker.get_holding_days(pair_id, current_time)
        self.assertAlmostEqual(holding_days, 7.0, places=5)

    def test_should_close_by_time(self):
        """Test time-based close conditions."""
        entry_time = 1000000000000000000
        pair_id = self.tracker.link_positions(
            spot_position_id="spot_1",
            perp_position_id="perp_1",
            entry_basis=0.05,
            entry_annual_return=15.0,
            entry_time=entry_time,
        )

        one_day_ns = 24 * 60 * 60 * int(1e9)

        # Less than min_days (7 days)
        current_time = entry_time + (5 * one_day_ns)
        should_close, reason = self.tracker.should_close_by_time(pair_id, current_time)
        self.assertFalse(should_close)
        self.assertEqual(reason, "")

        # Between min and max
        current_time = entry_time + (30 * one_day_ns)
        should_close, reason = self.tracker.should_close_by_time(pair_id, current_time)
        self.assertFalse(should_close)
        self.assertEqual(reason, "")

        # Exceeds max_days (90 days)
        current_time = entry_time + (91 * one_day_ns)
        should_close, reason = self.tracker.should_close_by_time(pair_id, current_time)
        self.assertTrue(should_close)
        self.assertIn("max_holding_days_reached", reason)

    def test_should_close_by_funding(self):
        """Test funding-based close conditions."""
        pair_id = self.tracker.link_positions(
            spot_position_id="spot_1",
            perp_position_id="perp_1",
            entry_basis=0.05,
            entry_annual_return=15.0,
            entry_time=1000000000000,
        )

        # Default threshold is 3
        self.assertFalse(self.tracker.should_close_by_funding(pair_id))

        # Increment to 1
        self.tracker.increment_negative_funding(pair_id)
        self.assertFalse(self.tracker.should_close_by_funding(pair_id))

        # Increment to 2
        self.tracker.increment_negative_funding(pair_id)
        self.assertFalse(self.tracker.should_close_by_funding(pair_id))

        # Increment to 3 (should trigger)
        self.tracker.increment_negative_funding(pair_id)
        self.assertTrue(self.tracker.should_close_by_funding(pair_id))

    def test_can_open_new_pair(self):
        """Test max pairs limit."""
        self.assertTrue(self.tracker.can_open_new_pair())

        # Add 3 pairs (max_pairs=3)
        for i in range(3):
            self.tracker.link_positions(
                spot_position_id=f"spot_{i}",
                perp_position_id=f"perp_{i}",
                entry_basis=0.05,
                entry_annual_return=15.0,
                entry_time=1000000000000,
            )

        self.assertFalse(self.tracker.can_open_new_pair())

        # Remove one pair
        self.tracker.unlink_pair("spot_0_perp_0")
        self.assertTrue(self.tracker.can_open_new_pair())

    def test_get_all_pairs(self):
        """Test getting all pairs."""
        self.assertEqual(len(self.tracker.get_all_pairs()), 0)

        # Add 2 pairs
        self.tracker.link_positions(
            spot_position_id="spot_1",
            perp_position_id="perp_1",
            entry_basis=0.05,
            entry_annual_return=15.0,
            entry_time=1000000000000,
        )
        self.tracker.link_positions(
            spot_position_id="spot_2",
            perp_position_id="perp_2",
            entry_basis=0.06,
            entry_annual_return=18.0,
            entry_time=2000000000000,
        )

        pairs = self.tracker.get_all_pairs()
        self.assertEqual(len(pairs), 2)
        self.assertIsInstance(pairs[0], ArbitragePair)


if __name__ == "__main__":
    unittest.main()
