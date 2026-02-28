"""
Unit tests for symbol normalization functionality.

Tests the normalize_symbol_to_internal() function from utils.instrument_helpers.
"""

import unittest
from utils.instrument_helpers import normalize_symbol_to_internal


class TestSymbolNormalization(unittest.TestCase):
    """Test cases for normalize_symbol_to_internal()"""

    def test_normalize_okx_swap_format(self):
        """Test OKX SWAP format conversion: BTC-USDT-SWAP → BTCUSDT"""
        result = normalize_symbol_to_internal("BTC-USDT-SWAP")
        self.assertEqual(result, "BTCUSDT")

    def test_normalize_okx_swap_with_venue(self):
        """Test OKX SWAP with venue suffix: ETH-USDT-SWAP.OKX → ETHUSDT"""
        result = normalize_symbol_to_internal("ETH-USDT-SWAP.OKX")
        self.assertEqual(result, "ETHUSDT")

    def test_normalize_binance_format(self):
        """Test Binance format passthrough: BTCUSDT → BTCUSDT"""
        result = normalize_symbol_to_internal("BTCUSDT")
        self.assertEqual(result, "BTCUSDT")

    def test_normalize_binance_perp_format(self):
        """Test Binance PERP format: BTCUSDT-PERP.BINANCE → BTCUSDT"""
        result = normalize_symbol_to_internal("BTCUSDT-PERP.BINANCE")
        self.assertEqual(result, "BTCUSDT")

    def test_normalize_lowercase_input(self):
        """Test lowercase input is uppercased: btc-usdt-swap → BTCUSDT"""
        result = normalize_symbol_to_internal("btc-usdt-swap")
        self.assertEqual(result, "BTCUSDT")

    def test_normalize_mixed_case_input(self):
        """Test mixed case input: Eth-USDT-Swap → ETHUSDT"""
        result = normalize_symbol_to_internal("Eth-USDT-Swap")
        self.assertEqual(result, "ETHUSDT")

    def test_normalize_with_whitespace(self):
        """Test input with whitespace is trimmed: ' BTC-USDT-SWAP ' → BTCUSDT"""
        result = normalize_symbol_to_internal("  BTC-USDT-SWAP  ")
        self.assertEqual(result, "BTCUSDT")

    def test_normalize_empty_string_raises_error(self):
        """Test empty string raises ValueError"""
        with self.assertRaises(ValueError) as context:
            normalize_symbol_to_internal("")
        self.assertIn("non-empty", str(context.exception))

    def test_normalize_whitespace_only_raises_error(self):
        """Test whitespace-only string raises ValueError"""
        with self.assertRaises(ValueError) as context:
            normalize_symbol_to_internal("   ")
        self.assertIn("non-empty", str(context.exception))

    def test_normalize_multiple_hyphens(self):
        """Test symbol with multiple hyphens: SOL-USDT-PERP → SOLUSDT"""
        result = normalize_symbol_to_internal("SOL-USDT-PERP")
        self.assertEqual(result, "SOLUSDT")

    def test_normalize_various_inst_types(self):
        """Test various instrument types are stripped correctly"""
        test_cases = [
            ("BTC-USDT-SWAP", "BTCUSDT"),
            ("ETH-USDT-PERP", "ETHUSDT"),
            ("SOL-USDT-FUTURE", "SOLUSDT"),
            ("BNB-USDT-SPOT", "BNBUSDT"),
            ("DOGE-USDT-LINEAR", "DOGEUSDT"),
        ]
        for input_symbol, expected in test_cases:
            with self.subTest(input_symbol=input_symbol):
                result = normalize_symbol_to_internal(input_symbol)
                self.assertEqual(result, expected)

    def test_normalize_preserves_non_usdt_pairs(self):
        """Test non-USDT pairs are processed (with warning logged)"""
        # This should still work but log a warning
        result = normalize_symbol_to_internal("BTC-BUSD-SWAP")
        self.assertEqual(result, "BTCBUSD")


if __name__ == "__main__":
    unittest.main()
