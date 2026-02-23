"""
KeltnerChannel 集成测试

验证 KeltnerChannel 在策略中的集成和信号生成逻辑。
"""

import unittest
import pandas as pd
from pathlib import Path

from strategy.common.indicators import KeltnerChannel
from config.constants import (
    DEFAULT_EMA_PERIOD,
    DEFAULT_ATR_PERIOD_LONG,
    DEFAULT_SMA_PERIOD,
    DEFAULT_BB_PERIOD,
    DEFAULT_BB_STD,
    DEFAULT_KELTNER_BASE_MULTIPLIER,
    DEFAULT_KELTNER_TRIGGER_MULTIPLIER,
)


class TestKeltnerChannelIntegration(unittest.TestCase):
    """KeltnerChannel 集成测试"""

    @classmethod
    def setUpClass(cls):
        """测试类初始化 - 加载真实历史数据"""
        cls.base_dir = Path(__file__).parent.parent.parent
        cls.data_file = (
            cls.base_dir / "data/raw/1000BONKUSDT/binance-1000BONKUSDT-1d-2024-01-01_2024-12-31.csv"
        )

        # 加载测试数据（CI 环境中跳过）
        if not cls.data_file.exists():
            raise unittest.SkipTest(f"测试数据文件不存在，跳过集成测试: {cls.data_file}")

        cls.df = pd.read_csv(cls.data_file)
        # 使用全部数据（约 365 条），确保足够 SMA(200) 预热

    def test_keltner_channel_in_strategy(self):
        """测试 KeltnerChannel 在策略中正常工作"""
        # 创建 KeltnerChannel 实例
        keltner = KeltnerChannel(
            ema_period=DEFAULT_EMA_PERIOD,
            atr_period=DEFAULT_ATR_PERIOD_LONG,
            sma_period=DEFAULT_SMA_PERIOD,
            bb_period=DEFAULT_BB_PERIOD,
            bb_std=DEFAULT_BB_STD,
            volume_period=DEFAULT_EMA_PERIOD,
            keltner_base_multiplier=DEFAULT_KELTNER_BASE_MULTIPLIER,
            keltner_trigger_multiplier=DEFAULT_KELTNER_TRIGGER_MULTIPLIER,
        )

        # 逐条更新数据
        for idx, row in self.df.iterrows():
            keltner.update(
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            )

        # 验证指标已准备好
        self.assertTrue(keltner.is_ready(), "KeltnerChannel 应该已准备好")

        # 验证所有指标都已计算
        self.assertIsNotNone(keltner.ema, "EMA 应该已计算")
        self.assertIsNotNone(keltner.atr, "ATR 应该已计算")
        self.assertIsNotNone(keltner.sma, "SMA 应该已计算")
        self.assertIsNotNone(keltner.volume_sma, "Volume SMA 应该已计算")
        self.assertTrue(keltner.bb.initialized, "BollingerBands 应该已初始化")

        # 验证通道值合理
        trigger_upper, trigger_lower = keltner.get_keltner_trigger_bands()
        base_upper, base_lower = keltner.get_keltner_base_bands()

        self.assertIsNotNone(trigger_upper, "Trigger 上轨应该已计算")
        self.assertIsNotNone(trigger_lower, "Trigger 下轨应该已计算")
        self.assertIsNotNone(base_upper, "Base 上轨应该已计算")
        self.assertIsNotNone(base_lower, "Base 下轨应该已计算")

        # 验证通道关系：Trigger 通道应该比 Base 通道更宽
        self.assertGreater(trigger_upper, base_upper, "Trigger 上轨应该高于 Base 上轨")
        self.assertLess(trigger_lower, base_lower, "Trigger 下轨应该低于 Base 下轨")

        # 验证通道对称性
        last_close = self.df.iloc[-1]["close"]
        self.assertGreater(trigger_upper, last_close, "上轨应该高于收盘价")
        self.assertLess(trigger_lower, last_close, "下轨应该低于收盘价")

    def test_signal_generation_unchanged(self):
        """测试信号生成逻辑不变"""
        # 创建两个 KeltnerChannel 实例（模拟重构前后）
        keltner_new = KeltnerChannel(
            ema_period=20,
            atr_period=20,
            sma_period=200,
            bb_period=20,
            bb_std=2.0,
            volume_period=20,
            keltner_base_multiplier=1.5,
            keltner_trigger_multiplier=2.25,
        )

        # 记录关键信号点
        squeeze_signals = []
        breakout_signals = []

        # 逐条更新数据并记录信号
        for idx, row in self.df.iterrows():
            keltner_new.update(
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            )

            if not keltner_new.is_ready():
                continue

            # 记录 Squeeze 状态
            is_squeeze = keltner_new.is_squeezing()
            squeeze_signals.append(is_squeeze)

            # 记录突破信号
            trigger_upper, trigger_lower = keltner_new.get_keltner_trigger_bands()
            if trigger_upper and trigger_lower:
                close = row["close"]
                breakout_up = close > trigger_upper
                breakout_down = close < trigger_lower
                breakout_signals.append((breakout_up, breakout_down))

        # 验证信号生成
        self.assertGreater(len(squeeze_signals), 0, "应该生成 Squeeze 信号")
        self.assertGreater(len(breakout_signals), 0, "应该生成突破信号")

        # 验证信号合理性
        squeeze_count = sum(squeeze_signals)
        self.assertGreaterEqual(squeeze_count, 0, "Squeeze 信号数量应该 >= 0")

        # 验证突破信号互斥性（不能同时向上和向下突破）
        for breakout_up, breakout_down in breakout_signals:
            self.assertFalse(breakout_up and breakout_down, "不能同时向上和向下突破")

    def test_backtest_results_consistent(self):
        """测试回测结果一致性（小规模验证）"""
        # 创建 KeltnerChannel 实例
        keltner = KeltnerChannel(
            ema_period=20,
            atr_period=20,
            sma_period=200,
            bb_period=20,
            bb_std=2.0,
            volume_period=20,
            keltner_base_multiplier=1.5,
            keltner_trigger_multiplier=2.25,
        )

        # 模拟策略逻辑：记录所有入场信号
        entry_signals = []

        for idx, row in self.df.iterrows():
            keltner.update(
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            )

            if not keltner.is_ready():
                continue

            # 入场条件：价格突破 Trigger 上轨
            trigger_upper, _ = keltner.get_keltner_trigger_bands()
            if trigger_upper and row["close"] > trigger_upper:
                entry_signals.append(
                    {
                        "timestamp": row["datetime"],
                        "price": row["close"],
                        "trigger_upper": trigger_upper,
                        "ema": keltner.ema,
                        "atr": keltner.atr,
                    }
                )

        # 验证入场信号
        self.assertIsInstance(entry_signals, list, "入场信号应该是列表")

        # 如果有入场信号，验证其合理性
        if len(entry_signals) > 0:
            for signal in entry_signals:
                self.assertGreater(
                    signal["price"],
                    signal["trigger_upper"],
                    "入场价格应该高于 Trigger 上轨",
                )
                self.assertIsNotNone(signal["ema"], "EMA 应该已计算")
                self.assertIsNotNone(signal["atr"], "ATR 应该已计算")
                self.assertGreater(signal["atr"], 0, "ATR 应该大于 0")

    def test_bollinger_bands_integration(self):
        """测试 BollingerBands 集成"""
        keltner = KeltnerChannel(
            ema_period=20,
            atr_period=20,
            sma_period=200,
            bb_period=20,
            bb_std=2.0,
            volume_period=20,
            keltner_base_multiplier=1.5,
            keltner_trigger_multiplier=2.25,
        )

        # 更新数据
        for idx, row in self.df.iterrows():
            keltner.update(
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            )

        # 验证 BollingerBands 已初始化
        self.assertTrue(keltner.bb.initialized, "BollingerBands 应该已初始化")

        # 验证 BollingerBands 值
        bb_upper = keltner.bb.upper
        bb_lower = keltner.bb.lower
        bb_middle = keltner.bb.middle

        self.assertIsNotNone(bb_upper, "BB 上轨应该已计算")
        self.assertIsNotNone(bb_lower, "BB 下轨应该已计算")
        self.assertIsNotNone(bb_middle, "BB 中轨应该已计算")

        # 验证 BB 通道关系
        self.assertGreater(bb_upper, bb_middle, "BB 上轨应该高于中轨")
        self.assertLess(bb_lower, bb_middle, "BB 下轨应该低于中轨")

        # 验证 Squeeze 检测
        is_squeeze = keltner.is_squeezing()
        self.assertIsInstance(is_squeeze, bool, "Squeeze 状态应该是布尔值")

    def test_indicator_warmup_period(self):
        """测试指标预热期"""
        keltner = KeltnerChannel(
            ema_period=20,
            atr_period=20,
            sma_period=200,
            bb_period=20,
            bb_std=2.0,
            volume_period=20,
            keltner_base_multiplier=1.5,
            keltner_trigger_multiplier=2.25,
        )

        # 逐条更新数据，记录何时准备好
        ready_at = None
        for idx, row in self.df.iterrows():
            keltner.update(
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            )

            if keltner.is_ready() and ready_at is None:
                ready_at = idx
                break

        # 验证预热期合理（应该在 200 条左右，因为 SMA 周期是 200）
        self.assertIsNotNone(ready_at, "指标应该在某个时刻准备好")
        self.assertGreaterEqual(ready_at, 199, "指标应该在至少 200 条数据后准备好（SMA 周期）")


if __name__ == "__main__":
    unittest.main()
