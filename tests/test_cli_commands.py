"""
测试 cli/commands 模块
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from cli.commands import (
    check_and_fetch_strategy_data,
    update_instrument_definitions,
)


class TestCliCommands(unittest.TestCase):
    """测试 CLI 命令"""

    def setUp(self):
        """初始化测试"""
        self.temp_dir = tempfile.mkdtemp()
        self.base_dir = Path(self.temp_dir)
        self.universe_symbols = {"BTCUSDT", "ETHUSDT"}

    def tearDown(self):
        """清理临时文件"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("cli.commands.logger")
    def test_check_and_fetch_strategy_data_skip_oi(self, mock_logger):
        """测试跳过 OI 数据检查"""
        args = MagicMock()
        args.skip_oi_data = True
        adapter = MagicMock()

        check_and_fetch_strategy_data(args, adapter, self.base_dir, self.universe_symbols)

        mock_logger.info.assert_called_with("⏩ Skipping OI/Funding data check")

    @patch("cli.commands.execute_oi_funding_data_fetch")
    @patch("cli.commands.check_strategy_data_dependencies")
    @patch("cli.commands.logger")
    def test_check_and_fetch_strategy_data_no_missing(
        self, mock_logger, mock_check_deps, mock_execute_fetch
    ):
        """测试没有缺失数据的情况"""
        args = MagicMock()
        args.skip_oi_data = False

        adapter = MagicMock()
        adapter.build_backtest_config.return_value = MagicMock(
            strategy=MagicMock(params=MagicMock())
        )
        adapter.get_start_date.return_value = "2025-01-01"
        adapter.get_end_date.return_value = "2025-01-31"

        mock_check_deps.return_value = {"missing_count": 0}

        check_and_fetch_strategy_data(args, adapter, self.base_dir, self.universe_symbols)

        mock_logger.info.assert_any_call("✅ All strategy data satisfied\n")
        mock_execute_fetch.assert_not_called()

    @patch("cli.commands.execute_oi_funding_data_fetch")
    @patch("cli.commands.check_strategy_data_dependencies")
    @patch("cli.commands.logger")
    def test_check_and_fetch_strategy_data_with_missing(
        self, mock_logger, mock_check_deps, mock_execute_fetch
    ):
        """测试有缺失数据的情况"""
        args = MagicMock()
        args.skip_oi_data = False
        args.oi_exchange = "binance"
        args.max_retries = 3

        adapter = MagicMock()
        adapter.build_backtest_config.return_value = MagicMock(
            strategy=MagicMock(params=MagicMock())
        )
        adapter.get_start_date.return_value = "2025-01-01"
        adapter.get_end_date.return_value = "2025-01-31"

        mock_check_deps.return_value = {"missing_count": 5}
        mock_execute_fetch.return_value = {"oi_files": 3, "funding_files": 2}

        check_and_fetch_strategy_data(args, adapter, self.base_dir, self.universe_symbols)

        mock_logger.info.assert_any_call("📊 5 missing data files")
        mock_logger.info.assert_any_call("✅ Downloaded 5 files")
        mock_execute_fetch.assert_called_once()

    @patch("cli.commands.update_instruments")
    @patch("cli.commands.parse_universe_symbols")
    @patch("cli.commands.logger")
    def test_update_instrument_definitions_with_universe(
        self, mock_logger, mock_parse_symbols, mock_update_instruments
    ):
        """测试更新 instrument 定义（包含 universe）"""
        adapter = MagicMock()

        # 模拟配置
        mock_instrument = MagicMock()
        mock_instrument.instrument_id = "BINANCE.BTCUSDT-SWAP"

        mock_feed = MagicMock()
        mock_feed.instrument_id = "BINANCE.ETHUSDT-SWAP"

        adapter.build_backtest_config.return_value = MagicMock(
            instrument=mock_instrument, data_feeds=[mock_feed]
        )

        adapter.get_venue.return_value = "BINANCE"
        adapter.env_config.trading.instrument_type = "SWAP"

        mock_parse_symbols.return_value = {"BINANCE.SOLUSDT-SWAP"}

        update_instrument_definitions(adapter, self.base_dir, self.universe_symbols)

        # 验证调用
        mock_parse_symbols.assert_called_once()
        mock_update_instruments.assert_called_once()

        # 验证传递的 instrument_ids 包含所有标的
        call_args = mock_update_instruments.call_args[0]
        instrument_ids = call_args[0]
        self.assertIn("BINANCE.BTCUSDT-SWAP", instrument_ids)
        self.assertIn("BINANCE.ETHUSDT-SWAP", instrument_ids)

    @patch("cli.commands.update_instruments")
    @patch("cli.commands.logger")
    def test_update_instrument_definitions_without_universe(
        self, mock_logger, mock_update_instruments
    ):
        """测试更新 instrument 定义（不包含 universe）"""
        adapter = MagicMock()

        mock_instrument = MagicMock()
        mock_instrument.instrument_id = "BINANCE.BTCUSDT-SWAP"

        adapter.build_backtest_config.return_value = MagicMock(
            instrument=mock_instrument, data_feeds=[]
        )

        update_instrument_definitions(adapter, self.base_dir, set())

        mock_update_instruments.assert_called_once()

    @patch("cli.commands.logger")
    def test_update_instrument_definitions_error_handling(self, mock_logger):
        """测试更新 instrument 定义时的错误处理"""
        adapter = MagicMock()
        adapter.build_backtest_config.side_effect = Exception("Test error")

        update_instrument_definitions(adapter, self.base_dir, self.universe_symbols)

        mock_logger.error.assert_called_once()
        self.assertIn("Error updating instruments", mock_logger.error.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
