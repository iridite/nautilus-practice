"""
测试 utils/data_file_checker.py 数据文件检查模块
"""

import unittest
from pathlib import Path
import tempfile
import os

from utils.data_file_checker import (
    check_single_data_file,
    check_oi_data_exists,
    check_funding_data_exists,
)


class TestCheckSingleDataFile(unittest.TestCase):
    """测试 check_single_data_file 函数"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.base_dir = Path(self.temp_dir)

    def tearDown(self):
        """清理测试环境"""
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_file_exists_and_valid(self):
        """测试文件存在且大小有效"""
        # 创建测试文件
        safe_symbol = "BTCUSDT"
        data_dir = self.base_dir / "data" / "raw" / safe_symbol
        data_dir.mkdir(parents=True, exist_ok=True)

        filename = "okx-BTCUSDT-1h-2024-01-01_2024-01-31.csv"
        filepath = data_dir / filename

        # 写入足够大的数据
        with open(filepath, "w") as f:
            f.write("timestamp,open,high,low,close,volume\n" * 1000)

        exists, path = check_single_data_file(
            symbol="BTC/USDT",
            start_date="2024-01-01",
            end_date="2024-01-31",
            timeframe="1h",
            exchange="OKX",
            base_dir=self.base_dir,
            min_size_bytes=10 * 1024,
        )

        self.assertTrue(exists)
        self.assertIn("BTCUSDT", path)

    def test_file_not_exists(self):
        """测试文件不存在"""
        exists, path = check_single_data_file(
            symbol="BTC/USDT",
            start_date="2024-01-01",
            end_date="2024-01-31",
            timeframe="1h",
            exchange="OKX",
            base_dir=self.base_dir,
        )

        self.assertFalse(exists)
        self.assertIn("BTCUSDT", path)

    def test_file_too_small(self):
        """测试文件太小"""
        safe_symbol = "ETHUSDT"
        data_dir = self.base_dir / "data" / "raw" / safe_symbol
        data_dir.mkdir(parents=True, exist_ok=True)

        filename = "okx-ETHUSDT-1h-2024-01-01_2024-01-31.csv"
        filepath = data_dir / filename

        # 写入很小的数据
        with open(filepath, "w") as f:
            f.write("test")

        exists, path = check_single_data_file(
            symbol="ETH/USDT",
            start_date="2024-01-01",
            end_date="2024-01-31",
            timeframe="1h",
            exchange="OKX",
            base_dir=self.base_dir,
            min_size_bytes=10 * 1024,
        )

        self.assertFalse(exists)
        self.assertIn("ETHUSDT", path)

    def test_symbol_with_slash(self):
        """测试带斜杠的交易对符号"""
        safe_symbol = "BTCUSDT"
        data_dir = self.base_dir / "data" / "raw" / safe_symbol
        data_dir.mkdir(parents=True, exist_ok=True)

        # 文件名格式：exchange-symbol-timeframe-start_end.csv
        filename = "binance-BTCUSDT-5m-2024-02-01_2024-02-28.csv"
        filepath = data_dir / filename

        # 写入足够大的数据（大于 10KB）
        with open(filepath, "w") as f:
            f.write("timestamp,open,high,low,close,volume\n" * 500)

        exists, path = check_single_data_file(
            symbol="BTC/USDT",
            start_date="2024-02-01",
            end_date="2024-02-28",
            timeframe="5m",
            exchange="binance",  # 小写
            base_dir=self.base_dir,
        )

        self.assertTrue(exists)
        # 路径中不应该有斜杠
        self.assertNotIn("/USDT", path)
        self.assertIn("BTCUSDT", path)

    def test_custom_min_size(self):
        """测试自定义最小文件大小"""
        symbol = "SOL/USDT"
        safe_symbol = "SOLUSDT"
        data_dir = self.base_dir / "data" / "raw" / safe_symbol
        data_dir.mkdir(parents=True, exist_ok=True)

        filename = "okx-SOLUSDT-1h-2024-01-01_2024-01-31.csv"
        filepath = data_dir / filename

        # 写入 5KB 数据
        with open(filepath, "w") as f:
            f.write("x" * 5000)

        # 使用 1KB 最小大小 - 应该通过
        exists1, _ = check_single_data_file(
            symbol=symbol,
            start_date="2024-01-01",
            end_date="2024-01-31",
            timeframe="1h",
            exchange="OKX",
            base_dir=self.base_dir,
            min_size_bytes=1024,
        )
        self.assertTrue(exists1)

        # 使用 10KB 最小大小 - 应该失败
        exists2, _ = check_single_data_file(
            symbol=symbol,
            start_date="2024-01-01",
            end_date="2024-01-31",
            timeframe="1h",
            exchange="OKX",
            base_dir=self.base_dir,
            min_size_bytes=10 * 1024,
        )
        self.assertFalse(exists2)


class TestCheckOiDataExists(unittest.TestCase):
    """测试 check_oi_data_exists 函数"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.base_dir = Path(self.temp_dir)

    def tearDown(self):
        """清理测试环境"""
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_all_files_exist(self):
        """测试所有文件都存在"""
        symbols = ["BTC/USDT", "ETH/USDT"]

        for symbol in symbols:
            safe_symbol = symbol.replace("/", "")
            data_dir = self.base_dir / "data" / "raw" / safe_symbol
            data_dir.mkdir(parents=True, exist_ok=True)

            filename = f"okx-{safe_symbol}-oi-5m-2024-01-01_2024-01-31.csv"
            filepath = data_dir / filename

            # 写入足够大的数据（大于 1024 字节）
            with open(filepath, "w") as f:
                f.write("timestamp,open_interest\n" * 100)

        all_exist, missing = check_oi_data_exists(
            symbols=symbols,
            start_date="2024-01-01",
            end_date="2024-01-31",
            period="5m",
            exchange="okx",  # 小写
            base_dir=self.base_dir,
        )

        self.assertTrue(all_exist)
        self.assertEqual(len(missing), 0)

    def test_some_files_missing(self):
        """测试部分文件缺失"""
        symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]

        # 只创建 BTC 的文件
        safe_symbol = "BTCUSDT"
        data_dir = self.base_dir / "data" / "raw" / safe_symbol
        data_dir.mkdir(parents=True, exist_ok=True)

        filename = f"okx-{safe_symbol}-oi-5m-2024-01-01_2024-01-31.csv"
        filepath = data_dir / filename

        # 写入足够大的数据
        with open(filepath, "w") as f:
            f.write("timestamp,open_interest\n" * 100)

        all_exist, missing = check_oi_data_exists(
            symbols=symbols,
            start_date="2024-01-01",
            end_date="2024-01-31",
            period="5m",
            exchange="okx",  # 小写
            base_dir=self.base_dir,
        )

        self.assertFalse(all_exist)
        self.assertEqual(len(missing), 2)
        self.assertTrue(any("ETHUSDT" in m for m in missing))
        self.assertTrue(any("SOLUSDT" in m for m in missing))

    def test_file_too_small(self):
        """测试文件太小（小于 1024 字节）"""
        symbols = ["BTC/USDT"]
        safe_symbol = "BTCUSDT"
        data_dir = self.base_dir / "data" / "raw" / safe_symbol
        data_dir.mkdir(parents=True, exist_ok=True)

        filename = f"okx-{safe_symbol}-oi-5m-2024-01-01_2024-01-31.csv"
        filepath = data_dir / filename

        # 写入小于 1024 字节的数据
        with open(filepath, "w") as f:
            f.write("small")

        all_exist, missing = check_oi_data_exists(
            symbols=symbols,
            start_date="2024-01-01",
            end_date="2024-01-31",
            period="5m",
            exchange="OKX",
            base_dir=self.base_dir,
        )

        self.assertFalse(all_exist)
        self.assertEqual(len(missing), 1)

    def test_empty_symbols_list(self):
        """测试空符号列表"""
        all_exist, missing = check_oi_data_exists(
            symbols=[],
            start_date="2024-01-01",
            end_date="2024-01-31",
            period="5m",
            exchange="OKX",
            base_dir=self.base_dir,
        )

        self.assertTrue(all_exist)
        self.assertEqual(len(missing), 0)


class TestCheckFundingDataExists(unittest.TestCase):
    """测试 check_funding_data_exists 函数"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.base_dir = Path(self.temp_dir)

    def tearDown(self):
        """清理测试环境"""
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_all_files_exist(self):
        """测试所有文件都存在"""
        symbols = ["BTC/USDT", "ETH/USDT"]

        for symbol in symbols:
            safe_symbol = symbol.replace("/", "")
            data_dir = self.base_dir / "data" / "raw" / safe_symbol
            data_dir.mkdir(parents=True, exist_ok=True)

            filename = f"okx-{safe_symbol}-funding-2024-01-01_2024-01-31.csv"
            filepath = data_dir / filename

            with open(filepath, "w") as f:
                f.write("timestamp,funding_rate\n" * 200)

        all_exist, missing = check_funding_data_exists(
            symbols=symbols,
            start_date="2024-01-01",
            end_date="2024-01-31",
            exchange="OKX",
            base_dir=self.base_dir,
        )

        self.assertTrue(all_exist)
        self.assertEqual(len(missing), 0)

    def test_some_files_missing(self):
        """测试部分文件缺失"""
        symbols = ["BTC/USDT", "ETH/USDT"]

        # 只创建 BTC 的文件
        safe_symbol = "BTCUSDT"
        data_dir = self.base_dir / "data" / "raw" / safe_symbol
        data_dir.mkdir(parents=True, exist_ok=True)

        filename = f"binance-{safe_symbol}-funding-2024-01-01_2024-01-31.csv"
        filepath = data_dir / filename

        # 写入足够大的数据
        with open(filepath, "w") as f:
            f.write("timestamp,funding_rate\n" * 100)

        all_exist, missing = check_funding_data_exists(
            symbols=symbols,
            start_date="2024-01-01",
            end_date="2024-01-31",
            exchange="binance",  # 小写
            base_dir=self.base_dir,
        )

        self.assertFalse(all_exist)
        self.assertEqual(len(missing), 1)
        self.assertTrue(any("ETHUSDT" in m for m in missing))

    def test_file_too_small(self):
        """测试文件太小"""
        symbols = ["SOL/USDT"]
        safe_symbol = "SOLUSDT"
        data_dir = self.base_dir / "data" / "raw" / safe_symbol
        data_dir.mkdir(parents=True, exist_ok=True)

        filename = f"okx-{safe_symbol}-funding-2024-01-01_2024-01-31.csv"
        filepath = data_dir / filename

        with open(filepath, "w") as f:
            f.write("tiny")

        all_exist, missing = check_funding_data_exists(
            symbols=symbols,
            start_date="2024-01-01",
            end_date="2024-01-31",
            exchange="OKX",
            base_dir=self.base_dir,
        )

        self.assertFalse(all_exist)
        self.assertEqual(len(missing), 1)

    def test_empty_symbols_list(self):
        """测试空符号列表"""
        all_exist, missing = check_funding_data_exists(
            symbols=[],
            start_date="2024-01-01",
            end_date="2024-01-31",
            exchange="OKX",
            base_dir=self.base_dir,
        )

        self.assertTrue(all_exist)
        self.assertEqual(len(missing), 0)

    def test_multiple_missing_files(self):
        """测试多个文件缺失"""
        symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "AVAX/USDT"]

        all_exist, missing = check_funding_data_exists(
            symbols=symbols,
            start_date="2024-01-01",
            end_date="2024-01-31",
            exchange="OKX",
            base_dir=self.base_dir,
        )

        self.assertFalse(all_exist)
        self.assertEqual(len(missing), 4)


if __name__ == "__main__":
    unittest.main()
