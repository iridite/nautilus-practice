"""
测试动态风险管理功能
"""

import unittest
from unittest.mock import MagicMock, patch
from decimal import Decimal

from strategy.keltner_rs_breakout import KeltnerRSBreakoutConfig, KeltnerRSBreakoutStrategy


class TestDynamicRiskManagement(unittest.TestCase):
    """测试动态风险管理"""

    def setUp(self):
        """设置测试环境"""
        self.config = KeltnerRSBreakoutConfig(
            instrument_id="BTCUSDT-PERP.BINANCE",
            bar_type="BTCUSDT-PERP.BINANCE-1-DAY-LAST-EXTERNAL",
            btc_instrument_id="BTCUSDT-PERP.BINANCE",
            enable_dynamic_risk=True,
            base_risk_pct=0.05,
            losing_streak_risk_pct=0.01,
            bear_market_risk_multiplier=0.5,
            recent_trades_window=3,
        )

    def test_config_has_dynamic_risk_params(self):
        """测试配置包含动态风险参数"""
        self.assertTrue(hasattr(self.config, "enable_dynamic_risk"))
        self.assertTrue(hasattr(self.config, "losing_streak_risk_pct"))
        self.assertTrue(hasattr(self.config, "bear_market_risk_multiplier"))
        self.assertTrue(hasattr(self.config, "recent_trades_window"))

    def test_config_default_values(self):
        """测试配置默认值"""
        self.assertTrue(self.config.enable_dynamic_risk)
        self.assertEqual(self.config.base_risk_pct, 0.05)
        self.assertEqual(self.config.losing_streak_risk_pct, 0.01)
        self.assertEqual(self.config.bear_market_risk_multiplier, 0.5)
        self.assertEqual(self.config.recent_trades_window, 3)

    @patch("strategy.keltner_rs_breakout.KeltnerRSBreakoutStrategy.get_market_regime")
    def test_normal_risk_no_trades(self, mock_regime):
        """测试正常情况下的风险 (无交易历史)"""
        mock_regime.return_value = "BULL"

        strategy = KeltnerRSBreakoutStrategy(self.config)
        strategy.recent_trades = []

        risk = strategy.get_dynamic_risk()
        self.assertEqual(risk, 0.05)  # 应该返回 base_risk_pct

    @patch("strategy.keltner_rs_breakout.KeltnerRSBreakoutStrategy.get_market_regime")
    def test_losing_streak_protection(self, mock_regime):
        """测试连败保护"""
        mock_regime.return_value = "BULL"

        strategy = KeltnerRSBreakoutStrategy(self.config)
        strategy.recent_trades = [-10.0, -5.0, -3.0]  # 3 连败

        risk = strategy.get_dynamic_risk()
        self.assertEqual(risk, 0.01)  # 应该降至 losing_streak_risk_pct

    @patch("strategy.keltner_rs_breakout.KeltnerRSBreakoutStrategy.get_market_regime")
    def test_bear_market_reduction(self, mock_regime):
        """测试熊市风险降低"""
        mock_regime.return_value = "BEAR"

        strategy = KeltnerRSBreakoutStrategy(self.config)
        strategy.recent_trades = [10.0, -5.0, 8.0]  # 有盈有亏

        risk = strategy.get_dynamic_risk()
        self.assertEqual(risk, 0.025)  # 应该减半: 0.05 * 0.5

    @patch("strategy.keltner_rs_breakout.KeltnerRSBreakoutStrategy.get_market_regime")
    def test_losing_streak_priority_over_bear(self, mock_regime):
        """测试连败保护优先级高于熊市降权"""
        mock_regime.return_value = "BEAR"

        strategy = KeltnerRSBreakoutStrategy(self.config)
        strategy.recent_trades = [-10.0, -5.0, -3.0]  # 3 连败 + 熊市

        risk = strategy.get_dynamic_risk()
        self.assertEqual(risk, 0.01)  # 应该使用连败保护 (更严格)

    @patch("strategy.keltner_rs_breakout.KeltnerRSBreakoutStrategy.get_market_regime")
    def test_mixed_trades_no_protection(self, mock_regime):
        """测试有盈有亏的情况不触发连败保护"""
        mock_regime.return_value = "BULL"

        strategy = KeltnerRSBreakoutStrategy(self.config)
        strategy.recent_trades = [10.0, -5.0, -3.0]  # 有盈有亏

        risk = strategy.get_dynamic_risk()
        self.assertEqual(risk, 0.05)  # 应该返回正常风险

    @patch("strategy.keltner_rs_breakout.KeltnerRSBreakoutStrategy.get_market_regime")
    def test_insufficient_trades_no_protection(self, mock_regime):
        """测试交易数量不足时不触发连败保护"""
        mock_regime.return_value = "BULL"

        strategy = KeltnerRSBreakoutStrategy(self.config)
        strategy.recent_trades = [-10.0, -5.0]  # 只有 2 笔

        risk = strategy.get_dynamic_risk()
        self.assertEqual(risk, 0.05)  # 应该返回正常风险

    def test_disabled_dynamic_risk(self):
        """测试禁用动态风险管理"""
        config = KeltnerRSBreakoutConfig(
            instrument_id="BTCUSDT-PERP.BINANCE",
            bar_type="BTCUSDT-PERP.BINANCE-1-DAY-LAST-EXTERNAL",
            btc_instrument_id="BTCUSDT-PERP.BINANCE",
            enable_dynamic_risk=False,
            base_risk_pct=0.05,
        )

        strategy = KeltnerRSBreakoutStrategy(config)
        strategy.recent_trades = [-10.0, -5.0, -3.0]  # 3 连败

        risk = strategy.get_dynamic_risk()
        self.assertEqual(risk, 0.05)  # 禁用后应该返回 base_risk_pct

    @patch("strategy.keltner_rs_breakout.KeltnerRSBreakoutStrategy.get_market_regime")
    def test_choppy_market_normal_risk(self, mock_regime):
        """测试震荡市场使用正常风险 (震荡市场已被过滤,不会进入交易)"""
        mock_regime.return_value = "CHOPPY"

        strategy = KeltnerRSBreakoutStrategy(self.config)
        strategy.recent_trades = []

        risk = strategy.get_dynamic_risk()
        self.assertEqual(risk, 0.05)  # CHOPPY 不影响风险计算


if __name__ == "__main__":
    unittest.main()
