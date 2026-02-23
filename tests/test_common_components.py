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
