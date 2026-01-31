"""
数据加载工具模块单元测试

测试内容：
1. load_csv_with_time_detection() - CSV加载和时间列检测
2. 时间列格式处理（datetime vs timestamp）
3. 数据类型转换和验证
4. 错误处理和边界情况

Usage:
    uv run python -m unittest tests.test_data_loader -v
"""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from utils.data_management.data_loader import load_csv_with_time_detection


class TestDataLoader(unittest.TestCase):
    """数据加载器测试类"""

    def setUp(self):
        """设置测试环境"""
        # 创建临时目录用于测试
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

        # 创建测试CSV文件
        self.create_test_files()

    def tearDown(self):
        """清理测试环境"""
        self.temp_dir.cleanup()

    def create_test_files(self):
        """创建各种格式的测试CSV文件"""
        # 1. 使用datetime列的文件
        self.datetime_file = self.test_dir / "datetime_data.csv"
        datetime_data = {
            "datetime": ["2024-01-01 00:00:00", "2024-01-01 01:00:00", "2024-01-01 02:00:00"],
            "open": [100.0, 101.0, 102.0],
            "high": [100.5, 101.5, 102.5],
            "low": [99.5, 100.5, 101.5],
            "close": [100.2, 101.2, 102.2],
            "volume": [1000.0, 1100.0, 1200.0]
        }
        pd.DataFrame(datetime_data).to_csv(self.datetime_file, index=False)

        # 2. 使用timestamp列的文件
        self.timestamp_file = self.test_dir / "timestamp_data.csv"
        timestamp_data = {
            "timestamp": [1704067200000, 1704070800000, 1704074400000],  # 毫秒时间戳
            "open": [200.0, 201.0, 202.0],
            "high": [200.5, 201.5, 202.5],
            "low": [199.5, 200.5, 201.5],
            "close": [200.2, 201.2, 202.2],
            "volume": [2000.0, 2100.0, 2200.0]
        }
        pd.DataFrame(timestamp_data).to_csv(self.timestamp_file, index=False)

        # 3. 没有时间列的文件
        self.no_time_file = self.test_dir / "no_time_data.csv"
        no_time_data = {
            "open": [300.0, 301.0, 302.0],
            "high": [300.5, 301.5, 302.5],
            "low": [299.5, 300.5, 301.5],
            "close": [300.2, 301.2, 302.2],
            "volume": [3000.0, 3100.0, 3200.0]
        }
        pd.DataFrame(no_time_data).to_csv(self.no_time_file, index=False)

        # 4. 空文件
        self.empty_file = self.test_dir / "empty_data.csv"
        self.empty_file.touch()

        # 5. 格式错误的文件
        self.malformed_file = self.test_dir / "malformed_data.csv"
        with open(self.malformed_file, 'w') as f:
            f.write("invalid,csv,content,without,proper,headers\n")
            f.write("some,random,data,here\n")

    def test_load_csv_datetime_column(self):
        """测试加载带datetime列的CSV文件"""
        df = load_csv_with_time_detection(self.datetime_file)

        # 验证数据加载成功
        self.assertFalse(df.empty)
        self.assertEqual(len(df), 3)

        # 验证列存在
        expected_columns = ['datetime', 'open', 'high', 'low', 'close', 'volume']
        for col in expected_columns:
            self.assertIn(col, df.columns)

        # 验证datetime列已转换为datetime类型
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(df['datetime']))

        # 验证数据值
        self.assertEqual(df.loc[0, 'open'], 100.0)
        self.assertEqual(df.loc[1, 'open'], 101.0)

    def test_load_csv_timestamp_column(self):
        """测试加载带timestamp列的CSV文件"""
        df = load_csv_with_time_detection(self.timestamp_file)

        # 验证数据加载成功
        self.assertFalse(df.empty)
        self.assertEqual(len(df), 3)

        # 验证列存在
        expected_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        for col in expected_columns:
            self.assertIn(col, df.columns)

        # 验证timestamp列保持为数值类型（毫秒）
        self.assertTrue(pd.api.types.is_numeric_dtype(df['timestamp']))

        # 验证数据值
        self.assertEqual(df.loc[0, 'timestamp'], 1704067200000)
        self.assertEqual(df.loc[0, 'open'], 200.0)

    def test_load_csv_no_time_column(self):
        """测试加载没有时间列的CSV文件"""
        df = load_csv_with_time_detection(self.no_time_file)

        # 验证数据加载成功
        self.assertFalse(df.empty)
        self.assertEqual(len(df), 3)

        # 验证列存在但没有时间列
        expected_columns = ['open', 'high', 'low', 'close', 'volume']
        for col in expected_columns:
            self.assertIn(col, df.columns)

        # 验证没有时间相关列
        self.assertNotIn('datetime', df.columns)
        self.assertNotIn('timestamp', df.columns)

        # 验证数据值
        self.assertEqual(df.loc[0, 'open'], 300.0)

    def test_load_csv_file_not_found(self):
        """测试文件不存在的情况"""
        nonexistent_file = self.test_dir / "does_not_exist.csv"

        df = load_csv_with_time_detection(nonexistent_file)

        # 应该返回空DataFrame
        self.assertTrue(df.empty)

    def test_load_csv_empty_file(self):
        """测试空文件的情况"""
        df = load_csv_with_time_detection(self.empty_file)

        # 应该返回空DataFrame
        self.assertTrue(df.empty)

    def test_load_csv_malformed_file(self):
        """测试格式错误文件的处理"""
        df = load_csv_with_time_detection(self.malformed_file)

        # 应该能加载但可能没有预期的列结构
        # 主要测试不会崩溃
        self.assertIsInstance(df, pd.DataFrame)

    def test_load_csv_datetime_conversion(self):
        """测试datetime列的转换"""
        # 创建包含不同datetime格式的测试文件
        mixed_datetime_file = self.test_dir / "mixed_datetime.csv"
        mixed_data = {
            "datetime": [
                "2024-01-01 00:00:00",
                "2024-01-01T01:00:00",
                "2024-01-01 02:00:00.000"
            ],
            "open": [100.0, 101.0, 102.0],
            "close": [100.2, 101.2, 102.2]
        }
        pd.DataFrame(mixed_data).to_csv(mixed_datetime_file, index=False)

        df = load_csv_with_time_detection(mixed_datetime_file)

        # 验证datetime列转换成功
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(df['datetime']))
        self.assertFalse(df['datetime'].isnull().any())

    def test_load_csv_timestamp_formats(self):
        """测试不同timestamp格式的处理"""
        # 创建包含不同timestamp格式的测试文件
        mixed_timestamp_file = self.test_dir / "mixed_timestamp.csv"
        mixed_data = {
            "timestamp": [1704067200000, 1704070800000, 1704074400000],  # 毫秒
            "open": [100.0, 101.0, 102.0],
            "close": [100.2, 101.2, 102.2]
        }
        pd.DataFrame(mixed_data).to_csv(mixed_timestamp_file, index=False)

        df = load_csv_with_time_detection(mixed_timestamp_file)

        # 验证timestamp列保持数值类型
        self.assertTrue(pd.api.types.is_numeric_dtype(df['timestamp']))
        self.assertFalse(df['timestamp'].isnull().any())

    def test_load_csv_with_extra_columns(self):
        """测试包含额外列的CSV文件"""
        extra_cols_file = self.test_dir / "extra_columns.csv"
        extra_data = {
            "datetime": ["2024-01-01 00:00:00", "2024-01-01 01:00:00"],
            "open": [100.0, 101.0],
            "high": [100.5, 101.5],
            "low": [99.5, 100.5],
            "close": [100.2, 101.2],
            "volume": [1000.0, 1100.0],
            "extra_col1": ["data1", "data2"],
            "extra_col2": [123, 456]
        }
        pd.DataFrame(extra_data).to_csv(extra_cols_file, index=False)

        df = load_csv_with_time_detection(extra_cols_file)

        # 验证所有列都被保留
        expected_columns = ['datetime', 'open', 'high', 'low', 'close', 'volume', 'extra_col1', 'extra_col2']
        for col in expected_columns:
            self.assertIn(col, df.columns)

    def test_load_csv_case_sensitivity(self):
        """测试时间列名的大小写敏感性"""
        # 创建使用大写时间列名的文件
        uppercase_file = self.test_dir / "uppercase_time.csv"
        uppercase_data = {
            "DATETIME": ["2024-01-01 00:00:00", "2024-01-01 01:00:00"],
            "TIMESTAMP": [1704067200000, 1704070800000],
            "open": [100.0, 101.0],
            "close": [100.2, 101.2]
        }
        pd.DataFrame(uppercase_data).to_csv(uppercase_file, index=False)

        df = load_csv_with_time_detection(uppercase_file)

        # 验证能正确识别大写的时间列
        self.assertIn('DATETIME', df.columns)
        self.assertIn('TIMESTAMP', df.columns)

    def test_load_csv_data_types_preservation(self):
        """测试数据类型保持"""
        df = load_csv_with_time_detection(self.datetime_file)

        # 验证数值列的类型
        numeric_columns = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_columns:
            self.assertTrue(pd.api.types.is_numeric_dtype(df[col]))

    def test_load_csv_index_handling(self):
        """测试索引处理"""
        df = load_csv_with_time_detection(self.datetime_file)

        # 验证索引从0开始
        self.assertEqual(df.index[0], 0)
        self.assertEqual(len(df.index), len(df))


if __name__ == "__main__":
    unittest.main()
