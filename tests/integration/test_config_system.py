"""
配置系统集成测试

验证配置系统的完整工作流程。
"""

import unittest

from core import (
    BacktestConfig,
    ConfigAdapter,
    get_adapter,
)


class TestConfigSystemIntegration(unittest.TestCase):
    """配置系统集成测试"""

    def setUp(self):
        """测试前准备"""
        self.adapter = get_adapter()

    def test_config_adapter_initialization(self):
        """测试配置适配器初始化"""
        self.assertIsInstance(self.adapter, ConfigAdapter)
        self.assertIsNotNone(self.adapter.active_config)
        self.assertIsNotNone(self.adapter.env_config)
        self.assertIsNotNone(self.adapter.strategy_config)

    def test_config_access_functions(self):
        """测试配置访问函数"""
        venue = self.adapter.get_venue()
        self.assertIsInstance(venue, str)
        self.assertIn(venue.upper(), ["BINANCE", "OKX"])

        start_date = self.adapter.get_start_date()
        self.assertIsInstance(start_date, str)
        self.assertRegex(start_date, r"\d{4}-\d{2}-\d{2}")

        end_date = self.adapter.get_end_date()
        self.assertIsInstance(end_date, str)
        self.assertRegex(end_date, r"\d{4}-\d{2}-\d{2}")

    def test_build_backtest_config(self):
        """测试回测配置构建"""
        cfg = self.adapter.build_backtest_config()

        self.assertIsInstance(cfg, BacktestConfig)
        self.assertIsNotNone(cfg.strategy)
        self.assertIsNotNone(cfg.instrument)
        self.assertGreater(len(cfg.instruments), 0)
        self.assertGreater(len(cfg.data_feeds), 0)
        self.assertIsNotNone(cfg.start_date)
        self.assertIsNotNone(cfg.end_date)
        self.assertGreater(len(cfg.initial_balances), 0)

    def test_config_list_functions(self):
        """测试配置列表函数"""
        envs = self.adapter.loader.paths.list_environments()
        self.assertIsInstance(envs, list)
        self.assertGreater(len(envs), 0)
        self.assertIn("prod", envs)

        strategies = self.adapter.loader.paths.list_strategies()
        self.assertIsInstance(strategies, list)
        self.assertGreater(len(strategies), 0)

    def test_config_reload(self):
        """测试配置重载"""
        original_venue = self.adapter.get_venue()

        self.adapter.reload()

        new_venue = self.adapter.get_venue()
        self.assertEqual(original_venue, new_venue)

    def test_backtest_config_consistency(self):
        """测试回测配置一致性"""
        cfg = self.adapter.build_backtest_config()

        self.assertEqual(cfg.start_date, self.adapter.get_start_date())
        self.assertEqual(cfg.end_date, self.adapter.get_end_date())

        for inst in cfg.instruments:
            self.assertEqual(inst.venue_name, self.adapter.get_venue())

    def test_data_feeds_instrument_binding(self):
        """测试数据流与标的绑定"""
        cfg = self.adapter.build_backtest_config()

        instrument_ids = {inst.instrument_id for inst in cfg.instruments}

        for feed in cfg.data_feeds:
            if feed.instrument_id:
                self.assertIn(feed.instrument_id, instrument_ids)


if __name__ == "__main__":
    unittest.main()
