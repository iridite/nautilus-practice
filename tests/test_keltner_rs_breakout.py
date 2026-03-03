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

        with patch("utils.instrument_helpers.parse_instrument_id") as mock_parse:
            mock_parse.return_value = ("ETH-USDT", "BINANCE", "PERP")

            strategy = KeltnerRSBreakoutStrategy(self.config)
            strategy._parse_base_symbol()

            self.assertEqual(strategy._base_symbol, "ETHUSDT")
            mock_parse.assert_called_once()

    @patch("strategy.keltner_rs_breakout.DynamicUniverseManager")
    @patch("strategy.keltner_rs_breakout.get_project_root")
    def test_parse_base_symbol_fallback(self, mock_root, mock_universe_cls):
        """测试解析失败时的 fallback 逻辑"""
        mock_root.return_value = Path("/tmp")

        with patch("utils.instrument_helpers.parse_instrument_id") as mock_parse:
            mock_parse.side_effect = Exception("Parse error")

            strategy = KeltnerRSBreakoutStrategy(self.config)
            strategy._parse_base_symbol()

            self.assertEqual(strategy._base_symbol, "ETHUSDT")

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
        mock_universe.update.side_effect = [True, True]  # 周期变化返回 True
        mock_universe.get_current_period.side_effect = ["2024-01", "2024-02"]
        mock_universe.is_active.side_effect = [True, False]
        mock_universe_cls.return_value = mock_universe

        strategy = KeltnerRSBreakoutStrategy(self.config)
        strategy._base_symbol = "ETHUSDT"

        # 第一次更新
        strategy._update_active_cache(1000000)
        self.assertEqual(strategy._last_universe_period, "2024-01")
        self.assertTrue(strategy._is_active_cache)

        # 第二次更新（周期变化）
        strategy._update_active_cache(2000000)
        self.assertEqual(strategy._last_universe_period, "2024-02")
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
        mock_universe.update.side_effect = [True, False]  # 第一次变化，第二次不变化
        mock_universe.get_current_period.return_value = "2024-01"
        mock_universe.is_active.return_value = True
        mock_universe_cls.return_value = mock_universe

        strategy = KeltnerRSBreakoutStrategy(self.config)
        strategy._base_symbol = "ETHUSDT"

        # 第一次更新
        strategy._update_active_cache(1000000)
        self.assertEqual(strategy._last_universe_period, "2024-01")
        self.assertTrue(strategy._is_active_cache)

        # 第二次更新（周期未变化）
        strategy._update_active_cache(1500000)
        self.assertEqual(strategy._last_universe_period, "2024-01")
        self.assertTrue(strategy._is_active_cache)

        # is_active 应该只被调用一次（因为第二次 update 返回 False）
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
        # update() 返回值：True 表示周期变化，False 表示周期未变化
        mock_universe.update.side_effect = [True, False, True]
        mock_universe.get_current_period.side_effect = ["2024-01", "2024-02"]
        mock_universe.is_active.side_effect = [True, False]
        mock_universe_cls.return_value = mock_universe

        strategy = KeltnerRSBreakoutStrategy(self.config)
        strategy._base_symbol = "ETHUSDT"

        # 模拟 3 次 bar 更新
        strategy._update_active_cache(1000000)  # 周期变化，缓存 True
        strategy._update_active_cache(1500000)  # 周期未变化，不更新
        strategy._update_active_cache(2000000)  # 周期变化，缓存 False

        # is_active 应该只被调用 2 次（周期变化时）
        self.assertEqual(mock_universe.is_active.call_count, 2)
        self.assertFalse(strategy._is_active_cache)

        mock_universe_file.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()

class TestSmallCapitalOptimizations(unittest.TestCase):
    """测试 100U 小资金优化功能"""

    def setUp(self):
        """设置测试环境"""
        self.config = KeltnerRSBreakoutConfig(
            symbol="ETHUSDT",
            timeframe="1h",
            btc_symbol="BTCUSDT",
            instrument_id="ETHUSDT-PERP.BINANCE",
            bar_type="ETHUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL",
            btc_instrument_id="BTCUSDT-PERP.BINANCE",
            universe_top_n=2,
            max_positions=2,
            enable_chop_filter=True,
            chop_threshold=60.0,
            chop_period=14,
            enable_breakeven_stop=True,
            breakeven_trigger_atr=1.5,
            breakeven_offset_pct=0.005,
        )

    @patch("strategy.keltner_rs_breakout.DynamicUniverseManager")
    @patch("strategy.keltner_rs_breakout.get_project_root")
    def test_chop_filter_blocks_choppy_market(self, mock_root, mock_universe_cls):
        """测试 CHOP 过滤器在震荡市场中阻止开仓"""
        mock_root.return_value = Path("/tmp")
        mock_universe_file = Path("/tmp/data/universe/universe_2_ME.json")
        mock_universe_file.parent.mkdir(parents=True, exist_ok=True)
        mock_universe_file.write_text('{"2024-01": ["ETHUSDT", "BTCUSDT"]}')

        mock_universe = MagicMock()
        mock_universe_cls.return_value = mock_universe

        strategy = KeltnerRSBreakoutStrategy(self.config)
        strategy._base_symbol = "ETHUSDT"
        strategy._is_active_cache = True

        # Mock instrument
        mock_instrument = Mock()
        mock_instrument.id.symbol.value = "ETHUSDT"
        strategy.instrument = mock_instrument

        # Mock CHOP 指标（震荡市场）
        mock_chop = Mock()
        mock_chop.initialized = True
        mock_chop.value = 65.0  # > threshold (60)
        strategy.chop = mock_chop

        # Mock Keltner 指标
        mock_keltner = Mock()
        mock_keltner.sma = 100.0
        mock_keltner.atr = 5.0
        strategy.keltner = mock_keltner

        # 创建模拟 Bar
        mock_bar = Mock()
        mock_bar.close = 105.0
        mock_bar.volume = 1000.0
        mock_bar.instrument_id.symbol.value = "ETHUSDT"

        # 调用入场条件检查
        result = strategy._check_entry_conditions(mock_bar)

        # 应该被 CHOP 过滤器拦截
        self.assertFalse(result)
        self.assertEqual(strategy.filter_stats["chop_blocked"], 1)

        mock_universe_file.unlink(missing_ok=True)

    @patch("strategy.keltner_rs_breakout.DynamicUniverseManager")
    @patch("strategy.keltner_rs_breakout.get_project_root")
    def test_chop_filter_allows_trending_market(self, mock_root, mock_universe_cls):
        """测试 CHOP 过滤器在趋势市场中允许开仓"""
        mock_root.return_value = Path("/tmp")
        mock_universe_file = Path("/tmp/data/universe/universe_2_ME.json")
        mock_universe_file.parent.mkdir(parents=True, exist_ok=True)
        mock_universe_file.write_text('{"2024-01": ["ETHUSDT", "BTCUSDT"]}')

        mock_universe = MagicMock()
        mock_universe_cls.return_value = mock_universe

        strategy = KeltnerRSBreakoutStrategy(self.config)
        strategy._base_symbol = "ETHUSDT"
        strategy._is_active_cache = True

        # Mock CHOP 指标（趋势市场）
        mock_chop = Mock()
        mock_chop.initialized = True
        mock_chop.value = 45.0  # < threshold (60)
        strategy.chop = mock_chop

        # CHOP 过滤器不应该拦截
        self.assertEqual(strategy.filter_stats["chop_blocked"], 0)

        mock_universe_file.unlink(missing_ok=True)

    @patch("strategy.keltner_rs_breakout.DynamicUniverseManager")
    @patch("strategy.keltner_rs_breakout.get_project_root")
    def test_breakeven_stop_activation(self, mock_root, mock_universe_cls):
        """测试保本止损在价格移动 1.5*ATR 后激活"""
        from decimal import Decimal

        mock_root.return_value = Path("/tmp")
        mock_universe_file = Path("/tmp/data/universe/universe_2_ME.json")
        mock_universe_file.parent.mkdir(parents=True, exist_ok=True)
        mock_universe_file.write_text('{"2024-01": ["ETHUSDT", "BTCUSDT"]}')

        mock_universe = MagicMock()
        mock_universe_cls.return_value = mock_universe

        # 创建配置，设置 stop_loss_atr_multiplier
        config = KeltnerRSBreakoutConfig(
            symbol="ETHUSDT",
            timeframe="1h",
            btc_symbol="BTCUSDT",
            instrument_id="ETHUSDT-PERP.BINANCE",
            bar_type="ETHUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL",
            btc_instrument_id="BTCUSDT-PERP.BINANCE",
            stop_loss_atr_multiplier=2.0,
            breakeven_trigger_atr=1.5,
            breakeven_offset_pct=0.005,
        )

        strategy = KeltnerRSBreakoutStrategy(config)

        # 设置入场价格和 ATR
        strategy.entry_price = Decimal("100.0")

        # Mock Keltner 指标
        mock_keltner = Mock()
        mock_keltner.atr = 5.0  # ATR = 5
        strategy.keltner = mock_keltner

        # 初始止损线
        strategy.trailing_stop = 90.0  # 100 - 2*5 = 90

        # 模拟价格移动到 107.5（entry + 1.5*ATR）
        strategy.highest_high = 107.5

        # 创建模拟 Bar
        mock_bar = Mock()
        mock_bar.high = 107.5
        mock_bar.close = 107.0

        # 调用持仓管理
        strategy._handle_long_position_management(mock_bar)

        # 保本止损应该被激活：entry * (1 + 0.005) = 100.5
        expected_breakeven = 100.0 * 1.005
        self.assertGreaterEqual(strategy.trailing_stop, expected_breakeven)

        mock_universe_file.unlink(missing_ok=True)

    @patch("strategy.keltner_rs_breakout.DynamicUniverseManager")
    @patch("strategy.keltner_rs_breakout.get_project_root")
    def test_breakeven_stop_not_activated_early(self, mock_root, mock_universe_cls):
        """测试保本止损在价格未达到 1.5*ATR 时不激活"""
        from decimal import Decimal

        mock_root.return_value = Path("/tmp")
        mock_universe_file = Path("/tmp/data/universe/universe_2_ME.json")
        mock_universe_file.parent.mkdir(parents=True, exist_ok=True)
        mock_universe_file.write_text('{"2024-01": ["ETHUSDT", "BTCUSDT"]}')

        mock_universe = MagicMock()
        mock_universe_cls.return_value = mock_universe

        # 创建配置
        config = KeltnerRSBreakoutConfig(
            symbol="ETHUSDT",
            timeframe="1h",
            btc_symbol="BTCUSDT",
            instrument_id="ETHUSDT-PERP.BINANCE",
            bar_type="ETHUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL",
            btc_instrument_id="BTCUSDT-PERP.BINANCE",
            stop_loss_atr_multiplier=2.0,
            breakeven_trigger_atr=1.5,
            breakeven_offset_pct=0.005,
        )

        strategy = KeltnerRSBreakoutStrategy(config)

        # 设置入场价格和 ATR
        strategy.entry_price = Decimal("100.0")

        # Mock Keltner 指标
        mock_keltner = Mock()
        mock_keltner.atr = 5.0
        strategy.keltner = mock_keltner

        # 初始止损线
        strategy.trailing_stop = 90.0

        # 模拟价格只移动到 105（< entry + 1.5*ATR = 107.5）
        strategy.highest_high = 105.0

        # 创建模拟 Bar
        mock_bar = Mock()
        mock_bar.high = 105.0
        mock_bar.close = 104.5

        # 调用持仓管理
        strategy._handle_long_position_management(mock_bar)

        # 保本止损不应该被激活，止损线应该保持原样或按 Chandelier 更新
        # Chandelier: 105 - 2*5 = 95
        self.assertEqual(strategy.trailing_stop, 95.0)

        mock_universe_file.unlink(missing_ok=True)
