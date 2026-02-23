"""
测试 data_validator 模块
"""

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from utils.data_management.data_validator import (
    DataValidator,
    validate_multi_instrument_alignment,
)


class TestDataValidator(unittest.TestCase):
    """测试数据验证器"""

    def setUp(self):
        """初始化测试"""
        self.validator = DataValidator(spike_threshold=0.5, enable_logging=False)

    def test_validate_oi_valid(self):
        """测试有效的 OI 数据"""
        is_valid, error = self.validator.validate_oi(Decimal("1000000"))
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_validate_oi_none(self):
        """测试 None OI 数据"""
        is_valid, error = self.validator.validate_oi(None)
        self.assertFalse(is_valid)
        self.assertIn("Invalid OI data", error)

    def test_validate_oi_zero(self):
        """测试零值 OI 数据"""
        is_valid, error = self.validator.validate_oi(Decimal("0"))
        self.assertFalse(is_valid)
        self.assertIn("Invalid OI data", error)

    def test_validate_oi_negative(self):
        """测试负值 OI 数据"""
        is_valid, error = self.validator.validate_oi(Decimal("-100"))
        self.assertFalse(is_valid)
        self.assertIn("Invalid OI data", error)

    def test_validate_oi_spike_detection(self):
        """测试 OI 突变检测"""
        # 第一个值正常
        is_valid, _ = self.validator.validate_oi(Decimal("1000000"))
        self.assertTrue(is_valid)

        # 第二个值突变超过 50%
        is_valid, error = self.validator.validate_oi(Decimal("2000000"))
        self.assertFalse(is_valid)
        self.assertIn("spike detected", error)

    def test_validate_oi_gradual_change(self):
        """测试 OI 渐进变化（不触发突变）"""
        # 第一个值
        is_valid, _ = self.validator.validate_oi(Decimal("1000000"))
        self.assertTrue(is_valid)

        # 第二个值变化 30%（小于阈值 50%）
        is_valid, error = self.validator.validate_oi(Decimal("1300000"))
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_validate_funding_rate_valid(self):
        """测试有效的资金费率"""
        is_valid, error = self.validator.validate_funding_rate(Decimal("10.5"))
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_validate_funding_rate_none(self):
        """测试 None 资金费率"""
        is_valid, error = self.validator.validate_funding_rate(None)
        self.assertFalse(is_valid)
        self.assertIn("Invalid Funding Rate", error)

    def test_validate_funding_rate_abnormal(self):
        """测试异常资金费率（超出范围）"""
        is_valid, error = self.validator.validate_funding_rate(Decimal("600"), max_abs_value=500.0)
        self.assertFalse(is_valid)
        self.assertIn("Abnormal Funding Rate", error)

    def test_validate_funding_rate_spike(self):
        """测试资金费率突变"""
        # 第一个值
        is_valid, _ = self.validator.validate_funding_rate(Decimal("10"))
        self.assertTrue(is_valid)

        # 第二个值突变超过 200%
        is_valid, error = self.validator.validate_funding_rate(
            Decimal("250"), spike_threshold=200.0
        )
        self.assertFalse(is_valid)
        self.assertIn("spike detected", error)

    def test_validate_funding_rate_negative(self):
        """测试负资金费率（合法）"""
        is_valid, error = self.validator.validate_funding_rate(Decimal("-15.5"))
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_validate_price_valid(self):
        """测试有效价格"""
        is_valid, error = self.validator.validate_price(Decimal("50000"))
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_validate_price_none(self):
        """测试 None 价格"""
        is_valid, error = self.validator.validate_price(None)
        self.assertFalse(is_valid)
        self.assertIn("Invalid price", error)

    def test_validate_price_zero(self):
        """测试零价格"""
        is_valid, error = self.validator.validate_price(Decimal("0"))
        self.assertFalse(is_valid)
        self.assertIn("Invalid price", error)

    def test_validate_price_below_minimum(self):
        """测试价格低于最小值"""
        is_valid, error = self.validator.validate_price(Decimal("100"), min_price=Decimal("1000"))
        self.assertFalse(is_valid)
        self.assertIn("below minimum", error)

    def test_validate_price_above_maximum(self):
        """测试价格高于最大值"""
        is_valid, error = self.validator.validate_price(
            Decimal("100000"), max_price=Decimal("50000")
        )
        self.assertFalse(is_valid)
        self.assertIn("above maximum", error)

    def test_validate_price_spike(self):
        """测试价格突变"""
        # 第一个值
        is_valid, _ = self.validator.validate_price(Decimal("50000"))
        self.assertTrue(is_valid)

        # 第二个值突变超过 50%
        is_valid, error = self.validator.validate_price(Decimal("80000"))
        self.assertFalse(is_valid)
        self.assertIn("spike detected", error)

    def test_validator_reset(self):
        """测试验证器重置"""
        # 设置一个值
        self.validator.validate_oi(Decimal("1000000"))
        self.assertIsNotNone(self.validator._last_valid_value)

        # 重置
        self.validator.reset()
        self.assertIsNone(self.validator._last_valid_value)

    def test_validator_with_logging_enabled(self):
        """测试启用日志的验证器"""
        validator = DataValidator(enable_logging=True)
        is_valid, error = validator.validate_oi(None)
        self.assertFalse(is_valid)
        self.assertIsNotNone(error)


class TestMultiInstrumentAlignment(unittest.TestCase):
    """测试多标的数据对齐验证"""

    def setUp(self):
        """创建临时测试文件"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

    def tearDown(self):
        """清理临时文件"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_alignment_perfect(self):
        """测试完美对齐的数据"""
        # 创建两个完全对齐的CSV文件
        primary_csv = self.temp_path / "primary.csv"
        secondary_csv = self.temp_path / "secondary.csv"

        primary_csv.write_text(
            "timestamp,open,high,low,close,volume\n"
            "2025-01-01,100,110,90,105,1000\n"
            "2025-01-02,105,115,95,110,1100\n"
        )

        secondary_csv.write_text(
            "timestamp,open,high,low,close,volume\n"
            "2025-01-01,50000,51000,49000,50500,2000\n"
            "2025-01-02,50500,51500,49500,51000,2100\n"
        )

        is_aligned, error = validate_multi_instrument_alignment(
            primary_csv, secondary_csv, min_alignment_rate=0.95
        )
        self.assertTrue(is_aligned)
        self.assertIsNone(error)

    def test_alignment_partial(self):
        """测试部分对齐的数据"""
        primary_csv = self.temp_path / "primary.csv"
        secondary_csv = self.temp_path / "secondary.csv"

        # 主标的有 10 条数据
        primary_data = "timestamp,open,high,low,close,volume\n"
        for i in range(10):
            primary_data += f"2025-01-{i + 1:02d},100,110,90,105,1000\n"
        primary_csv.write_text(primary_data)

        # 辅助标的只有 5 条数据（50% 对齐率）
        secondary_data = "timestamp,open,high,low,close,volume\n"
        for i in range(5):
            secondary_data += f"2025-01-{i + 1:02d},50000,51000,49000,50500,2000\n"
        secondary_csv.write_text(secondary_data)

        is_aligned, error = validate_multi_instrument_alignment(
            primary_csv, secondary_csv, min_alignment_rate=0.95
        )
        self.assertFalse(is_aligned)
        self.assertIn("对齐率过低", error)

    def test_alignment_primary_not_found(self):
        """测试主标的文件不存在"""
        secondary_csv = self.temp_path / "secondary.csv"
        secondary_csv.write_text("timestamp,open,high,low,close,volume\n")

        is_aligned, error = validate_multi_instrument_alignment(
            self.temp_path / "nonexistent.csv", secondary_csv, min_alignment_rate=0.95
        )
        self.assertFalse(is_aligned)
        self.assertIn("不存在", error)

    def test_alignment_secondary_not_found(self):
        """测试辅助标的文件不存在"""
        primary_csv = self.temp_path / "primary.csv"
        primary_csv.write_text("timestamp,open,high,low,close,volume\n")

        is_aligned, error = validate_multi_instrument_alignment(
            primary_csv, self.temp_path / "nonexistent.csv", min_alignment_rate=0.95
        )
        self.assertFalse(is_aligned)
        self.assertIn("不存在", error)

    def test_alignment_missing_time_column(self):
        """测试缺少时间列"""
        primary_csv = self.temp_path / "primary.csv"
        secondary_csv = self.temp_path / "secondary.csv"

        # 缺少时间列
        primary_csv.write_text("open,high,low,close,volume\n100,110,90,105,1000\n")
        secondary_csv.write_text(
            "timestamp,open,high,low,close,volume\n2025-01-01,50000,51000,49000,50500,2000\n"
        )

        is_aligned, error = validate_multi_instrument_alignment(
            primary_csv, secondary_csv, min_alignment_rate=0.95
        )
        self.assertFalse(is_aligned)
        self.assertIn("缺少时间列", error)

    def test_alignment_datetime_column(self):
        """测试使用 datetime 列名"""
        primary_csv = self.temp_path / "primary.csv"
        secondary_csv = self.temp_path / "secondary.csv"

        primary_csv.write_text(
            "datetime,open,high,low,close,volume\n2025-01-01,100,110,90,105,1000\n"
        )

        secondary_csv.write_text(
            "datetime,open,high,low,close,volume\n2025-01-01,50000,51000,49000,50500,2000\n"
        )

        is_aligned, error = validate_multi_instrument_alignment(
            primary_csv, secondary_csv, min_alignment_rate=0.95
        )
        self.assertTrue(is_aligned)
        self.assertIsNone(error)


if __name__ == "__main__":
    unittest.main()
