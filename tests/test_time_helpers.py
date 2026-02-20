"""
时间处理工具模块单元测试

测试内容：
1. get_ms_timestamp() - 日期字符串转毫秒时间戳
2. get_ns_timestamp() - 日期字符串转纳秒时间戳
3. format_timestamp() - 时间戳格式化
4. parse_date_to_timestamp() - 解析日期为 pandas Timestamp
5. parse_datetime_range() - 解析日期范围
6. validate_date_string() - 验证日期字符串格式
7. normalize_timestamp_to_utc() - 标准化时间戳为UTC

Usage:
    uv run pytest tests/test_time_helpers.py -v
"""

import unittest
from datetime import datetime, timezone
import pandas as pd
import pytest

from utils.time_helpers import (
    get_ms_timestamp,
    get_ns_timestamp,
    format_timestamp,
    parse_date_to_timestamp,
    parse_datetime_range,
    validate_date_string,
    normalize_timestamp_to_utc,
)


class TestGetMsTimestamp(unittest.TestCase):
    """测试 get_ms_timestamp 函数"""

    def test_basic_conversion(self):
        """测试基本的日期字符串转换"""
        result = get_ms_timestamp("2024-01-01")
        expected = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        self.assertEqual(result, expected)
        self.assertEqual(result, 1704067200000)

    def test_edge_cases(self):
        """测试边界情况"""
        # 闰年
        result = get_ms_timestamp("2024-02-29")
        expected = int(datetime(2024, 2, 29, tzinfo=timezone.utc).timestamp() * 1000)
        self.assertEqual(result, expected)

    def test_timezone_handling(self):
        """测试时区处理 - 应始终返回UTC时间戳"""
        result = get_ms_timestamp("2024-06-15")
        expected_utc = datetime(2024, 6, 15, 0, 0, 0, tzinfo=timezone.utc)
        expected_ms = int(expected_utc.timestamp() * 1000)
        self.assertEqual(result, expected_ms)

    def test_invalid_format(self):
        """测试无效日期格式"""
        with self.assertRaises(ValueError):
            get_ms_timestamp("2024/01/01")
        with self.assertRaises(ValueError):
            get_ms_timestamp("01-01-2024")
        with self.assertRaises(ValueError):
            get_ms_timestamp("2024-13-01")

    def test_consistency(self):
        """测试函数一致性"""
        date_str = "2024-05-15"
        result1 = get_ms_timestamp(date_str)
        result2 = get_ms_timestamp(date_str)
        self.assertEqual(result1, result2)

    def test_order(self):
        """测试时间戳顺序"""
        earlier = get_ms_timestamp("2024-01-01")
        later = get_ms_timestamp("2024-12-31")
        self.assertLess(earlier, later)

        # 连续日期
        day1 = get_ms_timestamp("2024-06-15")
        day2 = get_ms_timestamp("2024-06-16")
        self.assertEqual(day2 - day1, 86400000)  # 一天的毫秒数


class TestGetNsTimestamp(unittest.TestCase):
    """测试 get_ns_timestamp 函数"""

    def test_basic_conversion(self):
        """测试基本转换"""
        result = get_ns_timestamp("2024-01-01")
        self.assertIsInstance(result, int)
        self.assertEqual(result, 1704067200000000000)

    def test_ms_to_ns_ratio(self):
        """测试毫秒到纳秒的转换比例"""
        ms_result = get_ms_timestamp("2024-01-01")
        ns_result = get_ns_timestamp("2024-01-01")
        self.assertEqual(ns_result, ms_result * 1_000_000)


class TestFormatTimestamp(unittest.TestCase):
    """测试 format_timestamp 函数"""

    def test_format_ms_timestamp(self):
        """测试格式化毫秒时间戳"""
        timestamp = 1704067200000  # 2024-01-01 00:00:00 UTC
        result = format_timestamp(timestamp)
        self.assertIn("2024-01-01", result)
        self.assertIn("00:00:00", result)

    def test_format_ns_timestamp(self):
        """测试格式化纳秒时间戳"""
        timestamp = 1704067200000000000
        result = format_timestamp(timestamp, is_ms=False)
        self.assertIn("2024-01-01", result)
        self.assertIn("00:00:00", result)

    def test_custom_format(self):
        """测试自定义格式"""
        timestamp = 1704067200000
        result = format_timestamp(timestamp, format_str="%Y/%m/%d")
        self.assertEqual(result, "2024/01/01")

    def test_format_with_time(self):
        """测试包含时间的格式化"""
        timestamp = 1704112245000  # 2024-01-01 12:30:45 UTC
        result = format_timestamp(timestamp, format_str="%Y-%m-%d %H:%M:%S")
        self.assertIn("2024-01-01 12:30:45", result)


class TestParseDateToTimestamp(unittest.TestCase):
    """测试 parse_date_to_timestamp 函数"""

    def test_parse_date(self):
        """测试解析日期"""
        result = parse_date_to_timestamp("2024-01-01")
        self.assertIsInstance(result, pd.Timestamp)
        self.assertIsNone(result.tz)  # 默认移除时区

    def test_parse_date_tz_aware(self):
        """测试解析带时区的日期"""
        result = parse_date_to_timestamp("2024-01-01", tz_aware=True)
        self.assertIsInstance(result, pd.Timestamp)

    def test_parse_date_removes_tz(self):
        """测试默认移除时区"""
        result = parse_date_to_timestamp("2024-01-01", tz_aware=False)
        self.assertIsNone(result.tz)


class TestParseDatetimeRange(unittest.TestCase):
    """测试 parse_datetime_range 函数"""

    def test_valid_range(self):
        """测试有效日期范围"""
        start, end = parse_datetime_range("2024-01-01", "2024-01-31")
        self.assertIsInstance(start, pd.Timestamp)
        self.assertIsInstance(end, pd.Timestamp)
        self.assertLess(start, end)
        self.assertIsNotNone(start.tz)  # 应该有UTC时区
        self.assertIsNotNone(end.tz)

    def test_invalid_range(self):
        """测试无效日期范围"""
        with self.assertRaises(ValueError) as context:
            parse_datetime_range("2024-01-31", "2024-01-01")
        self.assertIn("cannot be later than", str(context.exception))

    def test_same_date_range(self):
        """测试相同日期范围"""
        start, end = parse_datetime_range("2024-01-01", "2024-01-01")
        self.assertEqual(start, end)


class TestValidateDateString(unittest.TestCase):
    """测试 validate_date_string 函数"""

    def test_valid_date(self):
        """测试有效日期字符串"""
        self.assertTrue(validate_date_string("2024-01-01"))
        self.assertTrue(validate_date_string("2024-12-31"))

    def test_invalid_date(self):
        """测试无效日期字符串"""
        self.assertFalse(validate_date_string("01/01/2024"))
        self.assertFalse(validate_date_string("2024-13-01"))
        self.assertFalse(validate_date_string("invalid"))
        self.assertFalse(validate_date_string(""))

    def test_custom_format(self):
        """测试自定义日期格式"""
        self.assertTrue(validate_date_string("01/01/2024", date_format="%m/%d/%Y"))
        self.assertFalse(validate_date_string("2024-01-01", date_format="%m/%d/%Y"))

    def test_edge_cases(self):
        """测试边界情况"""
        self.assertFalse(validate_date_string("2024-02-30"))  # 2月没有30号
        self.assertTrue(validate_date_string("2024-02-29"))  # 闰年2月29号


class TestNormalizeTimestampToUtc(unittest.TestCase):
    """测试 normalize_timestamp_to_utc 函数"""

    def test_normalize_ms_timestamp(self):
        """测试标准化毫秒时间戳"""
        timestamp = 1704067200000
        result = normalize_timestamp_to_utc(timestamp, is_ms=True)
        self.assertIsInstance(result, int)
        self.assertEqual(result, timestamp)

    def test_normalize_ns_timestamp(self):
        """测试标准化纳秒时间戳"""
        timestamp = 1704067200000000000
        result = normalize_timestamp_to_utc(timestamp, is_ms=False)
        self.assertIsInstance(result, int)
        self.assertEqual(result, timestamp)

    def test_normalize_preserves_format(self):
        """测试标准化保持原格式"""
        ms_timestamp = 1704067200000
        ns_timestamp = 1704067200000000000

        ms_result = normalize_timestamp_to_utc(ms_timestamp, is_ms=True)
        ns_result = normalize_timestamp_to_utc(ns_timestamp, is_ms=False)

        # 毫秒和纳秒的比例应该是 1:1000000
        self.assertEqual(ns_result, ms_result * 1_000_000)


if __name__ == "__main__":
    unittest.main()
