"""
测试数据质量检查模块
"""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from utils.data_management.data_manager import DataQualityChecker, DataManager
from core.exceptions import DataValidationError


class TestDataQualityChecker(unittest.TestCase):
    """测试数据质量检查器"""

    def setUp(self):
        """初始化测试"""
        self.checker = DataQualityChecker(enable_logging=False)
        self.symbol = "BTCUSDT"
        self.timeframe = "1h"

    def test_check_missing_values_no_issues(self):
        """测试无缺失值的数据"""
        df = pd.DataFrame(
            {
                "timestamp": [1000, 2000, 3000],
                "open": [100, 101, 102],
                "high": [105, 106, 107],
                "low": [95, 96, 97],
                "close": [102, 103, 104],
                "volume": [1000, 1100, 1200],
            }
        )
        issues = self.checker.check_missing_values(df, self.symbol)
        self.assertEqual(len(issues), 0)

    def test_check_missing_values_with_nulls(self):
        """测试有缺失值的数据"""
        df = pd.DataFrame(
            {
                "timestamp": [1000, 2000, 3000],
                "open": [100, None, 102],
                "close": [102, 103, None],
                "volume": [1000, 1100, 1200],
            }
        )
        issues = self.checker.check_missing_values(df, self.symbol)
        self.assertEqual(len(issues), 1)
        self.assertIn("缺失值", issues[0])

    def test_check_timestamp_continuity_valid(self):
        """测试连续的时间戳"""
        df = pd.DataFrame(
            {
                "timestamp": [
                    1000000,
                    1000000 + 3600000,  # +1小时
                    1000000 + 7200000,  # +2小时
                    1000000 + 10800000,  # +3小时
                ],
                "close": [100, 101, 102, 103],
            }
        )
        issues = self.checker.check_timestamp_continuity(df, self.symbol, "1h")
        self.assertEqual(len(issues), 0)

    def test_check_timestamp_continuity_with_gaps(self):
        """测试有间隔的时间戳"""
        df = pd.DataFrame(
            {
                "timestamp": [
                    1000000,
                    1000000 + 3600000,  # +1小时
                    1000000 + 10800000,  # +3小时（跳过了2小时）
                ],
                "close": [100, 101, 102],
            }
        )
        issues = self.checker.check_timestamp_continuity(df, self.symbol, "1h")
        self.assertEqual(len(issues), 1)
        self.assertIn("间隔异常", issues[0])

    def test_check_price_outliers_normal(self):
        """测试正常价格波动"""
        df = pd.DataFrame(
            {
                "close": [100, 101, 102, 101, 100, 99, 100, 101, 102, 103],
            }
        )
        issues = self.checker.check_price_outliers(df, self.symbol, sigma=3.0)
        self.assertEqual(len(issues), 0)

    def test_check_price_outliers_with_spike(self):
        """测试价格异常波动"""
        # 创建有明显异常值的数据
        df = pd.DataFrame(
            {
                "close": [100] * 50 + [200] + [100] * 49,  # 中间有一个2倍的异常值
            }
        )
        issues = self.checker.check_price_outliers(df, self.symbol, sigma=3.0)
        self.assertEqual(len(issues), 1)
        self.assertIn("异常值", issues[0])

    def test_check_volume_anomalies_normal(self):
        """测试正常成交量"""
        df = pd.DataFrame(
            {
                "volume": [1000, 1100, 1200, 1300, 1400],
            }
        )
        issues = self.checker.check_volume_anomalies(df, self.symbol)
        self.assertEqual(len(issues), 0)

    def test_check_volume_anomalies_with_zeros(self):
        """测试零成交量"""
        df = pd.DataFrame(
            {
                "volume": [1000, 0, 0, 0, 0, 0, 0, 1000, 1000, 1000],  # 60%零成交量
            }
        )
        issues = self.checker.check_volume_anomalies(df, self.symbol, zero_threshold=0.05)
        self.assertEqual(len(issues), 1)
        self.assertIn("零成交量", issues[0])

    def test_check_data_completeness_full(self):
        """测试完整数据"""
        # 创建24小时的1小时数据（24个数据点）
        start_ms = 1609459200000  # 2021-01-01 00:00:00
        timestamps = [start_ms + i * 3600000 for i in range(24)]
        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "close": [100] * 24,
            }
        )
        issues = self.checker.check_data_completeness(
            df, self.symbol, "2021-01-01", "2021-01-02", "1h"
        )
        self.assertEqual(len(issues), 0)

    def test_check_data_completeness_incomplete(self):
        """测试不完整数据"""
        # 创建24小时的1小时数据，但只有10个数据点（<95%）
        start_ms = 1609459200000  # 2021-01-01 00:00:00
        timestamps = [start_ms + i * 3600000 for i in range(10)]
        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "close": [100] * 10,
            }
        )
        issues = self.checker.check_data_completeness(
            df, self.symbol, "2021-01-01", "2021-01-02", "1h"
        )
        self.assertEqual(len(issues), 1)
        self.assertIn("完整性不足", issues[0])

    def test_validate_data_quality_all_pass(self):
        """测试综合质量检查 - 全部通过"""
        start_ms = 1609459200000
        timestamps = [start_ms + i * 3600000 for i in range(24)]
        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": [100 + i * 0.5 for i in range(24)],
                "high": [105 + i * 0.5 for i in range(24)],
                "low": [95 + i * 0.5 for i in range(24)],
                "close": [102 + i * 0.5 for i in range(24)],
                "volume": [1000 + i * 10 for i in range(24)],
            }
        )
        is_valid, issues = self.checker.validate_data_quality(
            df, self.symbol, "1h", "2021-01-01", "2021-01-02"
        )
        self.assertTrue(is_valid)
        self.assertEqual(len(issues), 0)

    def test_validate_data_quality_with_issues(self):
        """测试综合质量检查 - 有问题"""
        df = pd.DataFrame(
            {
                "timestamp": [1000, 2000],
                "open": [100, None],  # 有缺失值
                "close": [102, 103],
                "volume": [0, 0],  # 全是零成交量
            }
        )
        is_valid, issues = self.checker.validate_data_quality(df, self.symbol, "1h")
        self.assertFalse(is_valid)
        self.assertGreater(len(issues), 0)

    def test_validate_data_quality_raise_on_error(self):
        """测试综合质量检查 - 抛出异常"""
        df = pd.DataFrame(
            {
                "timestamp": [1000, 2000],
                "open": [100, None],
                "close": [102, 103],
            }
        )
        with self.assertRaises(DataValidationError):
            self.checker.validate_data_quality(df, self.symbol, "1h", raise_on_error=True)


class TestDataManager(unittest.TestCase):
    """测试数据管理器"""

    def setUp(self):
        """初始化测试"""
        self.temp_dir = tempfile.mkdtemp()
        self.base_dir = Path(self.temp_dir)
        self.manager = DataManager(self.base_dir, enable_quality_check=True)

    def tearDown(self):
        """清理临时文件"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization_with_quality_check(self):
        """测试初始化（启用质量检查）"""
        self.assertTrue(self.manager.enable_quality_check)
        self.assertIsNotNone(self.manager.quality_checker)

    def test_initialization_without_quality_check(self):
        """测试初始化（禁用质量检查）"""
        manager = DataManager(self.base_dir, enable_quality_check=False)
        self.assertFalse(manager.enable_quality_check)
        self.assertIsNone(manager.quality_checker)

    def test_validate_data_file_not_exists(self):
        """测试验证不存在的文件"""
        file_path = self.base_dir / "nonexistent.csv"
        is_valid, issues = self.manager.validate_data_file(file_path, "BTCUSDT", "1h")
        self.assertFalse(is_valid)
        self.assertIn("不存在", issues[0])

    def test_validate_data_file_valid(self):
        """测试验证有效数据文件"""
        # 创建测试数据文件
        data_dir = self.base_dir / "data" / "raw" / "BTCUSDT"
        data_dir.mkdir(parents=True, exist_ok=True)
        file_path = data_dir / "test.csv"

        start_ms = 1609459200000
        timestamps = [start_ms + i * 3600000 for i in range(24)]
        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": [100 + i * 0.5 for i in range(24)],
                "high": [105 + i * 0.5 for i in range(24)],
                "low": [95 + i * 0.5 for i in range(24)],
                "close": [102 + i * 0.5 for i in range(24)],
                "volume": [1000 + i * 10 for i in range(24)],
            }
        )
        df.to_csv(file_path, index=False)

        is_valid, issues = self.manager.validate_data_file(
            file_path, "BTCUSDT", "1h", "2021-01-01", "2021-01-02"
        )
        self.assertTrue(is_valid)
        self.assertEqual(len(issues), 0)

    def test_validate_data_file_invalid(self):
        """测试验证无效数据文件"""
        # 创建有问题的测试数据文件
        data_dir = self.base_dir / "data" / "raw" / "BTCUSDT"
        data_dir.mkdir(parents=True, exist_ok=True)
        file_path = data_dir / "test.csv"

        df = pd.DataFrame(
            {
                "timestamp": [1000, 2000],
                "open": [100, None],  # 有缺失值
                "close": [102, 103],
            }
        )
        df.to_csv(file_path, index=False)

        is_valid, issues = self.manager.validate_data_file(file_path, "BTCUSDT", "1h")
        self.assertFalse(is_valid)
        self.assertGreater(len(issues), 0)

    def test_batch_validate_data(self):
        """测试批量验证数据"""
        # 创建测试数据
        data_dir = self.base_dir / "data" / "raw"

        # 创建有效数据文件
        btc_dir = data_dir / "BTCUSDT"
        btc_dir.mkdir(parents=True, exist_ok=True)
        btc_file = btc_dir / "binance-BTCUSDT-1h-2021-01-01_2021-01-02.csv"

        start_ms = 1609459200000
        timestamps = [start_ms + i * 3600000 for i in range(24)]
        df_valid = pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": [100 + i * 0.5 for i in range(24)],
                "high": [105 + i * 0.5 for i in range(24)],
                "low": [95 + i * 0.5 for i in range(24)],
                "close": [102 + i * 0.5 for i in range(24)],
                "volume": [1000 + i * 10 for i in range(24)],
            }
        )
        df_valid.to_csv(btc_file, index=False)

        # 创建无效数据文件
        eth_dir = data_dir / "ETHUSDT"
        eth_dir.mkdir(parents=True, exist_ok=True)
        eth_file = eth_dir / "binance-ETHUSDT-1h-2021-01-01_2021-01-02.csv"

        df_invalid = pd.DataFrame(
            {
                "timestamp": [1000, 2000],
                "open": [100, None],
                "close": [102, 103],
            }
        )
        df_invalid.to_csv(eth_file, index=False)

        # 批量验证
        result = self.manager.batch_validate_data(
            ["BTCUSDT", "ETHUSDT"], "2021-01-01", "2021-01-02", "1h", "binance"
        )

        self.assertIn("BTCUSDT", result["passed"])
        self.assertIn("ETHUSDT", result["failed"])
        self.assertGreater(len(result["failed"]["ETHUSDT"]), 0)


if __name__ == "__main__":
    unittest.main()
