"""
Tests for Keltner RS Breakout Strategy
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.test_kit.providers import TestInstrumentProvider

from strategy.keltner_rs_breakout import KeltnerRSBreakoutConfig, KeltnerRSBreakoutStrategy


class TestKeltnerRSBreakoutConfig(unittest.TestCase):
    def test_default_config(self):
        config = KeltnerRSBreakoutConfig()
        self.assertEqual(config.ema_period, 20)
        self.assertEqual(config.atr_period, 20)
        self.assertEqual(config.sma_period, 200)
        self.assertEqual(config.base_risk_pct, 0.01)

    def test_custom_config(self):
        config = KeltnerRSBreakoutConfig(
            symbol="ETHUSDT", timeframe="1h", ema_period=30, base_risk_pct=0.02
        )
        self.assertEqual(config.symbol, "ETHUSDT")
        self.assertEqual(config.ema_period, 30)
        self.assertEqual(config.base_risk_pct, 0.02)


class TestSymbolActiveCache(unittest.TestCase):
    """测试符号活跃缓存机制"""

    def setUp(self):
        """设置测试环境"""
        self.config = KeltnerRSBreakoutConfig(
            symbol="ETHUSDT",
            timeframe="1h",
            btc_symbol="BTCUSDT",
            instrument_id="ETHUSDT-PERP.BINANCE",
            bar_type="ETHUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL",
            btc_instrument_id="BTCUSDT-PERP.BINANCE",
            universe_top_n=15,
            universe_freq="ME",
        )

    @patch("strategy.keltner_rs_breakout.DynamicUniverseManager")
    @patch("strategy.keltner_rs_breakout.get_project_root")
    def test_parse_base_symbol_with_helper(self, mock_root, mock_universe_cls):
        """测试使用 instrument_helpers 解析 base symbol"""
        mock_root.return_value = Path("/tmp")
        mock_universe_file = Path("/tmp/data/universe/universe_15_ME.json")
        mock_universe_file.parent.mkdir(parents=True, exist_ok=True)
        mock_universe_file.write_text('{"2024-01": ["ETHUSDT", "BTCUSDT"]}')

        with patch("utils.instrument_helpers.parse_instrument_id") as mock_parse:
            mock_parse.return_value = ("ETH-USDT", "BINANCE", "PERP")

            strategy = KeltnerRSBreakoutStrategy(self.config)
            strategy.on_start()

            self.assertEqual(strategy._base_symbol, "ETHUSDT")
            mock_parse.assert_called_once()

        mock_universe_file.unlink(missing_ok=True)

    @patch("strategy.keltner_rs_breakout.DynamicUniverseManager")
    @patch("strategy.keltner_rs_breakout.get_project_root")
    def test_parse_base_symbol_fallback(self, mock_root, mock_universe_cls):
        """测试解析失败时的 fallback 逻辑"""
        mock_root.return_value = Path("/tmp")
        mock_universe_file = Path("/tmp/data/universe/universe_15_ME.json")
        mock_universe_file.parent.mkdir(parents=True, exist_ok=True)
        mock_universe_file.write_text('{"2024-01": ["ETHUSDT", "BTCUSDT"]}')

        with patch("utils.instrument_helpers.parse_instrument_id") as mock_parse:
            mock_parse.side_effect = Exception("Parse error")

            strategy = KeltnerRSBreakoutStrategy(self.config)
            strategy.on_start()

            self.assertEqual(strategy._base_symbol, "ETHUSDT")

        mock_universe_file.unlink(missing_ok=True)

    @patch("strategy.keltner_rs_breakout.get_project_root")
    def test_cache_initialization(self, mock_root):
        """测试缓存字段初始化"""
        mock_root.return_value = Path("/tmp")

        strategy = KeltnerRSBreakoutStrategy(self.config)

        self.assertIsNone(strategy._base_symbol)
        self.assertTrue(strategy._is_active_cache)
        self.assertIsNone(strategy._last_universe_period)

    @patch("strategy.keltner_rs_breakout.DynamicUniverseManager")
    @patch("strategy.keltner_rs_breakout.get_project_root")
    def test_update_active_cache_no_universe(self, mock_root, mock_universe_cls):
        """测试无 universe 管理器时缓存更新"""
        mock_root.return_value = Path("/tmp")

        config = KeltnerRSBreakoutConfig(
            symbol="ETHUSDT",
            timeframe="1h",
            btc_symbol="BTCUSDT",
            instrument_id="ETHUSDT-PERP.BINANCE",
            bar_type="ETHUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL",
            btc_instrument_id="BTCUSDT-PERP.BINANCE",
            universe_top_n=None,  # 无 universe
        )

        strategy = KeltnerRSBreakoutStrategy(config)
        strategy._update_active_cache(1000000)

        self.assertTrue(strategy._is_active_cache)
        self.assertIsNone(strategy._last_universe_period)

    @patch("strategy.keltner_rs_breakout.DynamicUniverseManager")
    @patch("strategy.keltner_rs_breakout.get_project_root")
    def test_update_active_cache_period_change(self, mock_root, mock_universe_cls):
        """测试周期变化时缓存更新"""
        mock_root.return_value = Path("/tmp")
        mock_universe_file = Path("/tmp/data/universe/universe_15_ME.json")
        mock_universe_file.parent.mkdir(parents=True, exist_ok=True)
        mock_universe_file.write_text('{"2024-01": ["ETHUSDT", "BTCUSDT"]}')

        mock_universe = MagicMock()
        mock_universe.get_current_period.side_effect = [202401, 202402]
        mock_universe.is_active.side_effect = [True, False]
        mock_universe_cls.return_value = mock_universe

        strategy = KeltnerRSBreakoutStrategy(self.config)
        strategy._base_symbol = "ETHUSDT"

        # 第一次更新
        strategy._update_active_cache(1000000)
        self.assertEqual(strategy._last_universe_period, 202401)
        self.assertTrue(strategy._is_active_cache)

        # 第二次更新（周期变化）
        strategy._update_active_cache(2000000)
        self.assertEqual(strategy._last_universe_period, 202402)
        self.assertFalse(strategy._is_active_cache)

        mock_universe_file.unlink(missing_ok=True)

    @patch("strategy.keltner_rs_breakout.DynamicUniverseManager")
    @patch("strategy.keltner_rs_breakout.get_project_root")
    def test_update_active_cache_no_period_change(self, mock_root, mock_universe_cls):
        """测试周期未变化时不更新缓存"""
        mock_root.return_value = Path("/tmp")
        mock_universe_file = Path("/tmp/data/universe/universe_15_ME.json")
        mock_universe_file.parent.mkdir(parents=True, exist_ok=True)
        mock_universe_file.write_text('{"2024-01": ["ETHUSDT", "BTCUSDT"]}')

        mock_universe = MagicMock()
        mock_universe.get_current_period.return_value = 202401
        mock_universe.is_active.return_value = True
        mock_universe_cls.return_value = mock_universe

        strategy = KeltnerRSBreakoutStrategy(self.config)
        strategy._base_symbol = "ETHUSDT"

        # 第一次更新
        strategy._update_active_cache(1000000)
        self.assertEqual(strategy._last_universe_period, 202401)
        self.assertTrue(strategy._is_active_cache)

        # 第二次更新（周期未变化）
        strategy._update_active_cache(1500000)
        self.assertEqual(strategy._last_universe_period, 202401)
        self.assertTrue(strategy._is_active_cache)

        # is_active 应该只被调用一次
        mock_universe.is_active.assert_called_once_with("ETHUSDT")

        mock_universe_file.unlink(missing_ok=True)

    @patch("strategy.keltner_rs_breakout.DynamicUniverseManager")
    @patch("strategy.keltner_rs_breakout.get_project_root")
    def test_is_symbol_active_uses_cache(self, mock_root, mock_universe_cls):
        """测试 _is_symbol_active 使用缓存"""
        mock_root.return_value = Path("/tmp")
        mock_universe_file = Path("/tmp/data/universe/universe_15_ME.json")
        mock_universe_file.parent.mkdir(parents=True, exist_ok=True)
        mock_universe_file.write_text('{"2024-01": ["ETHUSDT", "BTCUSDT"]}')

        mock_universe = MagicMock()
        mock_universe_cls.return_value = mock_universe

        strategy = KeltnerRSBreakoutStrategy(self.config)

        # 设置缓存值
        strategy._is_active_cache = False

        # 调用 _is_symbol_active 应该返回缓存值
        result = strategy._is_symbol_active()
        self.assertFalse(result)

        # universe_manager.is_active 不应该被调用
        mock_universe.is_active.assert_not_called()

        mock_universe_file.unlink(missing_ok=True)

    @patch("strategy.keltner_rs_breakout.DynamicUniverseManager")
    @patch("strategy.keltner_rs_breakout.get_project_root")
    def test_cache_integration_with_on_bar(self, mock_root, mock_universe_cls):
        """测试缓存与 on_bar 的集成"""
        mock_root.return_value = Path("/tmp")
        mock_universe_file = Path("/tmp/data/universe/universe_15_ME.json")
        mock_universe_file.parent.mkdir(parents=True, exist_ok=True)
        mock_universe_file.write_text('{"2024-01": ["ETHUSDT", "BTCUSDT"]}')

        mock_universe = MagicMock()
        mock_universe.get_current_period.side_effect = [202401, 202401, 202402]
        mock_universe.is_active.side_effect = [True, False]
        mock_universe_cls.return_value = mock_universe

        strategy = KeltnerRSBreakoutStrategy(self.config)
        strategy._base_symbol = "ETHUSDT"

        # 模拟 3 次 bar 更新
        strategy._update_active_cache(1000000)  # 周期 202401，缓存 True
        strategy._update_active_cache(1500000)  # 周期 202401，不更新
        strategy._update_active_cache(2000000)  # 周期 202402，缓存 False

        # is_active 应该只被调用 2 次（周期变化时）
        self.assertEqual(mock_universe.is_active.call_count, 2)
        self.assertFalse(strategy._is_active_cache)

        mock_universe_file.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
