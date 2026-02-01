"""
时间处理工具模块单元测试

测试内容：
1. get_ms_timestamp() - 日期字符串转毫秒时间戳
2. 时区处理验证
3. 边界情况和错误处理

Usage:
    uv run python -m unittest tests.test_time_helpers -v
"""

import unittest
from datetime import datetime, timezone

from utils.time_helpers import get_ms_timestamp


class TestTimeHelpers(unittest.TestCase):
    """时间处理工具测试类"""

    def test_get_ms_timestamp_basic(self):
        """测试基本的日期字符串转换"""
        # 测试标准日期格式
        result = get_ms_timestamp("2024-01-01")
        expected = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        self.assertEqual(result, expected)

        # 测试其他日期
        result = get_ms_timestamp("2023-12-31")
        expected = int(datetime(2023, 12, 31, tzinfo=timezone.utc).timestamp() * 1000)
        self.assertEqual(result, expected)

    def test_get_ms_timestamp_edge_cases(self):
        """测试边界情况"""
        # 测试闰年
        result = get_ms_timestamp("2024-02-29")
        expected = int(datetime(2024, 2, 29, tzinfo=timezone.utc).timestamp() * 1000)
        self.assertEqual(result, expected)

        # 测试年初年末
        result = get_ms_timestamp("2024-01-01")
        self.assertIsInstance(result, int)
        self.assertGreater(result, 0)

        result = get_ms_timestamp("2024-12-31")
        self.assertIsInstance(result, int)
        self.assertGreater(result, 0)

    def test_get_ms_timestamp_timezone_handling(self):
        """测试时区处理 - 应始终返回UTC时间戳"""
        result = get_ms_timestamp("2024-06-15")

        # 验证返回的是UTC午夜时间戳
        expected_utc = datetime(2024, 6, 15, 0, 0, 0, tzinfo=timezone.utc)
        expected_ms = int(expected_utc.timestamp() * 1000)

        self.assertEqual(result, expected_ms)

    def test_get_ms_timestamp_invalid_format(self):
        """测试无效日期格式"""
        with self.assertRaises(ValueError):
            get_ms_timestamp("2024/01/01")  # 错误的分隔符

        with self.assertRaises(ValueError):
            get_ms_timestamp("01-01-2024")  # 错误的顺序

        with self.assertRaises(ValueError):
            get_ms_timestamp("2024-13-01")  # 无效的月份

        with self.assertRaises(ValueError):
            get_ms_timestamp("invalid-date")  # 完全无效的格式

    def test_get_ms_timestamp_consistency(self):
        """测试函数一致性 - 同样的输入应产生同样的输出"""
        date_str = "2024-05-15"
        result1 = get_ms_timestamp(date_str)
        result2 = get_ms_timestamp(date_str)

        self.assertEqual(result1, result2)

    def test_get_ms_timestamp_order(self):
        """测试时间戳顺序 - 后面的日期应有更大的时间戳"""
        earlier = get_ms_timestamp("2024-01-01")
        later = get_ms_timestamp("2024-12-31")

        self.assertLess(earlier, later)

        # 测试连续日期
        day1 = get_ms_timestamp("2024-06-15")
        day2 = get_ms_timestamp("2024-06-16")

        self.assertLess(day1, day2)
        # 一天的毫秒数应该是 24 * 60 * 60 * 1000 = 86,400,000
        self.assertEqual(day2 - day1, 86400000)


if __name__ == "__main__":
    unittest.main()