#!/usr/bin/env python3
"""
Tests for exchange-specific format conversion.

Ensures that instrument IDs are correctly converted to exchange-specific formats,
particularly for OKX which requires hyphenated symbols (BTC-USDT-SWAP).
"""

import unittest
from utils.instrument_helpers import convert_to_exchange_format


class TestExchangeFormatConversion(unittest.TestCase):
    """Test cases for convert_to_exchange_format()"""

    def test_okx_btcusdt_to_hyphenated(self):
        """Test OKX: BTCUSDT-SWAP.OKX → BTC-USDT-SWAP.OKX"""
        result = convert_to_exchange_format("BTCUSDT-SWAP.OKX", "OKX")
        self.assertEqual(result, "BTC-USDT-SWAP.OKX")

    def test_okx_ethusdt_to_hyphenated(self):
        """Test OKX: ETHUSDT-SWAP.OKX → ETH-USDT-SWAP.OKX"""
        result = convert_to_exchange_format("ETHUSDT-SWAP.OKX", "OKX")
        self.assertEqual(result, "ETH-USDT-SWAP.OKX")

    def test_okx_already_hyphenated(self):
        """Test OKX: Already hyphenated format passes through"""
        result = convert_to_exchange_format("BTC-USDT-SWAP.OKX", "OKX")
        self.assertEqual(result, "BTC-USDT-SWAP.OKX")

    def test_okx_perp_format(self):
        """Test OKX: BTCUSDT-PERP.OKX → BTC-USDT-PERP.OKX"""
        result = convert_to_exchange_format("BTCUSDT-PERP.OKX", "OKX")
        self.assertEqual(result, "BTC-USDT-PERP.OKX")

    def test_okx_spot_format(self):
        """Test OKX: BTCUSDT-SPOT.OKX → BTC-USDT-SPOT.OKX"""
        result = convert_to_exchange_format("BTCUSDT-SPOT.OKX", "OKX")
        self.assertEqual(result, "BTC-USDT-SPOT.OKX")

    def test_binance_no_conversion(self):
        """Test Binance: Format remains unchanged (no hyphens needed)"""
        result = convert_to_exchange_format("BTCUSDT-PERP.BINANCE", "BINANCE")
        self.assertEqual(result, "BTCUSDT-PERP.BINANCE")

    def test_binance_spot_no_conversion(self):
        """Test Binance: Spot format remains unchanged"""
        result = convert_to_exchange_format("BTCUSDT.BINANCE", "BINANCE")
        self.assertEqual(result, "BTCUSDT.BINANCE")

    def test_okx_lowercase_venue(self):
        """Test OKX: Venue name is case-insensitive"""
        result = convert_to_exchange_format("BTCUSDT-SWAP.OKX", "okx")
        self.assertEqual(result, "BTC-USDT-SWAP.OKX")

    def test_okx_various_symbols(self):
        """Test OKX: Various symbols are correctly converted"""
        test_cases = [
            ("SOLUSDT-SWAP.OKX", "SOL-USDT-SWAP.OKX"),
            ("BNBUSDT-SWAP.OKX", "BNB-USDT-SWAP.OKX"),
            ("DOGEUSDT-SWAP.OKX", "DOGE-USDT-SWAP.OKX"),
            ("AVAXUSDT-PERP.OKX", "AVAX-USDT-PERP.OKX"),
        ]
        for input_id, expected in test_cases:
            with self.subTest(input_id=input_id):
                result = convert_to_exchange_format(input_id, "OKX")
                self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
