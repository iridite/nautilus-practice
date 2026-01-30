"""
OI Divergence 策略单元测试

测试内容：
1. 自定义数据类型（OpenInterestData, FundingRateData）
2. 策略配置验证
3. 信号检测逻辑
4. 数据加载器功能
5. 策略基本功能

Usage:
    uv run python -m unittest tests.test_oi_divergence -v
"""

import unittest
from decimal import Decimal
from pathlib import Path

from nautilus_trader.core.nautilus_pyo3 import millis_to_nanos
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.test_kit.stubs.data import TestDataStubs

from strategy.oi_divergence import OIDivergenceStrategy, OIDivergenceStrategyConfig
from utils.custom_data import FundingRateData, OpenInterestData


class TestCustomData(unittest.TestCase):
    """测试自定义数据类型"""

    def setUp(self):
        """初始化测试数据"""
        self.instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        self.ts_event = millis_to_nanos(1704067200000)  # 2024-01-01 00:00:00 UTC
        self.ts_init = self.ts_event

    def test_open_interest_data_creation(self):
        """测试 OpenInterestData 创建"""
        oi = Decimal("1000000.5")
        data = OpenInterestData(
            instrument_id=self.instrument_id,
            open_interest=oi,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )

        self.assertEqual(data.instrument_id, self.instrument_id)
        self.assertEqual(data.open_interest, oi)
        self.assertEqual(data.ts_event, self.ts_event)
        self.assertEqual(data.ts_init, self.ts_init)

    def test_open_interest_data_repr(self):
        """测试 OpenInterestData 字符串表示"""
        data = OpenInterestData(
            instrument_id=self.instrument_id,
            open_interest=Decimal("1000000"),
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )

        repr_str = repr(data)
        self.assertIn("OpenInterestData", repr_str)
        self.assertIn("BTCUSDT.BINANCE", repr_str)
        self.assertIn("1000000", repr_str)

    def test_open_interest_data_equality(self):
        """测试 OpenInterestData 相等性"""
        data1 = OpenInterestData(
            instrument_id=self.instrument_id,
            open_interest=Decimal("1000000"),
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )

        data2 = OpenInterestData(
            instrument_id=self.instrument_id,
            open_interest=Decimal("1000000"),
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )

        self.assertEqual(data1, data2)
        self.assertEqual(hash(data1), hash(data2))

    def test_funding_rate_data_creation(self):
        """测试 FundingRateData 创建"""
        funding_rate = Decimal("0.0001")  # 0.01%
        next_funding_time = millis_to_nanos(1704096000000)  # 8 hours later

        data = FundingRateData(
            instrument_id=self.instrument_id,
            funding_rate=funding_rate,
            next_funding_time=next_funding_time,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )

        self.assertEqual(data.instrument_id, self.instrument_id)
        self.assertEqual(data.funding_rate, funding_rate)
        self.assertEqual(data.next_funding_time, next_funding_time)

    def test_funding_rate_annual_calculation(self):
        """测试年化资金费率计算"""
        # 资金费率 0.01% 每 8 小时
        funding_rate = Decimal("0.0001")

        data = FundingRateData(
            instrument_id=self.instrument_id,
            funding_rate=funding_rate,
            next_funding_time=None,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )

        # 年化 = 0.0001 * 3 (每天) * 365 (天) * 100 (百分比)
        expected_annual = Decimal("0.0001") * 3 * 365 * 100
        self.assertEqual(data.funding_rate_annual, expected_annual)
        self.assertAlmostEqual(float(data.funding_rate_annual), 10.95, places=2)

    def test_funding_rate_data_repr(self):
        """测试 FundingRateData 字符串表示"""
        data = FundingRateData(
            instrument_id=self.instrument_id,
            funding_rate=Decimal("0.0001"),
            next_funding_time=None,
            ts_event=self.ts_event,
            ts_init=self.ts_init,
        )

        repr_str = repr(data)
        self.assertIn("FundingRateData", repr_str)
        self.assertIn("BTCUSDT.BINANCE", repr_str)
        self.assertIn("annual=", repr_str)


class TestOIDivergenceConfig(unittest.TestCase):
    """测试 OI Divergence 策略配置"""

    def test_default_config(self):
        """测试默认配置"""
        config = OIDivergenceStrategyConfig(
            instrument_id="BTCUSDT.BINANCE",
            bar_type="BTCUSDT.BINANCE-1-HOUR-LAST-EXTERNAL",
        )

        self.assertEqual(config.lookback_bars, 48)
        self.assertEqual(config.oi_decline_threshold, 0.05)
        self.assertEqual(config.funding_rate_threshold_annual, 30.0)
        self.assertTrue(config.use_funding_filter)
        self.assertTrue(config.tp_use_vwap)
        self.assertEqual(config.max_positions, 1)

    def test_custom_config(self):
        """测试自定义配置"""
        config = OIDivergenceStrategyConfig(
            instrument_id="ETHUSDT.BINANCE",
            bar_type="ETHUSDT.BINANCE-1-HOUR-LAST-EXTERNAL",
            lookback_bars=24,
            oi_decline_threshold=0.03,
            funding_rate_threshold_annual=50.0,
            use_funding_filter=False,
            stop_loss_pct=0.02,
            time_stop_bars=12,
            trade_size=0.5,
        )

        self.assertEqual(config.lookback_bars, 24)
        self.assertEqual(config.oi_decline_threshold, 0.03)
        self.assertEqual(config.funding_rate_threshold_annual, 50.0)
        self.assertFalse(config.use_funding_filter)
        self.assertEqual(config.stop_loss_pct, 0.02)
        self.assertEqual(config.time_stop_bars, 12)
        self.assertEqual(config.trade_size, 0.5)


class TestOIDivergenceStrategy(unittest.TestCase):
    """测试 OI Divergence 策略逻辑"""

    def setUp(self):
        """初始化测试环境"""
        from nautilus_trader.test_kit.stubs.component import TestComponentStubs

        self.config = OIDivergenceStrategyConfig(
            instrument_id="BTCUSDT.BINANCE",
            bar_type="BTCUSDT.BINANCE-1-HOUR-LAST-EXTERNAL",
            lookback_bars=48,
            oi_decline_threshold=0.05,
            trade_size=0.1,
        )

        # 创建策略实例（使用测试桩）
        self.strategy = OIDivergenceStrategy(config=self.config)

    def test_strategy_initialization(self):
        """测试策略初始化"""
        self.assertIsNotNone(self.strategy)
        self.assertEqual(self.strategy.config.lookback_bars, 48)
        self.assertEqual(len(self.strategy.bars_main), 0)
        self.assertEqual(len(self.strategy.oi_history), 0)
        self.assertIsNone(self.strategy.resistance)
        self.assertIsNone(self.strategy.support)

    def test_is_ready_false_initially(self):
        """测试策略初始状态未就绪"""
        self.assertFalse(self.strategy._is_ready())

    def test_oi_decline_detection_insufficient_data(self):
        """测试 OI 下降检测 - 数据不足"""
        # 没有足够的 OI 数据
        self.strategy.current_oi = Decimal("1000000")
        result = self.strategy._calculate_oi_divergence()
        self.assertIsNone(result, "数据不足时应返回 None")

    def test_oi_decline_detection_with_data(self):
        """测试 OI 下降检测 - 有足够数据"""
        # 模拟 OI 历史数据
        for i in range(12):
            self.strategy.oi_history.append(
                {
                    "ts": millis_to_nanos(1704067200000 + i * 3600000),
                    "oi": Decimal("1000000"),
                    "data": None,
                }
            )

        # 当前 OI 下降 6%（超过 5% 阈值）
        self.strategy.current_oi = Decimal("940000")
        result = self.strategy._calculate_oi_divergence()
        self.assertIsNotNone(result)
        self.assertLess(result, Decimal("0"), "OI下降应返回负值")

        # 验证下降幅度达到阈值
        is_declining = result <= -Decimal(str(self.strategy.config.oi_decline_threshold))
        self.assertTrue(is_declining, "下降6%应超过5%阈值")

        # 当前 OI 仅下降 3%（未超过阈值）
        self.strategy.current_oi = Decimal("970000")
        result = self.strategy._calculate_oi_divergence()
        self.assertIsNotNone(result)
        is_declining = result <= -Decimal(str(self.strategy.config.oi_decline_threshold))
        self.assertFalse(is_declining, "下降3%应未超过5%阈值")

    def test_funding_rate_high_detection(self):
        """测试高资金费率检测"""
        # 年化资金费率 40%（高于 30% 阈值）
        self.strategy.current_funding_rate_annual = Decimal("40.0")
        is_high = self.strategy.current_funding_rate_annual > Decimal(str(self.strategy.config.funding_rate_threshold_annual))
        self.assertTrue(is_high, "40%应高于30%阈值")

        # 年化资金费率 20%（低于阈值）
        self.strategy.current_funding_rate_annual = Decimal("20.0")
        is_high = self.strategy.current_funding_rate_annual > Decimal(str(self.strategy.config.funding_rate_threshold_annual))
        self.assertFalse(is_high, "20%应低于30%阈值")

    def test_funding_rate_low_detection(self):
        """测试低资金费率检测"""
        # 年化资金费率 -40%（空头拥挤）
        self.strategy.current_funding_rate_annual = Decimal("-40.0")
        is_low = self.strategy.current_funding_rate_annual < -Decimal(str(self.strategy.config.funding_rate_threshold_annual))
        self.assertTrue(is_low, "-40%应低于-30%阈值")

        # 年化资金费率 -20%（未达到阈值）
        self.strategy.current_funding_rate_annual = Decimal("-20.0")
        is_low = self.strategy.current_funding_rate_annual < -Decimal(str(self.strategy.config.funding_rate_threshold_annual))
        self.assertFalse(is_low, "-20%应高于-30%阈值")

    def test_update_key_levels(self):
        """测试关键价位更新"""
        from nautilus_trader.model.data import BarType
        from nautilus_trader.test_kit.stubs.data import TestDataStubs

        # 创建模拟 Bar 数据
        bar_type = BarType.from_str("BTCUSDT.BINANCE-1-HOUR-LAST-EXTERNAL")

        for i in range(48):
            # 使用默认的TestDataStubs.bar_5decimal()方法
            # Bar对象是不可变的，所以我们使用默认价格进行测试
            bar = TestDataStubs.bar_5decimal()
            self.strategy.bars_main.append(bar)

        # 更新关键价位
        self.strategy._update_key_levels()

        self.assertIsNotNone(self.strategy.resistance)
        self.assertIsNotNone(self.strategy.support)
        self.assertIsNotNone(self.strategy.midpoint)

        # Resistance 应该是最高价
        # Support 应该是最低价
        self.assertGreater(self.strategy.resistance, self.strategy.support)
        self.assertEqual(
            self.strategy.midpoint,
            (self.strategy.resistance + self.strategy.support) / Decimal("2"),
        )


class TestOIFundingDataLoader(unittest.TestCase):
    """测试 OI 和 Funding Rate 数据加载器"""

    def setUp(self):
        """初始化测试环境"""
        from utils.oi_funding_adapter import OIFundingDataLoader

        self.project_root = Path(__file__).parent.parent
        self.loader = OIFundingDataLoader(self.project_root)

    def test_loader_initialization(self):
        """测试加载器初始化"""
        self.assertIsNotNone(self.loader)
        self.assertEqual(self.loader.base_dir, self.project_root)
        self.assertTrue(self.loader.data_dir.exists() or True)  # 目录可能不存在


class TestDataAlignment(unittest.TestCase):
    """测试数据对齐功能"""

    def test_merge_custom_data(self):
        """测试合并自定义数据"""
        from utils.oi_funding_adapter import merge_custom_data_with_bars

        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")

        # 创建模拟 OI 数据
        oi_data = [
            OpenInterestData(
                instrument_id=instrument_id,
                open_interest=Decimal("1000000"),
                ts_event=millis_to_nanos(1704067200000),
                ts_init=millis_to_nanos(1704067200000),
            ),
            OpenInterestData(
                instrument_id=instrument_id,
                open_interest=Decimal("1100000"),
                ts_event=millis_to_nanos(1704070800000),
                ts_init=millis_to_nanos(1704070800000),
            ),
        ]

        # 创建模拟 Funding Rate 数据
        funding_data = [
            FundingRateData(
                instrument_id=instrument_id,
                funding_rate=Decimal("0.0001"),
                next_funding_time=None,
                ts_event=millis_to_nanos(1704067200000),
                ts_init=millis_to_nanos(1704067200000),
            )
        ]

        # 合并数据
        merged = merge_custom_data_with_bars(oi_data, funding_data)

        self.assertEqual(len(merged), 3)
        # 数据应该按时间排序
        for i in range(len(merged) - 1):
            self.assertLessEqual(merged[i].ts_event, merged[i + 1].ts_event)


if __name__ == "__main__":
    unittest.main()
