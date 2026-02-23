"""
测试 universe 模块
"""

import json
import tempfile
import unittest
from pathlib import Path

from core.exceptions import UniverseParseError
from core.schemas import InstrumentType
from utils.universe import (
    extract_universe_symbols,
    load_universe_file,
    load_universe_symbols_from_file,
    parse_universe_symbols,
    resolve_universe_path,
)


class TestUniverseModule(unittest.TestCase):
    """测试 Universe 模块"""

    def setUp(self):
        """创建临时测试文件"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

    def tearDown(self):
        """清理临时文件"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_universe_file_success(self):
        """测试成功加载 Universe JSON 文件"""
        universe_data = {"2025-01": ["BTCUSDT", "ETHUSDT"], "2025-02": ["BTCUSDT", "SOLUSDT"]}

        universe_file = self.temp_path / "universe.json"
        with open(universe_file, "w") as f:
            json.dump(universe_data, f)

        result = load_universe_file(universe_file)
        self.assertEqual(result, universe_data)

    def test_load_universe_file_not_found(self):
        """测试文件不存在"""
        with self.assertRaises(UniverseParseError) as ctx:
            load_universe_file(self.temp_path / "nonexistent.json")
        self.assertIn("not found", str(ctx.exception))

    def test_load_universe_file_not_json(self):
        """测试非 JSON 文件"""
        txt_file = self.temp_path / "universe.txt"
        txt_file.write_text("not json")

        with self.assertRaises(UniverseParseError) as ctx:
            load_universe_file(txt_file)
        self.assertIn("must be JSON format", str(ctx.exception))

    def test_load_universe_file_invalid_json(self):
        """测试无效 JSON 格式"""
        invalid_file = self.temp_path / "invalid.json"
        invalid_file.write_text("{invalid json")

        with self.assertRaises(UniverseParseError) as ctx:
            load_universe_file(invalid_file)
        self.assertIn("Invalid JSON format", str(ctx.exception))

    def test_load_universe_file_not_dict(self):
        """测试 JSON 不是字典"""
        list_file = self.temp_path / "list.json"
        with open(list_file, "w") as f:
            json.dump(["BTCUSDT", "ETHUSDT"], f)

        with self.assertRaises(UniverseParseError) as ctx:
            load_universe_file(list_file)
        self.assertIn("must contain a JSON object", str(ctx.exception))

    def test_load_universe_file_invalid_structure(self):
        """测试无效的数据结构"""
        invalid_data = {"2025-01": "BTCUSDT"}  # 应该是列表

        invalid_file = self.temp_path / "invalid_structure.json"
        with open(invalid_file, "w") as f:
            json.dump(invalid_data, f)

        with self.assertRaises(UniverseParseError) as ctx:
            load_universe_file(invalid_file)
        self.assertIn("must contain a list", str(ctx.exception))

    def test_extract_universe_symbols_all_months(self):
        """测试提取所有月份的符号"""
        universe_data = {"2025-01": ["BTCUSDT", "ETHUSDT"], "2025-02": ["BTCUSDT", "SOLUSDT"]}

        symbols = extract_universe_symbols(universe_data)
        self.assertEqual(symbols, {"BTCUSDT", "ETHUSDT", "SOLUSDT"})

    def test_extract_universe_symbols_specific_months(self):
        """测试提取特定月份的符号"""
        universe_data = {
            "2025-01": ["BTCUSDT", "ETHUSDT"],
            "2025-02": ["BTCUSDT", "SOLUSDT"],
            "2025-03": ["BNBUSDT"],
        }

        symbols = extract_universe_symbols(universe_data, months=["2025-01", "2025-03"])
        self.assertEqual(symbols, {"BTCUSDT", "ETHUSDT", "BNBUSDT"})

    def test_extract_universe_symbols_nonexistent_month(self):
        """测试提取不存在的月份（应该警告但不报错）"""
        universe_data = {"2025-01": ["BTCUSDT", "ETHUSDT"]}

        symbols = extract_universe_symbols(universe_data, months=["2025-01", "2025-99"])
        self.assertEqual(symbols, {"BTCUSDT", "ETHUSDT"})

    def test_load_universe_symbols_from_file_success(self):
        """测试从文本文件加载符号"""
        symbols_file = self.temp_path / "symbols.txt"
        symbols_file.write_text("BTCUSDT\nETHUSDT\n# Comment\nSOLUSDT\n\n")

        symbols = load_universe_symbols_from_file(symbols_file)
        self.assertEqual(symbols, ["BTCUSDT", "ETHUSDT", "SOLUSDT"])

    def test_load_universe_symbols_from_file_with_duplicates(self):
        """测试去重功能"""
        symbols_file = self.temp_path / "symbols.txt"
        symbols_file.write_text("BTCUSDT\nETHUSDT\nBTCUSDT\n")

        symbols = load_universe_symbols_from_file(symbols_file)
        self.assertEqual(symbols, ["BTCUSDT", "ETHUSDT"])

    def test_load_universe_symbols_from_file_case_insensitive(self):
        """测试大小写转换"""
        symbols_file = self.temp_path / "symbols.txt"
        symbols_file.write_text("btcusdt\nEthUsdt\n")

        symbols = load_universe_symbols_from_file(symbols_file)
        self.assertEqual(symbols, ["BTCUSDT", "ETHUSDT"])

    def test_load_universe_symbols_from_file_not_found(self):
        """测试文件不存在（返回空列表）"""
        symbols = load_universe_symbols_from_file(self.temp_path / "nonexistent.txt")
        self.assertEqual(symbols, [])

    def test_parse_universe_symbols(self):
        """测试解析 Universe 符号为 Instrument ID"""
        universe_symbols = {"BTCUSDT", "ETHUSDT"}

        instrument_ids = parse_universe_symbols(
            universe_symbols, venue="BINANCE", base_currency="USDT", inst_type=InstrumentType.SWAP
        )

        self.assertEqual(len(instrument_ids), 2)
        self.assertTrue(any("BTC" in id for id in instrument_ids))
        self.assertTrue(any("ETH" in id for id in instrument_ids))

    def test_parse_universe_symbols_with_colon(self):
        """测试带冒号的符号"""
        universe_symbols = {"BTCUSDT:BINANCE"}

        instrument_ids = parse_universe_symbols(
            universe_symbols, venue="BINANCE", base_currency="USDT", inst_type=InstrumentType.SWAP
        )

        self.assertEqual(len(instrument_ids), 1)

    def test_resolve_universe_path_absolute(self):
        """测试绝对路径"""
        universe_file = self.temp_path / "universe.json"
        universe_file.write_text("{}")

        result = resolve_universe_path(str(universe_file), self.temp_path)
        self.assertEqual(result, universe_file)

    def test_resolve_universe_path_relative(self):
        """测试相对路径"""
        data_dir = self.temp_path / "data"
        data_dir.mkdir()
        universe_file = data_dir / "universe.json"
        universe_file.write_text("{}")

        result = resolve_universe_path("universe.json", self.temp_path)
        self.assertEqual(result, universe_file)

    def test_resolve_universe_path_not_found(self):
        """测试文件不存在"""
        result = resolve_universe_path("nonexistent.json", self.temp_path)
        self.assertIsNone(result)

    def test_resolve_universe_path_none(self):
        """测试 None 输入"""
        result = resolve_universe_path(None, self.temp_path)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
