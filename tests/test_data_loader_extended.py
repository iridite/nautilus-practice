"""
测试 data_loader 模块的额外功能
"""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from utils.data_management.data_loader import (
    DataLoadError,
    TimeColumnError,
    detect_time_column,
    _validate_time_column,
    _looks_like_time_column,
    _filter_by_date_range,
)


class TestDetectTimeColumnExtended(unittest.TestCase):
    """测试时间列检测功能（扩展）"""

    def setUp(self):
        """创建临时测试文件"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

    def tearDown(self):
        """清理临时文件"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_detect_timestamp_column(self):
        """测试检测 timestamp 列"""
        csv_file = self.temp_path / "data.csv"
        csv_file.write_text(
            "timestamp,open,high,low,close,volume\n"
            "2025-01-01 00:00:00,100,110,90,105,1000\n"
            "2025-01-02 00:00:00,105,115,95,110,1100\n"
        )

        time_col = detect_time_column(csv_file)
        self.assertEqual(time_col, "timestamp")

    def test_detect_datetime_column(self):
        """测试检测 datetime 列"""
        csv_file = self.temp_path / "data.csv"
        csv_file.write_text(
            "datetime,open,high,low,close,volume\n"
            "2025-01-01 00:00:00,100,110,90,105,1000\n"
            "2025-01-02 00:00:00,105,115,95,110,1100\n"
        )

        time_col = detect_time_column(csv_file)
        self.assertEqual(time_col, "datetime")

    def test_detect_time_column_priority(self):
        """测试时间列优先级（timestamp > datetime）"""
        csv_file = self.temp_path / "data.csv"
        csv_file.write_text(
            "timestamp,datetime,open,high,low,close,volume\n"
            "2025-01-01 00:00:00,2025-01-01,100,110,90,105,1000\n"
        )

        time_col = detect_time_column(csv_file)
        self.assertEqual(time_col, "timestamp")

    def test_detect_numeric_timestamp(self):
        """测试检测数值型时间戳"""
        csv_file = self.temp_path / "data.csv"
        csv_file.write_text(
            "timestamp,open,high,low,close,volume\n"
            "1640995200000,100,110,90,105,1000\n"
            "1641081600000,105,115,95,110,1100\n"
        )

        time_col = detect_time_column(csv_file)
        self.assertEqual(time_col, "timestamp")

    def test_detect_no_time_column(self):
        """测试没有时间列的情况"""
        csv_file = self.temp_path / "data.csv"
        csv_file.write_text("open,high,low,close,volume\n100,110,90,105,1000\n")

        with self.assertRaises(TimeColumnError) as ctx:
            detect_time_column(csv_file)
        self.assertIn("No valid time column found", str(ctx.exception))

    def test_detect_empty_csv(self):
        """测试空 CSV 文件"""
        csv_file = self.temp_path / "empty.csv"
        csv_file.write_text("")

        with self.assertRaises(TimeColumnError) as ctx:
            detect_time_column(csv_file)
        self.assertIn("empty", str(ctx.exception).lower())

    def test_detect_alternative_time_column(self):
        """测试检测其他时间列名（time, date）"""
        csv_file = self.temp_path / "data.csv"
        csv_file.write_text(
            "time,open,high,low,close,volume\n2025-01-01 00:00:00,100,110,90,105,1000\n"
        )

        time_col = detect_time_column(csv_file)
        self.assertEqual(time_col, "time")


class TestValidateTimeColumnExtended(unittest.TestCase):
    """测试时间列验证功能（扩展）"""

    def test_validate_datetime_string(self):
        """测试验证日期字符串"""
        series = pd.Series(["2025-01-01", "2025-01-02", "2025-01-03"])
        self.assertTrue(_validate_time_column(series))

    def test_validate_numeric_timestamp(self):
        """测试验证数值时间戳"""
        series = pd.Series([1640995200000.0, 1641081600000.0, 1641168000000.0])
        self.assertTrue(_validate_time_column(series))

    def test_validate_empty_series(self):
        """测试验证空序列"""
        series = pd.Series([])
        self.assertFalse(_validate_time_column(series))

    def test_validate_all_nan(self):
        """测试验证全 NaN 序列"""
        series = pd.Series([None, None, None])
        self.assertFalse(_validate_time_column(series))

    def test_validate_invalid_format(self):
        """测试验证无效格式"""
        series = pd.Series(["not", "a", "date"])
        self.assertFalse(_validate_time_column(series))

    def test_validate_with_nan(self):
        """测试验证包含 NaN 的序列"""
        series = pd.Series([None, "2025-01-01", "2025-01-02"])
        self.assertTrue(_validate_time_column(series))


class TestLooksLikeTimeColumnExtended(unittest.TestCase):
    """测试时间列名称检测（扩展）"""

    def test_looks_like_time_column_timestamp(self):
        """测试包含 timestamp 的列名"""
        series = pd.Series([1, 2, 3], name="timestamp")
        self.assertTrue(_looks_like_time_column(series))

    def test_looks_like_time_column_datetime(self):
        """测试包含 datetime 的列名"""
        series = pd.Series([1, 2, 3], name="datetime")
        self.assertTrue(_looks_like_time_column(series))

    def test_looks_like_time_column_date(self):
        """测试包含 date 的列名"""
        series = pd.Series([1, 2, 3], name="trade_date")
        self.assertTrue(_looks_like_time_column(series))

    def test_looks_like_time_column_time(self):
        """测试包含 time 的列名"""
        series = pd.Series([1, 2, 3], name="time")
        self.assertTrue(_looks_like_time_column(series))

    def test_not_looks_like_time_column(self):
        """测试不像时间列的列名"""
        series = pd.Series([1, 2, 3], name="price")
        self.assertFalse(_looks_like_time_column(series))

    def test_looks_like_time_column_empty(self):
        """测试空序列"""
        series = pd.Series([], name="timestamp")
        self.assertFalse(_looks_like_time_column(series))

    def test_looks_like_time_column_no_name(self):
        """测试没有列名的序列"""
        series = pd.Series([1, 2, 3])
        self.assertFalse(_looks_like_time_column(series))


class TestFilterByDateRangeExtended(unittest.TestCase):
    """测试日期范围过滤（扩展）"""

    def setUp(self):
        """创建测试数据"""
        dates = pd.date_range("2025-01-01", "2025-01-10", freq="D")
        self.df = pd.DataFrame({"value": range(10)}, index=dates)

    def test_filter_with_start_date(self):
        """测试使用开始日期过滤"""
        filtered = _filter_by_date_range(self.df, "2025-01-05", None)
        self.assertEqual(len(filtered), 6)  # 01-05 到 01-10
        self.assertEqual(filtered.index[0].date().isoformat(), "2025-01-05")

    def test_filter_with_end_date(self):
        """测试使用结束日期过滤"""
        filtered = _filter_by_date_range(self.df, None, "2025-01-05")
        self.assertEqual(len(filtered), 5)  # 01-01 到 01-05
        self.assertEqual(filtered.index[-1].date().isoformat(), "2025-01-05")

    def test_filter_with_both_dates(self):
        """测试使用开始和结束日期过滤"""
        filtered = _filter_by_date_range(self.df, "2025-01-03", "2025-01-07")
        self.assertEqual(len(filtered), 5)  # 01-03 到 01-07
        self.assertEqual(filtered.index[0].date().isoformat(), "2025-01-03")
        self.assertEqual(filtered.index[-1].date().isoformat(), "2025-01-07")

    def test_filter_with_no_dates(self):
        """测试不使用日期过滤"""
        filtered = _filter_by_date_range(self.df, None, None)
        self.assertEqual(len(filtered), 10)  # 全部数据

    def test_filter_outside_range(self):
        """测试过滤范围外的数据"""
        filtered = _filter_by_date_range(self.df, "2025-01-15", "2025-01-20")
        self.assertEqual(len(filtered), 0)  # 没有数据


if __name__ == "__main__":
    unittest.main()
