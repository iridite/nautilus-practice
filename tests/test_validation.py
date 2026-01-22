"""
验证工具模块单元测试

测试内容：
1. check_data_exists() - 数据文件存在性检查
2. 文件大小验证
3. 路径处理和边界情况
4. 错误处理测试

Usage:
    uv run python -m unittest tests.test_validation -v
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils.validation import check_data_exists


class TestValidation(unittest.TestCase):
    """验证工具测试类"""

    def setUp(self):
        """设置测试环境"""
        # 创建临时目录用于测试
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_base_dir = Path(self.temp_dir.name)
        
        # 创建测试用的目录结构
        (self.test_base_dir / "data" / "raw" / "BTCUSDT").mkdir(parents=True, exist_ok=True)
        
        # 创建测试文件 - 使用正确的文件名格式
        self.large_file = self.test_base_dir / "data" / "raw" / "BTCUSDT" / "test-BTCUSDT-1h-2024-01-01_2024-12-31.csv"
        self.small_file = self.test_base_dir / "data" / "raw" / "BTCUSDT" / "test-BTCUSDT-1h-2024-01-01_2024-12-31.csv"
        self.empty_file = self.test_base_dir / "data" / "raw" / "BTCUSDT" / "test-BTCUSDT-1h-2024-01-01_2024-12-31.csv"
        
        # 写入测试数据
        with open(self.large_file, 'w') as f:
            f.write("timestamp,open,high,low,close,volume\n")
            # 写入足够大的数据（大于10KB）
            for i in range(1000):
                f.write(f"{i},100.0,101.0,99.0,100.5,1000.0\n")
        
        # 为了测试不同大小的文件，我们需要不同的文件名
        self.small_file_name = "test-BTCUSDT-1h-small.csv"
        self.empty_file_name = "test-BTCUSDT-1h-empty.csv"
        
        self.small_file_path = self.test_base_dir / "data" / "raw" / "BTCUSDT" / self.small_file_name
        self.empty_file_path = self.test_base_dir / "data" / "raw" / "BTCUSDT" / self.empty_file_name
        
        with open(self.small_file_path, 'w') as f:
            f.write("timestamp,open,high,low,close,volume\n")
            f.write("1,100.0,101.0,99.0,100.5,1000.0\n")
        
        # 创建空文件
        self.empty_file_path.touch()

    def tearDown(self):
        """清理测试环境"""
        self.temp_dir.cleanup()

    def test_check_data_exists_large_file(self):
        """测试大文件检查通过"""
        symbols = ["BTCUSDT"]
        start_date = "2024-01-01"
        end_date = "2024-12-31"
        timeframe = "1h"
        exchange_id = "test"
        
        result = check_data_exists(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe,
            exchange_id=exchange_id,
            base_dir=self.test_base_dir,
            filename_template=lambda ex, sym, tf, start, end: f"{ex}-{sym}-{tf}-{start}_{end}.csv"
        )
        
        # 大文件应该被认为存在
        self.assertTrue(result)

    def test_check_data_exists_small_file(self):
        """测试小文件检查失败"""
        symbols = ["BTCUSDT"]
        start_date = "small"
        end_date = ""
        timeframe = "1h"
        exchange_id = "test"
        
        result = check_data_exists(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe,
            exchange_id=exchange_id,
            base_dir=self.test_base_dir,
            filename_template=lambda ex, sym, tf, start, end: f"{ex}-{sym}-{tf}-{start}.csv"
        )
        
        # 小文件应该被认为不存在（小于10KB）
        self.assertFalse(result)

    def test_check_data_exists_missing_file(self):
        """测试不存在文件的情况"""
        symbols = ["ETHUSDT"]  # 不存在的符号
        start_date = "2024-01-01"
        end_date = "2024-12-31"
        timeframe = "1h"
        exchange_id = "test"
        
        result = check_data_exists(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe,
            exchange_id=exchange_id,
            base_dir=self.test_base_dir,
            filename_template=lambda ex, sym, tf, start, end: f"{ex}-{sym}-{tf}-{start}_{end}.csv"
        )
        
        self.assertFalse(result)

    def test_check_data_exists_empty_file(self):
        """测试空文件的情况"""
        symbols = ["BTCUSDT"]
        start_date = "empty"
        end_date = ""
        timeframe = "1h"
        exchange_id = "test"
        
        result = check_data_exists(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe,
            exchange_id=exchange_id,
            base_dir=self.test_base_dir,
            filename_template=lambda ex, sym, tf, start, end: f"{ex}-{sym}-{tf}-{start}.csv"
        )
        
        # 空文件应该被认为不存在
        self.assertFalse(result)

    def test_check_data_exists_multiple_symbols_all_exist(self):
        """测试多个符号都存在的情况"""
        # 创建第二个符号的文件
        (self.test_base_dir / "data" / "raw" / "ETHUSDT").mkdir(parents=True, exist_ok=True)
        eth_file = self.test_base_dir / "data" / "raw" / "ETHUSDT" / "test-ETHUSDT-1h-2024-01-01_2024-12-31.csv"
        
        with open(eth_file, 'w') as f:
            f.write("timestamp,open,high,low,close,volume\n")
            for i in range(1000):
                f.write(f"{i},200.0,201.0,199.0,200.5,2000.0\n")
        
        symbols = ["BTCUSDT", "ETHUSDT"]
        start_date = "2024-01-01"
        end_date = "2024-12-31"
        timeframe = "1h"
        exchange_id = "test"
        
        result = check_data_exists(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe,
            exchange_id=exchange_id,
            base_dir=self.test_base_dir,
            filename_template=lambda ex, sym, tf, start, end: f"{ex}-{sym}-{tf}-{start}_{end}.csv"
        )
        
        self.assertTrue(result)

    def test_check_data_exists_multiple_symbols_partial_exist(self):
        """测试多个符号部分存在的情况"""
        symbols = ["BTCUSDT", "ETHUSDT"]  # ETHUSDT不存在
        start_date = "2024-01-01"
        end_date = "2024-12-31"
        timeframe = "1h"
        exchange_id = "test"
        
        result = check_data_exists(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe,
            exchange_id=exchange_id,
            base_dir=self.test_base_dir,
            filename_template=lambda ex, sym, tf, start, end: f"{ex}-{sym}-{tf}-{start}_{end}.csv"
        )
        
        # 只要有一个不存在就返回False
        self.assertFalse(result)

    def test_check_data_exists_custom_size_threshold(self):
        """测试自定义大小阈值"""
        symbols = ["BTCUSDT"]
        start_date = "2024-01-01"
        end_date = "2024-12-31"
        timeframe = "1h"
        exchange_id = "test"
        
        # 使用很大的阈值，使得现有大文件也被认为太小
        large_threshold = 1024 * 1024  # 1MB
        
        result = check_data_exists(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe,
            exchange_id=exchange_id,
            base_dir=self.test_base_dir,
            filename_template=lambda ex, sym, tf, start, end: f"{ex}-{sym}-{tf}-{start}_{end}.csv",
            min_size_bytes=large_threshold
        )
        
        # 以更大的阈值检查，现有文件应该被认为太小
        self.assertFalse(result)

    def test_check_data_exists_custom_filename_template(self):
        """测试自定义文件名模板"""
        # 创建使用不同命名规则的文件
        custom_file = self.test_base_dir / "data" / "raw" / "BTCUSDT" / "custom_BTCUSDT_1h.csv"
        with open(custom_file, 'w') as f:
            f.write("timestamp,open,high,low,close,volume\n")
            for i in range(1000):
                f.write(f"{i},100.0,101.0,99.0,100.5,1000.0\n")
        
        symbols = ["BTCUSDT"]
        start_date = "2024-01-01"
        end_date = "2024-12-31"
        timeframe = "1h"
        exchange_id = "custom"
        
        result = check_data_exists(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe,
            exchange_id=exchange_id,
            base_dir=self.test_base_dir,
            filename_template=lambda ex, sym, tf, start, end: f"{ex}_{sym}_{tf}.csv"
        )
        
        self.assertTrue(result)

    def test_check_data_exists_path_error_handling(self):
        """测试路径错误处理"""
        # 使用不存在的基础目录
        nonexistent_dir = Path("/definitely/does/not/exist")
        
        symbols = ["BTCUSDT"]
        start_date = "2024-01-01"
        end_date = "2024-12-31"
        timeframe = "1h"
        exchange_id = "test"
        
        result = check_data_exists(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe,
            exchange_id=exchange_id,
            base_dir=nonexistent_dir,
            filename_template=lambda ex, sym, tf, start, end: f"{ex}-{sym}-{tf}-{start}_{end}.csv"
        )
        
        # 不存在的路径应该返回False
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()