#!/usr/bin/env python3
"""
Equivalence tests: ensure ConfigAdapter's restore helpers delegate semantics
match the standalone helpers in utils.instrument_helpers.

Run with:
    uv run python -m unittest discover -s tests -p "test_*.py" -v
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.adapter import ConfigAdapter
from utils.instrument_helpers import (
    build_bar_type_from_timeframe,
    format_aux_instrument_id,
)


@patch("core.adapter.ConfigLoader")
class TestAdapterRestoreEquivalence(unittest.TestCase):
    def setUp(self):
        # Note: ConfigLoader is patched by the class decorator; constructing
        # ConfigAdapter will not attempt real file I/O. We'll override the
        # env_config with minimal objects for our tests.
        self.adapter = ConfigAdapter()

    def _set_env(self, venue: str, inst_type: str):
        """
        Helper to set minimal env_config on the adapter for tests.
        """
        trading = SimpleNamespace(
            venue=venue,
            instrument_type=inst_type,
            main_timeframe="1d",
            trend_timeframe="1d",
            initial_balance=100,
        )
        # Provide minimal backtest and logging to avoid attribute errors elsewhere
        backtest = SimpleNamespace(start_date="2020-01-01", end_date="2020-12-31")
        logging = SimpleNamespace(
            level="INFO", file_level="INFO", components={}, components_only=False
        )
        # active_config and strategy_config are not used by the methods under test,
        # but ensure they exist to keep the adapter in a consistent state.
        self.adapter.env_config = SimpleNamespace(
            trading=trading, backtest=backtest, logging=logging
        )
        self.adapter.active_config = SimpleNamespace(
            timeframe=None, price_type=None, origination=None, overrides=None
        )
        self.adapter.strategy_config = SimpleNamespace(parameters={})

    def test_restore_instrument_id_matches_helper_swap_binance(self, mock_loader):
        self._set_env(venue="BINANCE", inst_type="SWAP")
        symbols = [
            "BTCUSDT",
            "BTC",
            "BTC-USDT",
            "BTC-USDT-PERP.OKX",  # already instrument-like (diff venue included)
        ]

        for sym in symbols:
            with self.subTest(symbol=sym):
                expected = format_aux_instrument_id(
                    sym,
                    template_inst_id=None,
                    venue=self.adapter.get_venue(),
                    inst_type=self.adapter.env_config.trading.instrument_type,
                )
                actual = self.adapter._restore_instrument_id(sym)
                self.assertEqual(actual, expected, f"Mismatch for symbol={sym}: adapter != helper")

    def test_restore_instrument_id_matches_helper_spot_okx(self, mock_loader):
        self._set_env(venue="OKX", inst_type="SPOT")
        symbols = [
            "ETHUSDT",
            "ETH",
            "eth-usdt",
            "LTC-USDT-PERP.BINANCE",
        ]

        for sym in symbols:
            with self.subTest(symbol=sym):
                expected = format_aux_instrument_id(
                    sym,
                    template_inst_id=None,
                    venue=self.adapter.get_venue(),
                    inst_type=self.adapter.env_config.trading.instrument_type,
                )
                actual = self.adapter._restore_instrument_id(sym)
                self.assertEqual(actual, expected, f"Mismatch for symbol={sym}: adapter != helper")

    def test_restore_bar_type_matches_helper_various_timeframes(self, mock_loader):
        self._set_env(venue="BINANCE", inst_type="SWAP")
        symbols = ["BTCUSDT", "ADA", "ADA-USDT"]
        timeframes = ["1d", "2h", "15m"]
        price_orig_pairs = [
            ("LAST", "EXTERNAL"),
            ("MID", "INTERNAL"),
        ]

        for sym in symbols:
            for tf in timeframes:
                for price_type, orig in price_orig_pairs:
                    with self.subTest(symbol=sym, timeframe=tf, price=price_type, orig=orig):
                        # Use adapter to get instrument_id (env-driven) then helper to build bar_type
                        inst_id = self.adapter._restore_instrument_id(sym)
                        expected = build_bar_type_from_timeframe(
                            inst_id, tf, price_type=price_type, origination=orig
                        )
                        actual = self.adapter._restore_bar_type(
                            sym, tf, price_type=price_type, origination=orig
                        )
                        self.assertEqual(
                            actual,
                            expected,
                            f"Bar type mismatch for {sym} {tf} {price_type}/{orig}",
                        )

    def test_restore_bar_type_fallback_behavior_on_unusual_timeframe(self, mock_loader):
        """
        Ensure adapter falls back to the helper semantics (or its own fallback) for unknown timeframe formats.
        """
        self._set_env(venue="BINANCE", inst_type="SWAP")
        sym = "BTC"
        weird_tfs = ["", "xyz", "10x"]  # unknown formats -> helper falls back to 1-DAY
        for tf in weird_tfs:
            with self.subTest(timeframe=tf):
                inst_id = self.adapter._restore_instrument_id(sym)
                # build_bar_type_from_timeframe will treat unknown tf as 1d (DAY)
                expected = build_bar_type_from_timeframe(inst_id, tf or "1d")
                actual = self.adapter._restore_bar_type(
                    sym, tf, price_type="LAST", origination="EXTERNAL"
                )
                self.assertEqual(
                    actual, expected, f"Fallback bar type mismatch for timeframe='{tf}'"
                )


if __name__ == "__main__":
    unittest.main()
