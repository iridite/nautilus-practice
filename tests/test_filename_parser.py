"""
测试 filename_parser 模块
"""

import unittest
from pathlib import Path

from utils.filename_parser import FilenameParser, ParsedFilename


class TestFilenameParser(unittest.TestCase):
    """测试文件名解析器"""

    def test_parse_underscore_format(self):
        """测试下划线格式: okx-BTCUSDT-1h-2020-01-01_2026-01-14.csv"""
        filename = "okx-BTCUSDT-1h-2020-01-01_2026-01-14.csv"
        result = FilenameParser.parse(filename)

        self.assertIsNotNone(result)
        self.assertEqual(result.exchange, "okx")
        self.assertEqual(result.symbol, "BTCUSDT")
        self.assertEqual(result.timeframe, "1h")
        self.assertEqual(result.start_date, "2020-01-01")
        self.assertEqual(result.end_date, "2026-01-14")

    def test_parse_dash_format(self):
        """测试横线格式: binance-DOGEUSDT-1h-2025-12-01-2025-12-30.csv"""
        filename = "binance-DOGEUSDT-1h-2025-12-01-2025-12-30.csv"
        result = FilenameParser.parse(filename)

        self.assertIsNotNone(result)
        self.assertEqual(result.exchange, "binance")
        self.assertEqual(result.symbol, "DOGEUSDT")
        self.assertEqual(result.timeframe, "1h")
        self.assertEqual(result.start_date, "2025-12-01")
        self.assertEqual(result.end_date, "2025-12-30")

    def test_parse_single_date_format(self):
        """测试单日期格式: binance-DOGEUSDT-1h-2025-12-01.csv"""
        filename = "binance-DOGEUSDT-1h-2025-12-01.csv"
        result = FilenameParser.parse(filename)

        self.assertIsNotNone(result)
        self.assertEqual(result.exchange, "binance")
        self.assertEqual(result.symbol, "DOGEUSDT")
        self.assertEqual(result.timeframe, "1h")
        self.assertEqual(result.start_date, "2025-12-01")
        self.assertEqual(result.end_date, "2025-12-01")

    def test_parse_with_path_object(self):
        """测试使用 Path 对象"""
        path = Path("/data/raw/okx-BTCUSDT-1h-2020-01-01_2026-01-14.csv")
        result = FilenameParser.parse(path)

        self.assertIsNotNone(result)
        self.assertEqual(result.exchange, "okx")
        self.assertEqual(result.symbol, "BTCUSDT")

    def test_parse_invalid_format(self):
        """测试无效格式"""
        invalid_filenames = [
            "invalid.csv",
            "BTCUSDT-1h.csv",
            "okx-BTCUSDT.csv",
            "okx-BTCUSDT-1h.csv",
            "okx_BTCUSDT_1h_2020-01-01.csv",
            "not-a-csv-file.txt",
        ]

        for filename in invalid_filenames:
            result = FilenameParser.parse(filename)
            self.assertIsNone(result, f"Expected None for {filename}")

    def test_parse_different_timeframes(self):
        """测试不同时间框架"""
        timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]

        for tf in timeframes:
            filename = f"binance-ETHUSDT-{tf}-2025-01-01-2025-01-31.csv"
            result = FilenameParser.parse(filename)
            self.assertIsNotNone(result)
            self.assertEqual(result.timeframe, tf)

    def test_parse_different_symbols(self):
        """测试不同交易对"""
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

        for symbol in symbols:
            filename = f"binance-{symbol}-1h-2025-01-01-2025-01-31.csv"
            result = FilenameParser.parse(filename)
            self.assertIsNotNone(result)
            self.assertEqual(result.symbol, symbol)

    def test_parsed_filename_dataclass(self):
        """测试 ParsedFilename 数据类"""
        parsed = ParsedFilename(
            exchange="binance",
            symbol="BTCUSDT",
            timeframe="1h",
            start_date="2025-01-01",
            end_date="2025-01-31",
        )

        self.assertEqual(parsed.exchange, "binance")
        self.assertEqual(parsed.symbol, "BTCUSDT")
        self.assertEqual(parsed.timeframe, "1h")
        self.assertEqual(parsed.start_date, "2025-01-01")
        self.assertEqual(parsed.end_date, "2025-01-31")


if __name__ == "__main__":
    unittest.main()
