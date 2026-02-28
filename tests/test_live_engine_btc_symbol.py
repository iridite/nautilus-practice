#!/usr/bin/env python3
"""
Test that btc_symbol is correctly converted to OKX format in live engine.

This test verifies that when a strategy has btc_symbol parameter,
it gets converted to the correct exchange-specific format.
"""

import unittest
from unittest.mock import MagicMock, patch

from utils.instrument_helpers import convert_to_exchange_format, format_aux_instrument_id


class TestBtcSymbolConversion(unittest.TestCase):
    """Test btc_symbol conversion in live engine"""

    def test_btc_symbol_to_okx_format(self):
        """Test that BTCUSDT gets converted to BTC-USDT-SWAP.OKX"""
        # Simulate what happens in load_strategy_instance()
        btc_symbol = "BTCUSDT"
        template_inst_id = "ETH-USDT-SWAP.OKX"

        # Step 1: format_aux_instrument_id
        btc_inst_id = format_aux_instrument_id(btc_symbol, template_inst_id=template_inst_id)
        self.assertEqual(btc_inst_id, "BTCUSDT-SWAP.OKX")

        # Step 2: convert_to_exchange_format
        venue = template_inst_id.split(".")[-1]
        final_inst_id = convert_to_exchange_format(btc_inst_id, venue)
        self.assertEqual(final_inst_id, "BTC-USDT-SWAP.OKX")

    def test_btc_symbol_to_binance_format(self):
        """Test that BTCUSDT stays as BTCUSDT-PERP.BINANCE for Binance"""
        btc_symbol = "BTCUSDT"
        template_inst_id = "ETHUSDT-PERP.BINANCE"

        # Step 1: format_aux_instrument_id
        btc_inst_id = format_aux_instrument_id(btc_symbol, template_inst_id=template_inst_id)
        self.assertEqual(btc_inst_id, "BTCUSDT-PERP.BINANCE")

        # Step 2: convert_to_exchange_format (should be no-op for Binance)
        venue = template_inst_id.split(".")[-1]
        final_inst_id = convert_to_exchange_format(btc_inst_id, venue)
        self.assertEqual(final_inst_id, "BTCUSDT-PERP.BINANCE")

    def test_various_okx_templates(self):
        """Test btc_symbol conversion with various OKX templates"""
        btc_symbol = "BTCUSDT"
        test_cases = [
            ("SOL-USDT-SWAP.OKX", "BTC-USDT-SWAP.OKX"),
            ("BNB-USDT-SWAP.OKX", "BTC-USDT-SWAP.OKX"),
            ("DOGE-USDT-PERP.OKX", "BTC-USDT-PERP.OKX"),
        ]

        for template, expected in test_cases:
            with self.subTest(template=template):
                btc_inst_id = format_aux_instrument_id(btc_symbol, template_inst_id=template)
                venue = template.split(".")[-1]
                final_inst_id = convert_to_exchange_format(btc_inst_id, venue)
                self.assertEqual(final_inst_id, expected)


if __name__ == "__main__":
    unittest.main()
