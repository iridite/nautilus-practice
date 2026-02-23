"""
数据流集成测试

验证数据获取、验证和加载的完整流程。
"""

import unittest
from pathlib import Path

from core import get_adapter
from utils.data_file_checker import check_single_data_file


class TestDataFlowIntegration(unittest.TestCase):
    """数据流集成测试"""

    @classmethod
    def setUpClass(cls):
        """检查 universe 文件是否存在"""
        adapter = get_adapter()
        params = adapter.strategy_config.parameters
        universe_top_n = params.get("universe_top_n", 15)
        universe_freq = params.get("universe_freq", "W-MON")
        universe_file = Path(f"data/universe/universe_{universe_top_n}_{universe_freq}.json")

        if not universe_file.exists():
            raise unittest.SkipTest(f"Universe 文件不存在: {universe_file}")

    def setUp(self):
        """测试前准备"""
        self.base_dir = Path(__file__).parent.parent.parent
        self.adapter = get_adapter()
        self.cfg = self.adapter.build_backtest_config()

    def test_config_to_data_feeds(self):
        """测试配置到数据流的转换"""
        self.assertGreater(len(self.cfg.data_feeds), 0)

        for feed in self.cfg.data_feeds:
            self.assertIsNotNone(feed.csv_file_name)
            self.assertIsNotNone(feed.bar_aggregation)
            self.assertIsNotNone(feed.bar_period)
            self.assertIsNotNone(feed.label)

    def test_data_config_path_generation(self):
        """测试数据配置路径生成"""
        for feed in self.cfg.data_feeds:
            full_path = feed.full_path
            self.assertIsInstance(full_path, Path)
            self.assertTrue(str(full_path).endswith(".csv"))

    def test_data_validation_integration(self):
        """测试数据验证集成"""
        venue = self.adapter.get_venue().lower()
        start_date = self.adapter.get_start_date()
        end_date = self.adapter.get_end_date()

        for feed in self.cfg.data_feeds[:1]:
            symbol = feed.csv_file_name.split("/")[0]
            timeframe = f"{feed.bar_period}{'h' if feed.bar_aggregation.name == 'HOUR' else 'm'}"

            exists, _ = check_single_data_file(
                symbol, start_date, end_date, timeframe, venue, self.base_dir
            )

            self.assertIsInstance(exists, bool)

    def test_instrument_to_data_feed_mapping(self):
        """测试标的到数据流的映射"""
        instrument_ids = {inst.instrument_id for inst in self.cfg.instruments}

        bound_feeds = [f for f in self.cfg.data_feeds if f.instrument_id]

        for feed in bound_feeds:
            self.assertIn(feed.instrument_id, instrument_ids)


if __name__ == "__main__":
    unittest.main()
