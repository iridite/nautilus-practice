"""
测试 utils/custom_data.py 自定义数据类型
"""

import unittest
from decimal import Decimal

from nautilus_trader.model.identifiers import InstrumentId

from utils.custom_data import OpenInterestData, FundingRateData


class TestOpenInterestData(unittest.TestCase):
    """测试 OpenInterestData 类"""

    def setUp(self):
        """设置测试数据"""
        self.instrument_id = InstrumentId.from_str("BTC-USDT-SWAP.OKX")
        self.open_interest = Decimal("1000000")
        self.ts_event = 1704067200000000000
        self.ts_init = 1704067200000000000

    def test_initialization(self):
        """测试初始化"""
        data = OpenInterestData(
            instrument_id=self.instrument_id,
            open_interest=self.open_interest,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        self.assertEqual(data.instrument_id, self.instrument_id)
        self.assertEqual(data.open_interest, self.open_interest)
        self.assertEqual(data.ts_event, self.ts_event)
        self.assertEqual(data.ts_init, self.ts_init)

    def test_properties(self):
        """测试属性访问"""
        data = OpenInterestData(
            instrument_id=self.instrument_id,
            open_interest=self.open_interest,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        self.assertEqual(data.ts_event, self.ts_event)
        self.assertEqual(data.ts_init, self.ts_init)

    def test_repr(self):
        """测试字符串表示"""
        data = OpenInterestData(
            instrument_id=self.instrument_id,
            open_interest=self.open_interest,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        repr_str = repr(data)
        self.assertIn("OpenInterestData", repr_str)
        self.assertIn("BTC-USDT-SWAP.OKX", repr_str)
        self.assertIn("1000000", repr_str)

    def test_equality(self):
        """测试相等性比较"""
        data1 = OpenInterestData(
            instrument_id=self.instrument_id,
            open_interest=self.open_interest,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        data2 = OpenInterestData(
            instrument_id=self.instrument_id,
            open_interest=self.open_interest,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        self.assertEqual(data1, data2)

    def test_inequality(self):
        """测试不相等性"""
        data1 = OpenInterestData(
            instrument_id=self.instrument_id,
            open_interest=self.open_interest,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        data2 = OpenInterestData(
            instrument_id=self.instrument_id,
            open_interest=Decimal("2000000"),
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        self.assertNotEqual(data1, data2)

    def test_equality_with_different_type(self):
        """测试与不同类型的比较"""
        data = OpenInterestData(
            instrument_id=self.instrument_id,
            open_interest=self.open_interest,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        self.assertNotEqual(data, "not a data object")
        self.assertNotEqual(data, 123)

    def test_hash(self):
        """测试哈希值"""
        data1 = OpenInterestData(
            instrument_id=self.instrument_id,
            open_interest=self.open_interest,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        data2 = OpenInterestData(
            instrument_id=self.instrument_id,
            open_interest=self.open_interest,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        self.assertEqual(hash(data1), hash(data2))

    def test_hash_in_set(self):
        """测试在集合中使用"""
        data1 = OpenInterestData(
            instrument_id=self.instrument_id,
            open_interest=self.open_interest,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        data2 = OpenInterestData(
            instrument_id=self.instrument_id,
            open_interest=self.open_interest,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        data_set = {data1, data2}
        self.assertEqual(len(data_set), 1)  # 相同的数据应该只有一个


class TestFundingRateData(unittest.TestCase):
    """测试 FundingRateData 类"""

    def setUp(self):
        """设置测试数据"""
        self.instrument_id = InstrumentId.from_str("BTC-USDT-SWAP.OKX")
        self.funding_rate = Decimal("0.0001")
        self.next_funding_time = 1704096000000000000
        self.ts_event = 1704067200000000000
        self.ts_init = 1704067200000000000

    def test_initialization(self):
        """测试初始化"""
        data = FundingRateData(
            instrument_id=self.instrument_id,
            funding_rate=self.funding_rate,
            next_funding_time=self.next_funding_time,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        self.assertEqual(data.instrument_id, self.instrument_id)
        self.assertEqual(data.funding_rate, self.funding_rate)
        self.assertEqual(data.next_funding_time, self.next_funding_time)
        self.assertEqual(data.ts_event, self.ts_event)
        self.assertEqual(data.ts_init, self.ts_init)

    def test_initialization_without_next_funding_time(self):
        """测试不带下次结算时间的初始化"""
        data = FundingRateData(
            instrument_id=self.instrument_id,
            funding_rate=self.funding_rate,
            next_funding_time=None,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        self.assertIsNone(data.next_funding_time)

    def test_properties(self):
        """测试属性访问"""
        data = FundingRateData(
            instrument_id=self.instrument_id,
            funding_rate=self.funding_rate,
            next_funding_time=self.next_funding_time,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        self.assertEqual(data.ts_event, self.ts_event)
        self.assertEqual(data.ts_init, self.ts_init)

    def test_funding_rate_annual(self):
        """测试年化资金费率计算"""
        data = FundingRateData(
            instrument_id=self.instrument_id,
            funding_rate=Decimal("0.0001"),
            next_funding_time=self.next_funding_time,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        # 0.0001 * 3 * 365 * 100 = 10.95
        expected = Decimal("0.0001") * Decimal("3") * Decimal("365") * Decimal("100")
        self.assertEqual(data.funding_rate_annual, expected)

    def test_funding_rate_annual_negative(self):
        """测试负资金费率的年化"""
        data = FundingRateData(
            instrument_id=self.instrument_id,
            funding_rate=Decimal("-0.0001"),
            next_funding_time=self.next_funding_time,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        expected = Decimal("-0.0001") * Decimal("3") * Decimal("365") * Decimal("100")
        self.assertEqual(data.funding_rate_annual, expected)

    def test_repr(self):
        """测试字符串表示"""
        data = FundingRateData(
            instrument_id=self.instrument_id,
            funding_rate=self.funding_rate,
            next_funding_time=self.next_funding_time,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        repr_str = repr(data)
        self.assertIn("FundingRateData", repr_str)
        self.assertIn("BTC-USDT-SWAP.OKX", repr_str)
        self.assertIn("0.0001", repr_str)
        self.assertIn("annual", repr_str)

    def test_equality(self):
        """测试相等性比较"""
        data1 = FundingRateData(
            instrument_id=self.instrument_id,
            funding_rate=self.funding_rate,
            next_funding_time=self.next_funding_time,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        data2 = FundingRateData(
            instrument_id=self.instrument_id,
            funding_rate=self.funding_rate,
            next_funding_time=self.next_funding_time,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        self.assertEqual(data1, data2)

    def test_inequality(self):
        """测试不相等性"""
        data1 = FundingRateData(
            instrument_id=self.instrument_id,
            funding_rate=self.funding_rate,
            next_funding_time=self.next_funding_time,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        data2 = FundingRateData(
            instrument_id=self.instrument_id,
            funding_rate=Decimal("0.0002"),
            next_funding_time=self.next_funding_time,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        self.assertNotEqual(data1, data2)

    def test_equality_with_different_type(self):
        """测试与不同类型的比较"""
        data = FundingRateData(
            instrument_id=self.instrument_id,
            funding_rate=self.funding_rate,
            next_funding_time=self.next_funding_time,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        self.assertNotEqual(data, "not a data object")
        self.assertNotEqual(data, 123)

    def test_hash(self):
        """测试哈希值"""
        data1 = FundingRateData(
            instrument_id=self.instrument_id,
            funding_rate=self.funding_rate,
            next_funding_time=self.next_funding_time,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        data2 = FundingRateData(
            instrument_id=self.instrument_id,
            funding_rate=self.funding_rate,
            next_funding_time=self.next_funding_time,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        self.assertEqual(hash(data1), hash(data2))

    def test_hash_in_set(self):
        """测试在集合中使用"""
        data1 = FundingRateData(
            instrument_id=self.instrument_id,
            funding_rate=self.funding_rate,
            next_funding_time=self.next_funding_time,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        data2 = FundingRateData(
            instrument_id=self.instrument_id,
            funding_rate=self.funding_rate,
            next_funding_time=self.next_funding_time,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )
        data_set = {data1, data2}
        self.assertEqual(len(data_set), 1)  # 相同的数据应该只有一个


if __name__ == "__main__":
    unittest.main()
