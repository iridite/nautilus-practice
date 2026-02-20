"""
Tests for Dual Thrust strategy configuration and components
"""

import pytest
from strategy.dual_thrust import DualThrustConfig
from strategy.common.indicators import DualThrustIndicator
from strategy.common.signals import DualThrustSignalGenerator


class TestDualThrustConfig:
    """测试 Dual Thrust 配置"""

    def test_default_config(self):
        """测试默认配置"""
        config = DualThrustConfig(
            symbol="BTCUSDT",
            timeframe="1h",
        )
        assert config.lookback_period == 4
        assert config.k1 == 0.5
        assert config.k2 == 0.5

    def test_custom_config(self):
        """测试自定义配置"""
        config = DualThrustConfig(
            symbol="ETHUSDT",
            timeframe="4h",
            lookback_period=5,
            k1=0.6,
            k2=0.4,
        )
        assert config.lookback_period == 5
        assert config.k1 == 0.6
        assert config.k2 == 0.4


class TestDualThrustIndicator:
    """测试 Dual Thrust 指标"""

    def test_initialization(self):
        """测试初始化"""
        indicator = DualThrustIndicator(
            lookback_period=4,
            k1=0.5,
            k2=0.5,
        )
        assert indicator.upper_band is None
        assert indicator.lower_band is None
        assert indicator.range_value is None
        assert not indicator.is_ready()

    def test_update_and_calculation(self):
        """测试更新和计算"""
        indicator = DualThrustIndicator(lookback_period=4, k1=0.5, k2=0.5)

        # 模拟 6 根 K 线（需要 lookback_period + 1 = 5 根才能计算）
        test_data = [
            (102, 98, 100, 100),   # Day 1
            (104, 100, 102, 102),  # Day 2
            (106, 102, 104, 104),  # Day 3
            (108, 104, 106, 106),  # Day 4
            (110, 106, 108, 108),  # Day 5 (现在���以计算了)
            (112, 108, 110, 110),  # Day 6
        ]

        for high, low, close, open_price in test_data:
            indicator.update(high, low, close, open_price)

        # 验证指标已计算
        assert indicator.is_ready()
        assert indicator.upper_band is not None
        assert indicator.lower_band is not None
        assert indicator.range_value is not None

        # 验证通道计算逻辑
        upper, lower = indicator.get_bands()
        assert upper is not None
        assert lower is not None
        assert upper > lower  # 上轨应该大于下轨

    def test_range_calculation(self):
        """测试 Range 计算逻辑"""
        indicator = DualThrustIndicator(lookback_period=2, k1=0.5, k2=0.5)

        # 简单的测试数据
        test_data = [
            (105, 95, 103, 100),   # Day 1
            (110, 100, 108, 105),  # Day 2
            (115, 105, 113, 110),  # Day 3 (现在可以计算)
        ]

        for high, low, close, open_price in test_data:
            indicator.update(high, low, close, open_price)

        assert indicator.is_ready()
        range_value = indicator.get_range()
        assert range_value is not None
        assert range_value > 0


class TestDualThrustSignalGenerator:
    """测试 Dual Thrust 信号生成器"""

    def test_long_entry_signal(self):
        """测试做多入场信号"""
        signals = DualThrustSignalGenerator()

        # 价格突破上轨
        assert signals.check_long_entry(price=105, upper_band=100)

        # 价格未突破上轨
        assert not signals.check_long_entry(price=95, upper_band=100)

        # 上轨为 None
        assert not signals.check_long_entry(price=105, upper_band=None)

    def test_short_entry_signal(self):
        """测试做空入场信号"""
        signals = DualThrustSignalGenerator()

        # 价格突破下轨
        assert signals.check_short_entry(price=95, lower_band=100)

        # 价格未突破下轨
        assert not signals.check_short_entry(price=105, lower_band=100)

        # 下轨为 None
        assert not signals.check_short_entry(price=95, lower_band=None)

    def test_long_exit_signal(self):
        """测试多头出场信号"""
        signals = DualThrustSignalGenerator()

        # 价格跌破下轨（止损）
        assert signals.check_long_exit(price=95, lower_band=100)

        # 价格未跌破下轨
        assert not signals.check_long_exit(price=105, lower_band=100)

        # 下轨为 None
        assert not signals.check_long_exit(price=95, lower_band=None)

    def test_short_exit_signal(self):
        """测试空头出场信号"""
        signals = DualThrustSignalGenerator()

        # 价格突破上轨（止损）
        assert signals.check_short_exit(price=105, upper_band=100)

        # 价格未突破上轨
        assert not signals.check_short_exit(price=95, upper_band=100)

        # 上轨为 None
        assert not signals.check_short_exit(price=105, upper_band=None)


class TestDualThrustIntegration:
    """测试 Dual Thrust 组件集成"""

    def test_indicator_and_signals_integration(self):
        """测试指标和信号生成器的集成"""
        indicator = DualThrustIndicator(lookback_period=3, k1=0.5, k2=0.5)
        signals = DualThrustSignalGenerator()

        # 模拟价格数据
        test_data = [
            (105, 95, 100, 100),
            (110, 100, 105, 105),
            (115, 105, 110, 110),
            (120, 110, 115, 115),  # 现在可以计算通道
        ]

        for high, low, close, open_price in test_data:
            indicator.update(high, low, close, open_price)

        # 验证指标准备好
        assert indicator.is_ready()

        # 获取通道
        upper, lower = indicator.get_bands()
        assert upper is not None
        assert lower is not None

        # 测试信号生成
        # 假设当前价格突破上轨
        current_price = upper + 1
        assert signals.check_long_entry(current_price, upper)

        # 假设当前价格跌破下轨
        current_price = lower - 1
        assert signals.check_short_entry(current_price, lower)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
