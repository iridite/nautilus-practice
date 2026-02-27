#!/usr/bin/env python3
"""
Unit tests for utils.instrument_helpers
Run with:
    uv run python -m unittest discover -s tests -p "test_*.py" -v
"""

import unittest

from utils.instrument_helpers import (
    build_bar_type_from_timeframe,
    format_aux_instrument_id,
    parse_instrument_id,
)


class TestInstrumentHelpers(unittest.TestCase):
    def test_format_aux_with_usdt_and_template(self):
        # Template provides contract type and venue; aux_symbol in compact form
        aux = "BTCUSDT"
        template = "AVAX-USDT-PERP.OKX"
        out = format_aux_instrument_id(aux, template_inst_id=template)
        self.assertEqual(out, "BTCUSDT-PERP.OKX")

    def test_format_aux_with_lowercase_base_and_template(self):
        # Lowercase aux and simple base (no USDT) should default to base-USDT
        aux = "btc"
        template = "AVAX-USDT-PERP.OKX"
        out = format_aux_instrument_id(aux, template_inst_id=template)
        self.assertEqual(out, "BTCUSDT-PERP.OKX")

    def test_format_aux_with_hyphenated_aux_and_template(self):
        # Already hyphenated aux_symbol should be preserved (normalized to uppercase)
        aux = "btc-usdt"
        template = "AVAX-USDT-PERP.OKX"
        out = format_aux_instrument_id(aux, template_inst_id=template)
        self.assertEqual(out, "BTC-USDT-PERP.OKX")

    def test_format_aux_inherits_inst_type_from_template_without_venue_arg(self):
        # Template without explicit venue; provide venue separately
        aux = "BTCUSDT"
        template = "AVAX-USDT-SWAP"  # no venue in template
        out = format_aux_instrument_id(aux, template_inst_id=template, venue="OKX")
        self.assertEqual(out, "BTCUSDT-SWAP.OKX")

    def test_format_aux_requires_venue_if_no_template(self):
        # If no template provided, venue must be supplied
        aux = "BTCUSDT"
        with self.assertRaises(ValueError):
            format_aux_instrument_id(aux, template_inst_id=None, venue=None)

    def test_format_aux_with_aux_that_is_already_instrument_and_template(self):
        # aux_symbol contains a venue; function should strip and recompose correctly
        aux = "BTC-USDT-PERP.OKX"
        template = "AVAX-USDT-PERP.OKX"
        out = format_aux_instrument_id(aux, template_inst_id=template)
        self.assertEqual(out, "BTC-USDT-PERP.OKX")

    def test_build_bar_type_default_1d(self):
        inst = "BTC-USDT-PERP.OKX"
        out = build_bar_type_from_timeframe(inst, "1d")
        self.assertEqual(out, "BTC-USDT-PERP.OKX-1-DAY-LAST-EXTERNAL")

    def test_build_bar_type_minutes_and_hours(self):
        inst = "BTC-USDT-PERP.OKX"
        out_m = build_bar_type_from_timeframe(inst, "15m", price_type="MID", origination="INTERNAL")
        self.assertEqual(out_m, "BTC-USDT-PERP.OKX-15-MINUTE-MID-INTERNAL")

        out_h = build_bar_type_from_timeframe(inst, "2h")
        self.assertEqual(out_h, "BTC-USDT-PERP.OKX-2-HOUR-LAST-EXTERNAL")

    def test_parse_instrument_id_with_venue_and_type(self):
        inst = "AVAX-USDT-PERP.OKX"
        symbol, inst_type, venue = parse_instrument_id(inst)
        self.assertEqual(symbol, "AVAX-USDT")
        self.assertEqual(inst_type, "PERP")
        self.assertEqual(venue, "OKX")

    def test_parse_instrument_id_without_venue(self):
        inst = "BTC-USDT-PERP"
        symbol, inst_type, venue = parse_instrument_id(inst)
        self.assertEqual(symbol, "BTC-USDT")
        self.assertEqual(inst_type, "PERP")
        self.assertIsNone(venue)

    def test_parse_instrument_id_no_type_fallback(self):
        inst = "BTC-USDT"
        symbol, inst_type, venue = parse_instrument_id(inst)
        self.assertEqual(symbol, "BTC-USDT")
        # When explicit type token missing, default is PERP
        self.assertEqual(inst_type, "PERP")
        self.assertIsNone(venue)


if __name__ == "__main__":
    unittest.main()
