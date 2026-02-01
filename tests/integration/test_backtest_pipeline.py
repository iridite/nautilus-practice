"""
回测流程集成测试

验证从配置到回测执行的完整流程（不实际运行回测）。
"""

import unittest
from pathlib import Path

from core import get_adapter


class TestBacktestPipeline(unittest.TestCase):
    """回测流程集成测试"""

    def setUp(self):
        """测试前准备"""
        self.base_dir = Path(__file__).parent.parent.parent
        self.adapter = get_adapter()
        self.cfg = self.adapter.build_backtest_config()

    def test_config_completeness(self):
        """测试配置完整性"""
        self.assertIsNotNone(self.cfg.instrument)
        self.assertIsNotNone(self.cfg.strategy)
        self.assertIsNotNone(self.cfg.start_date)
        self.assertIsNotNone(self.cfg.end_date)
        self.assertGreater(len(self.cfg.initial_balances), 0)

    def test_strategy_config_structure(self):
        """测试策略配置结构"""
        strategy = self.cfg.strategy

        self.assertIsNotNone(strategy.name)
        self.assertIsNotNone(strategy.module_path)
        self.assertIsNotNone(strategy.params)

    def test_instruments_consistency(self):
        """测试标的一致性"""
        self.assertGreater(len(self.cfg.instruments), 0)

        for inst in self.cfg.instruments:
            self.assertIsNotNone(inst.instrument_id)
            self.assertIsNotNone(inst.venue_name)
            self.assertIsNotNone(inst.quote_currency)
            self.assertIsNotNone(inst.base_currency)

    def test_data_feeds_consistency(self):
        """测试数据流一致性"""
        self.assertGreater(len(self.cfg.data_feeds), 0)

        labels = [f.label for f in self.cfg.data_feeds]
        self.assertIn("main", labels)

    def test_logging_config(self):
        """测试日志配置"""
        if self.cfg.logging:
            self.assertIsNotNone(self.cfg.logging.log_level)
            self.assertIsNotNone(self.cfg.logging.log_level_file)

    def test_date_range_validity(self):
        """测试日期范围有效性"""
        from datetime import datetime

        start_dt = datetime.strptime(self.cfg.start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(self.cfg.end_date, "%Y-%m-%d")

        self.assertLess(start_dt, end_dt)


if __name__ == "__main__":
    unittest.main()
