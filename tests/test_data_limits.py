"""
测试数据限制检查模块
"""

import unittest
from datetime import datetime, timedelta

from utils.data_management.data_limits import (
    EXCHANGE_DATA_LIMITS,
    check_data_availability,
    get_recommended_date_range,
    validate_strategy_data_requirements,
)


class TestDataLimits(unittest.TestCase):
    """测试数据限制检查功能"""

    def test_exchange_data_limits_structure(self):
        """测试交易所数据限制配置结构"""
        self.assertIn("binance", EXCHANGE_DATA_LIMITS)
        self.assertIn("okx", EXCHANGE_DATA_LIMITS)

        for exchange in ["binance", "okx"]:
            self.assertIn("oi", EXCHANGE_DATA_LIMITS[exchange])
            self.assertIn("funding", EXCHANGE_DATA_LIMITS[exchange])
            self.assertIn("ohlcv", EXCHANGE_DATA_LIMITS[exchange])

    def test_check_data_availability_valid_range(self):
        """测试有效的数据范围"""
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

        is_available, warning = check_data_availability(start_date, end_date, "binance", "oi")

        self.assertTrue(is_available)
        self.assertIsNone(warning)

    def test_check_data_availability_exceeds_range(self):
        """测试超过数据范围限制"""
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        is_available, warning = check_data_availability(start_date, end_date, "binance", "oi")

        self.assertFalse(is_available)
        self.assertIsNotNone(warning)
        self.assertIn("超过", warning)

    def test_check_data_availability_old_data(self):
        """测试过旧的数据"""
        end_date = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=110)).strftime("%Y-%m-%d")

        is_available, warning = check_data_availability(start_date, end_date, "binance", "oi")

        self.assertFalse(is_available)
        self.assertIsNotNone(warning)
        self.assertIn("距今", warning)

    def test_check_data_availability_unknown_exchange(self):
        """测试未知交易所"""
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

        is_available, warning = check_data_availability(
            start_date, end_date, "unknown_exchange", "oi"
        )

        self.assertTrue(is_available)
        self.assertIsNotNone(warning)
        self.assertIn("未知交易所", warning)

    def test_check_data_availability_unknown_data_type(self):
        """测试未知数据类型"""
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

        is_available, warning = check_data_availability(
            start_date, end_date, "binance", "unknown_type"
        )

        self.assertTrue(is_available)
        self.assertIsNotNone(warning)
        self.assertIn("未知数据类型", warning)

    def test_check_data_availability_invalid_date_format(self):
        """测试无效的日期格式"""
        is_available, warning = check_data_availability(
            "invalid-date", "2024-01-01", "binance", "oi"
        )

        self.assertFalse(is_available)
        self.assertIsNotNone(warning)
        self.assertIn("日期格式错误", warning)

    def test_check_data_availability_case_insensitive(self):
        """测试大小写不敏感"""
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

        is_available1, _ = check_data_availability(start_date, end_date, "BINANCE", "OI")
        is_available2, _ = check_data_availability(start_date, end_date, "binance", "oi")

        self.assertEqual(is_available1, is_available2)

    def test_get_recommended_date_range_default(self):
        """测试获取推荐日期范围（默认）"""
        start_date, end_date = get_recommended_date_range("binance", "oi")

        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        days_diff = (end_dt - start_dt).days
        max_days = EXCHANGE_DATA_LIMITS["binance"]["oi"]

        self.assertEqual(days_diff, max_days)

    def test_get_recommended_date_range_custom_days(self):
        """测试获取推荐日期范围（自定义天数）"""
        custom_days = 10
        start_date, end_date = get_recommended_date_range("binance", "oi", days=custom_days)

        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        days_diff = (end_dt - start_dt).days

        self.assertEqual(days_diff, custom_days)

    def test_get_recommended_date_range_exceeds_limit(self):
        """测试获取推荐日期范围（超过限制）"""
        excessive_days = 1000
        start_date, end_date = get_recommended_date_range("binance", "oi", days=excessive_days)

        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        days_diff = (end_dt - start_dt).days
        max_days = EXCHANGE_DATA_LIMITS["binance"]["oi"]

        # 应该被限制在最大天数
        self.assertEqual(days_diff, max_days)

    def test_get_recommended_date_range_unknown_exchange(self):
        """测试未知交易所的推荐日期范围"""
        start_date, end_date = get_recommended_date_range("unknown_exchange", "oi")

        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        days_diff = (end_dt - start_dt).days

        # 应该使用默认值 30 天
        self.assertEqual(days_diff, 30)

    def test_validate_strategy_data_requirements_all_valid(self):
        """测试验证策略数据需求（全部有效）"""
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

        results = validate_strategy_data_requirements(
            start_date, end_date, "binance", ["oi", "funding"]
        )

        self.assertEqual(len(results), 2)
        self.assertIn("oi", results)
        self.assertIn("funding", results)

        for data_type, (is_available, warning) in results.items():
            self.assertTrue(is_available)
            self.assertIsNone(warning)

    def test_validate_strategy_data_requirements_some_invalid(self):
        """测试验证策略数据需求（部分无效）"""
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        results = validate_strategy_data_requirements(
            start_date, end_date, "binance", ["oi", "ohlcv"]
        )

        self.assertEqual(len(results), 2)

        # OI 应该无效（超过 21 天）
        oi_available, oi_warning = results["oi"]
        self.assertFalse(oi_available)
        self.assertIsNotNone(oi_warning)

        # OHLCV 应该有效（限制 3 年）
        ohlcv_available, ohlcv_warning = results["ohlcv"]
        self.assertTrue(ohlcv_available)
        self.assertIsNone(ohlcv_warning)

    def test_validate_strategy_data_requirements_empty_list(self):
        """测试验证策略数据需求（空列表）"""
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

        results = validate_strategy_data_requirements(start_date, end_date, "binance", [])

        self.assertEqual(len(results), 0)

    def test_okx_vs_binance_limits(self):
        """测试 OKX 和 Binance 的限制差异"""
        # OKX 的 OI 限制应该比 Binance 更宽松
        okx_oi_limit = EXCHANGE_DATA_LIMITS["okx"]["oi"]
        binance_oi_limit = EXCHANGE_DATA_LIMITS["binance"]["oi"]

        self.assertGreater(okx_oi_limit, binance_oi_limit)


if __name__ == "__main__":
    unittest.main()
