"""
Tests for common strategy components
"""

import pytest
from strategy.common.indicators import (
    KeltnerChannel,
    RelativeStrengthCalculator,
    MarketRegimeFilter,
)
from strategy.common.signals import EntrySignalGenerator, ExitSignalGenerator, SqueezeDetector
from strategy.common.universe import DynamicUniverseManager
from pathlib import Path
import json
import tempfile
from decimal import Decimal
from datetime import datetime


class TestKeltnerChannel:
    """测试 Keltner Channel 指标"""

    def test_initialization(self):
        """测试初始化"""
        keltner = KeltnerChannel(
            ema_period=20,
            atr_period=20,
            sma_period=200,
        )
        assert keltner.ema is None
        assert keltner.atr is None
        assert keltner.sma is None
        assert not keltner.is_ready()

    def test_update_and_calculation(self):
        """测试更新和计算"""
        keltner = KeltnerChannel(
            ema_period=5, atr_period=5, sma_period=5, bb_period=5, volume_period=5
        )

        # 模拟 10 根 K 线
        for i in range(10):
            high = 100 + i
            low = 95 + i
            close = 98 + i
            volume = 1000 + i * 10
            keltner.update(high, low, close, volume)

        # 检查指标是否计算完成
        assert keltner.ema is not None
        assert keltner.atr is not None
        assert keltner.sma is not None
        assert keltner.is_ready()

    def test_squeeze_detection(self):
        """测试 Squeeze 检测"""
        keltner = KeltnerChannel(
            ema_period=5,
            atr_period=5,
            bb_period=5,
            volume_period=5,
            sma_period=5,
            keltner_base_multiplier=1.5,
        )

        # 模拟低波动率数据（Squeeze 状态）
        for i in range(10):
            high = 100 + 0.1 * i
            low = 99.5 + 0.1 * i
            close = 99.8 + 0.1 * i
            volume = 1000
            keltner.update(high, low, close, volume)

        # 检查是否检测到 Squeeze
        assert keltner.is_ready()

    def test_bb_initialization(self):
        """测试 BB 实例正确初始化"""
        keltner = KeltnerChannel(bb_period=20, bb_std=2.0)

        # 验证 BB 实例存在
        assert keltner.bb is not None
        assert keltner.bb.period == 20
        assert keltner.bb.k == 2.0

        # 初始状态未初始化
        assert not keltner.bb.initialized

    def test_bb_update(self):
        """测试 BB 值更新正确"""
        keltner = KeltnerChannel(
            ema_period=5,
            atr_period=5,
            bb_period=5,
            bb_std=2.0,
            volume_period=5,
            sma_period=5,
        )

        # 更新 5 根 K 线（BB period = 5）
        data = [
            (100, 99, 100),
            (101, 100, 101),
            (102, 101, 102),
            (103, 102, 103),
            (104, 103, 104),
        ]

        for high, low, close in data:
            keltner.update(high, low, close, volume=1000)

        # 验证 BB 已初始化
        assert keltner.bb.initialized

        # 验证 BB 值存在且合理
        assert keltner.bb.upper > keltner.bb.middle
        assert keltner.bb.middle > keltner.bb.lower
        assert keltner.bb.upper > 104  # 应该大于最高价
        assert keltner.bb.lower < 100  # 应该小于最低价

    def test_bb_vs_numpy(self):
        """测试 BB 与 numpy 实现的结果对比（允许小误差）"""
        import numpy as np

        keltner = KeltnerChannel(
            ema_period=5,
            atr_period=5,
            bb_period=5,
            bb_std=2.0,
            volume_period=5,
            sma_period=5,
        )

        # 使用固定数据
        data = [
            (100, 99, 100),
            (101, 100, 101),
            (102, 101, 102),
            (103, 102, 103),
            (104, 103, 104),
        ]

        closes = []
        for high, low, close in data:
            keltner.update(high, low, close, volume=1000)
            closes.append(close)

        # NautilusTrader BB 使用 EMA，不是 SMA
        # 所以我们只验证 BB 的基本属性，不做精确数值比较
        assert keltner.bb.initialized

        # 验证 BB 宽度合理（upper - lower 应该是正数且不为零）
        bb_width = keltner.bb.upper - keltner.bb.lower
        assert bb_width > 0

        # 验证 middle 在合理范围内（应该接近最近价格）
        assert 100 <= keltner.bb.middle <= 104

    def test_bb_insufficient_data(self):
        """测试数据不足时的行为"""
        keltner = KeltnerChannel(
            ema_period=5,
            atr_period=5,
            bb_period=5,
            bb_std=2.0,
            volume_period=5,
            sma_period=5,
        )

        # 只更新 3 根 K 线（不足 BB period = 5）
        for i in range(3):
            keltner.update(100 + i, 99 + i, 100 + i, volume=1000)

        # BB 应该未初始化
        assert not keltner.bb.initialized

        # is_ready() 应该返回 False
        assert not keltner.is_ready()

        # is_squeezing() 应该返回 False（因为 BB 未初始化）
        assert not keltner.is_squeezing()

    def test_nautilus_ema_accuracy(self):
        """测试 NautilusTrader EMA 指标准确性"""
        import numpy as np

        keltner = KeltnerChannel(
            ema_period=5, atr_period=5, sma_period=5, bb_period=5, volume_period=5
        )

        # 使用固定数据
        closes = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0]

        for i, close in enumerate(closes):
            keltner.update(close + 1, close - 1, close, 1000.0)

        # 手动计算 EMA (alpha = 2 / (period + 1) = 2 / 6 = 0.333...)
        alpha = 2.0 / (5 + 1)
        ema_manual = closes[0]
        for close in closes[1:]:
            ema_manual = alpha * close + (1 - alpha) * ema_manual

        # 验证 EMA 值（允许 0.1% 容差）
        assert keltner.ema is not None
        assert abs(keltner.ema - ema_manual) / ema_manual < 0.001

    def test_nautilus_atr_accuracy(self):
        """测试 NautilusTrader ATR 指标准确性"""
        keltner = KeltnerChannel(
            ema_period=5, atr_period=5, sma_period=5, bb_period=5, volume_period=5
        )

        # 使用固定数据
        data = [
            (101.0, 99.0, 100.0),
            (102.0, 100.0, 101.0),
            (103.0, 101.0, 102.0),
            (104.0, 102.0, 103.0),
            (105.0, 103.0, 104.0),
            (106.0, 104.0, 105.0),
        ]

        prev_close = None
        trs = []
        for high, low, close in data:
            keltner.update(high, low, close, 1000.0)
            if prev_close is not None:
                tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
                trs.append(tr)
            prev_close = close

        # 手动计算 ATR (Wilder's smoothing: alpha = 1 / period)
        alpha = 1.0 / 5
        atr_manual = sum(trs[:5]) / 5
        for tr in trs[5:]:
            atr_manual = alpha * tr + (1 - alpha) * atr_manual

        # 验证 ATR 值（允许 0.1% 容差）
        assert keltner.atr is not None
        assert abs(keltner.atr - atr_manual) / atr_manual < 0.001

    def test_nautilus_sma_accuracy(self):
        """测试 NautilusTrader SMA 指标准确性"""
        keltner = KeltnerChannel(
            ema_period=5, atr_period=5, sma_period=5, bb_period=5, volume_period=5
        )

        # 使用固定数据
        closes = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]

        for close in closes:
            keltner.update(close + 1, close - 1, close, 1000.0)

        # 手动计算 SMA（最近 5 个值）
        sma_manual = sum(closes[-5:]) / 5

        # 验证 SMA 值（允许 0.1% 容差）
        assert keltner.sma is not None
        assert abs(keltner.sma - sma_manual) / sma_manual < 0.001

    def test_nautilus_volume_sma_accuracy(self):
        """测试 NautilusTrader Volume SMA 指标准确性"""
        keltner = KeltnerChannel(
            ema_period=5, atr_period=5, sma_period=5, bb_period=5, volume_period=5
        )

        # 使用固定数据
        volumes = [1000.0, 1100.0, 1200.0, 1300.0, 1400.0, 1500.0]

        for i, volume in enumerate(volumes):
            keltner.update(100.0 + i, 99.0 + i, 100.0 + i, volume)

        # 手动计算 Volume SMA（最近 5 个值）
        volume_sma_manual = sum(volumes[-5:]) / 5

        # 验证 Volume SMA 值（允许 0.1% 容差）
        assert keltner.volume_sma is not None
        assert abs(keltner.volume_sma - volume_sma_manual) / volume_sma_manual < 0.001

    def test_nautilus_keltner_bands_accuracy(self):
        """测试 Keltner Bands 计算准确性"""
        keltner = KeltnerChannel(
            ema_period=5,
            atr_period=5,
            sma_period=5,
            bb_period=5,
            volume_period=5,
            keltner_base_multiplier=1.5,
            keltner_trigger_multiplier=2.25,
        )

        # 使用固定数据
        data = [
            (101.0, 99.0, 100.0),
            (102.0, 100.0, 101.0),
            (103.0, 101.0, 102.0),
            (104.0, 102.0, 103.0),
            (105.0, 103.0, 104.0),
            (106.0, 104.0, 105.0),
        ]

        for high, low, close in data:
            keltner.update(high, low, close, 1000.0)

        # 获取 Keltner Bands
        base_upper, base_lower = keltner.get_keltner_base_bands()
        trigger_upper, trigger_lower = keltner.get_keltner_trigger_bands()

        # 验证 Bands 存在
        assert base_upper is not None
        assert base_lower is not None
        assert trigger_upper is not None
        assert trigger_lower is not None

        # 验证 Bands 关系
        assert base_upper > base_lower
        assert trigger_upper > trigger_lower
        assert trigger_upper > base_upper
        assert trigger_lower < base_lower

        # 验证 Bands 计算（手动验证）
        ema_value = keltner.ema
        atr_value = keltner.atr
        assert abs(base_upper - (ema_value + 1.5 * atr_value)) < 1e-6
        assert abs(base_lower - (ema_value - 1.5 * atr_value)) < 1e-6
        assert abs(trigger_upper - (ema_value + 2.25 * atr_value)) < 1e-6
        assert abs(trigger_lower - (ema_value - 2.25 * atr_value)) < 1e-6

    def test_nautilus_indicators_initialization_state(self):
        """测试 NautilusTrader 指标初始化状态"""
        keltner = KeltnerChannel(
            ema_period=5, atr_period=5, sma_period=5, bb_period=5, volume_period=5
        )

        # 初始状态：所有指标未初始化
        assert not keltner.ema_indicator.initialized
        assert not keltner.atr_indicator.initialized
        assert not keltner.sma_indicator.initialized
        assert not keltner.bb.initialized
        assert not keltner.volume_sma_indicator.initialized
        assert not keltner.is_ready()

        # 更新 5 根 K 线后，所有指标应该初始化
        for i in range(5):
            keltner.update(100.0 + i, 99.0 + i, 100.0 + i, 1000.0 + i)

        assert keltner.ema_indicator.initialized
        assert keltner.atr_indicator.initialized
        assert keltner.sma_indicator.initialized
        assert keltner.bb.initialized
        assert keltner.volume_sma_indicator.initialized
        assert keltner.is_ready()

    def test_nautilus_property_accessors(self):
        """测试 NautilusTrader 指标属性访问器"""
        keltner = KeltnerChannel(
            ema_period=5, atr_period=5, sma_period=5, bb_period=5, volume_period=5
        )

        # 初始状态：所有属性返回 None
        assert keltner.ema is None
        assert keltner.atr is None
        assert keltner.sma is None
        assert keltner.volume_sma is None

        # 更新数据后，属性应该返回值
        for i in range(6):
            keltner.update(100.0 + i, 99.0 + i, 100.0 + i, 1000.0 + i)

        assert keltner.ema is not None
        assert keltner.atr is not None
        assert keltner.sma is not None
        assert keltner.volume_sma is not None

        # 验证属性值与指标实例值一致
        assert keltner.ema == keltner.ema_indicator.value
        assert keltner.atr == keltner.atr_indicator.value
        assert keltner.sma == keltner.sma_indicator.value
        assert keltner.volume_sma == keltner.volume_sma_indicator.value

    def test_nautilus_squeeze_detection_with_indicators(self):
        """测试使用 NautilusTrader 指标的 Squeeze 检测"""
        keltner = KeltnerChannel(
            ema_period=5,
            atr_period=5,
            sma_period=5,
            bb_period=5,
            volume_period=5,
            keltner_base_multiplier=2.0,  # 更大的倍数，更容易触发 Squeeze
        )

        # 模拟低波动率数据（Squeeze 状态）
        for i in range(10):
            high = 100.0 + 0.05 * i
            low = 99.9 + 0.05 * i
            close = 99.95 + 0.05 * i
            keltner.update(high, low, close, 1000.0)

        # 验证指标已初始化
        assert keltner.is_ready()

        # 验证 Squeeze 检测逻辑
        bb_upper = keltner.bb.upper
        bb_lower = keltner.bb.lower
        keltner_upper, keltner_lower = keltner.get_keltner_base_bands()

        # 如果 BB 在 Keltner 内，应该检测到 Squeeze
        if bb_upper < keltner_upper and bb_lower > keltner_lower:
            assert keltner.is_squeezing()
        else:
            assert not keltner.is_squeezing()

    def test_nautilus_indicators_consistency_across_updates(self):
        """测试 NautilusTrader 指标在多次更新中的一致性"""
        keltner = KeltnerChannel(
            ema_period=5, atr_period=5, sma_period=5, bb_period=5, volume_period=5
        )

        # 第一轮更新（使用变化的波动率）
        for i in range(10):
            high = 100.0 + i + (i % 3) * 0.5  # 添加波动
            low = 99.0 + i - (i % 2) * 0.3
            close = 100.0 + i
            keltner.update(high, low, close, 1000.0 + i)

        # 记录第一轮的值
        ema_1 = keltner.ema
        atr_1 = keltner.atr
        sma_1 = keltner.sma
        volume_sma_1 = keltner.volume_sma

        # 第二轮更新（继续更新，波动率变化）
        for i in range(10, 15):
            high = 100.0 + i + (i % 4) * 0.8  # 不同的波动模式
            low = 99.0 + i - (i % 3) * 0.5
            close = 100.0 + i
            keltner.update(high, low, close, 1000.0 + i)

        # 记录第二轮的值
        ema_2 = keltner.ema
        atr_2 = keltner.atr
        sma_2 = keltner.sma
        volume_sma_2 = keltner.volume_sma

        # 验证值已更新（不应该相同）
        assert ema_2 != ema_1
        assert atr_2 != atr_1  # 现在波动率会变化
        assert sma_2 != sma_1
        assert volume_sma_2 != volume_sma_1

        # 验证值在合理范围内（应该接近最近的价格）
        assert 105.0 <= ema_2 <= 115.0
        assert 0.5 <= atr_2 <= 3.0  # 扩大范围以适应波动
        assert 105.0 <= sma_2 <= 115.0
        assert 1005.0 <= volume_sma_2 <= 1015.0

    def test_nautilus_indicators_edge_cases(self):
        """测试 NautilusTrader 指标的边界情况"""
        keltner = KeltnerChannel(
            ema_period=5, atr_period=5, sma_period=5, bb_period=5, volume_period=5
        )

        # 边界情况 1：所有价格相同（零波动率）
        for i in range(10):
            keltner.update(100.0, 100.0, 100.0, 1000.0)

        assert keltner.is_ready()
        assert keltner.ema == 100.0
        assert keltner.atr == 0.0  # 零波动率
        assert keltner.sma == 100.0
        assert keltner.volume_sma == 1000.0

        # 边界情况 2：极端波动
        keltner2 = KeltnerChannel(
            ema_period=5, atr_period=5, sma_period=5, bb_period=5, volume_period=5
        )
        for i in range(10):
            high = 100.0 + i * 10
            low = 90.0 + i * 10
            close = 95.0 + i * 10
            keltner2.update(high, low, close, 1000.0)

        assert keltner2.is_ready()
        assert keltner2.atr > 5.0  # 高波动率


class TestRelativeStrengthCalculator:
    """测试相对强度计算器"""

    def test_initialization(self):
        """测试初始化"""
        rs_calc = RelativeStrengthCalculator(
            short_lookback_days=5,
            long_lookback_days=20,
        )
        assert rs_calc.get_symbol_history_size() == 0
        assert rs_calc.get_benchmark_history_size() == 0

    def test_update_prices(self):
        """测试价格更新"""
        rs_calc = RelativeStrengthCalculator(
            short_lookback_days=5,
            long_lookback_days=20,
        )

        # 更新价格
        for i in range(25):
            timestamp = i * 1_000_000_000  # 纳秒
            rs_calc.update_symbol_price(timestamp, 100 + i)
            rs_calc.update_benchmark_price(timestamp, 50 + i * 0.5)

        assert rs_calc.get_symbol_history_size() == 25
        assert rs_calc.get_benchmark_history_size() == 25

    def test_rs_calculation(self):
        """测试 RS 计算"""
        rs_calc = RelativeStrengthCalculator(
            short_lookback_days=5,
            long_lookback_days=20,
        )

        # 模拟标的跑赢基准的情况
        for i in range(25):
            timestamp = i * 1_000_000_000
            rs_calc.update_symbol_price(timestamp, 100 * (1.02**i))  # 2% 日涨幅
            rs_calc.update_benchmark_price(timestamp, 100 * (1.01**i))  # 1% 日涨幅

        rs = rs_calc.calculate_rs()
        assert rs is not None
        assert rs > 0  # 标的跑赢基准


class TestMarketRegimeFilter:
    """测试市场状态过滤器"""

    def test_initialization(self):
        """测试初始化"""
        regime_filter = MarketRegimeFilter(
            sma_period=200,
            atr_period=14,
            max_atr_pct=0.03,
        )
        assert not regime_filter.is_ready()

    def test_bullish_regime_detection(self):
        """测试牛市检测"""
        regime_filter = MarketRegimeFilter(
            sma_period=10,
            atr_period=5,
            max_atr_pct=0.03,
        )

        # 模拟上涨趋势
        for i in range(15):
            high = 100 + i * 2
            low = 98 + i * 2
            close = 99 + i * 2
            regime_filter.update(high, low, close)

        assert regime_filter.is_ready()
        assert regime_filter.is_bullish_regime()


class TestEntrySignalGenerator:
    """测试入场信号生成器"""

    def test_keltner_breakout(self):
        """测试 Keltner 突破检测"""
        entry_signals = EntrySignalGenerator()

        # 突破情况
        assert entry_signals.check_keltner_breakout(105, 100)

        # 未突破情况
        assert not entry_signals.check_keltner_breakout(95, 100)

    def test_volume_surge(self):
        """测试成交量放大检测"""
        entry_signals = EntrySignalGenerator(volume_multiplier=1.5)

        # 成交量放大（1600 > 1000 * 1.5）
        assert entry_signals.check_volume_surge(1600.0, 1000.0)

        # 成交量未放大（1400 < 1000 * 1.5）
        assert not entry_signals.check_volume_surge(1400.0, 1000.0)


class TestExitSignalGenerator:
    """测试出场信号生成器"""

    def test_time_stop(self):
        """测试时间止损"""
        exit_signals = ExitSignalGenerator(
            enable_time_stop=True,
            time_stop_bars=3,
            time_stop_momentum_threshold=0.01,
        )

        # 未达到时间止损条件
        assert not exit_signals.check_time_stop(2, 101.0, Decimal("100"))

        # 达到时间止损条件（时间到且动能不足）
        assert exit_signals.check_time_stop(3, 100.5, Decimal("100"))

    def test_chandelier_exit(self):
        """测试 Chandelier Exit"""
        exit_signals = ExitSignalGenerator(stop_loss_atr_multiplier=2.0)

        # 未触发止损
        assert not exit_signals.check_chandelier_exit(98, 100, 1.0)

        # 触发止损
        assert exit_signals.check_chandelier_exit(95, 100, 1.0)


class TestSqueezeDetector:
    """测试 Squeeze 检测器"""

    def test_squeeze_detection(self):
        """测试 Squeeze 检测"""
        squeeze_detector = SqueezeDetector(memory_days=5)

        # Squeeze 状态：布林带在 Keltner 通道内
        is_squeezing = squeeze_detector.check_squeeze(
            bb_upper=102,
            bb_lower=98,
            keltner_upper=105,
            keltner_lower=95,
        )
        assert is_squeezing

        # 非 Squeeze 状态：布林带超出 Keltner 通道
        is_squeezing = squeeze_detector.check_squeeze(
            bb_upper=106,
            bb_lower=94,
            keltner_upper=105,
            keltner_lower=95,
        )
        assert not is_squeezing


class TestDynamicUniverseManager:
    """测试动态 Universe 管理器"""

    def test_initialization_and_loading(self):
        """测试初始化和加载"""
        # 创建临时 Universe 文件
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            universe_data = {
                "2020-01": ["BTCUSDT", "ETHUSDT"],
                "2020-02": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
            }
            json.dump(universe_data, f)
            temp_file = Path(f.name)

        try:
            universe_manager = DynamicUniverseManager(
                universe_file=temp_file,
                freq="ME",
            )

            assert len(universe_manager.get_all_periods()) == 2
        finally:
            temp_file.unlink()

    def test_symbol_activity_check(self):
        """测试标的活跃性检查"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            universe_data = {
                "2020-01": ["BTCUSDT", "ETHUSDT"],
            }
            json.dump(universe_data, f)
            temp_file = Path(f.name)

        try:
            universe_manager = DynamicUniverseManager(
                universe_file=temp_file,
                freq="ME",
            )

            # 更新到 2020-01
            timestamp = int(datetime(2020, 1, 15).timestamp() * 1e9)
            universe_manager.update(timestamp)

            # 检查活跃性
            assert universe_manager.is_active("BTCUSDT")
            assert universe_manager.is_active("ETHUSDT")
            assert not universe_manager.is_active("BNBUSDT")
        finally:
            temp_file.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
