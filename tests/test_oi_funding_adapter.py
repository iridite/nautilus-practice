"""
测试 OI 和 Funding Rate 数据适配器
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pandas as pd

from utils.oi_funding_adapter import OIFundingDataLoader


class TestOIFundingDataLoader(unittest.TestCase):
    """测试 OI 和 Funding Rate 数据加载器"""

    def setUp(self):
        """设置测试环境"""
        self.base_dir = Path("/tmp/test_data")
        self.loader = OIFundingDataLoader(self.base_dir)

    def test_init(self):
        """测试初始化"""
        self.assertEqual(self.loader.base_dir, self.base_dir)
        self.assertEqual(self.loader.data_dir, self.base_dir / "data" / "raw")

    def test_find_available_oi_files_no_directory(self):
        """测试查找 OI 文件（目录不存在）"""
        with patch.object(Path, "exists", return_value=False):
            files = self.loader._find_available_oi_files("BTCUSDT", "binance")
            self.assertEqual(files, [])

    def test_find_available_oi_files_with_files(self):
        """测试查找 OI 文件（有文件）"""
        mock_files = [
            Path("/tmp/test_data/data/raw/BTCUSDT/binance-BTCUSDT-oi-1h.csv"),
            Path("/tmp/test_data/data/raw/BTCUSDT/binance-BTCUSDT-oi-4h.csv"),
        ]

        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "glob", return_value=mock_files):
                files = self.loader._find_available_oi_files("BTCUSDT", "binance")
                self.assertEqual(len(files), 2)

    def test_find_available_funding_files_no_directory(self):
        """测试查找 Funding Rate 文件（目录不存在）"""
        with patch.object(Path, "exists", return_value=False):
            files = self.loader._find_available_funding_files("BTCUSDT", "binance")
            self.assertEqual(files, [])

    def test_find_available_funding_files_with_files(self):
        """测试查找 Funding Rate 文件（有文件）"""
        mock_files = [
            Path(
                "/tmp/test_data/data/raw/BTCUSDT/binance-BTCUSDT-funding-2024-01-01_2024-01-10.csv"
            ),
        ]

        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "glob", return_value=mock_files):
                files = self.loader._find_available_funding_files("BTCUSDT", "binance")
                self.assertEqual(len(files), 1)

    @patch("utils.oi_funding_adapter.logger")
    def test_load_oi_data_file_not_found(self, mock_logger):
        """测试加载 OI 数据（文件不存在）"""
        instrument_id = MagicMock()

        with patch.object(Path, "exists", return_value=False):
            with patch.object(self.loader, "_find_available_oi_files", return_value=[]):
                result = self.loader.load_oi_data(
                    "BTCUSDT", instrument_id, "2024-01-01", "2024-01-10"
                )

                self.assertEqual(result, [])
                mock_logger.warning.assert_called()

    @patch("utils.oi_funding_adapter.logger")
    @patch("pandas.read_csv")
    def test_load_oi_data_invalid_format(self, mock_read_csv, mock_logger):
        """测试加载 OI 数据（格式无效）"""
        instrument_id = MagicMock()

        # 模拟缺少必需列的 DataFrame
        mock_df = pd.DataFrame({"invalid_column": [1, 2, 3]})
        mock_read_csv.return_value = mock_df

        with patch.object(Path, "exists", return_value=True):
            result = self.loader.load_oi_data("BTCUSDT", instrument_id, "2024-01-01", "2024-01-10")

            self.assertEqual(result, [])
            mock_logger.warning.assert_called()

    @patch("utils.oi_funding_adapter.logger")
    @patch("pandas.read_csv")
    def test_load_oi_data_success(self, mock_read_csv, mock_logger):
        """测试成功加载 OI 数据"""
        instrument_id = MagicMock()

        # 模拟有效的 DataFrame
        mock_df = pd.DataFrame(
            {"timestamp": [1704067200000, 1704070800000], "open_interest": [1000.0, 1100.0]}
        )
        mock_read_csv.return_value = mock_df

        with patch.object(Path, "exists", return_value=True):
            result = self.loader.load_oi_data("BTCUSDT", instrument_id, "2024-01-01", "2024-01-10")

            self.assertEqual(len(result), 2)
            mock_logger.info.assert_called()

    @patch("utils.oi_funding_adapter.logger")
    @patch("pandas.read_csv")
    def test_load_oi_data_exception(self, mock_read_csv, mock_logger):
        """测试加载 OI 数据时发生异常"""
        instrument_id = MagicMock()

        mock_read_csv.side_effect = Exception("Read error")

        with patch.object(Path, "exists", return_value=True):
            result = self.loader.load_oi_data("BTCUSDT", instrument_id, "2024-01-01", "2024-01-10")

            self.assertEqual(result, [])
            mock_logger.error.assert_called()

    @patch("utils.oi_funding_adapter.logger")
    def test_load_funding_data_file_not_found(self, mock_logger):
        """测试加载 Funding Rate 数据（文件不存在）"""
        instrument_id = MagicMock()

        with patch.object(Path, "exists", return_value=False):
            with patch.object(self.loader, "_find_available_funding_files", return_value=[]):
                result = self.loader.load_funding_data(
                    "BTCUSDT", instrument_id, "2024-01-01", "2024-01-10"
                )

                self.assertEqual(result, [])
                mock_logger.warning.assert_called()

    @patch("utils.oi_funding_adapter.logger")
    @patch("pandas.read_csv")
    def test_load_funding_data_invalid_format(self, mock_read_csv, mock_logger):
        """测试加载 Funding Rate 数据（格式无效）"""
        instrument_id = MagicMock()

        # 模拟缺少必需列的 DataFrame
        mock_df = pd.DataFrame({"invalid_column": [1, 2, 3]})
        mock_read_csv.return_value = mock_df

        with patch.object(Path, "exists", return_value=True):
            result = self.loader.load_funding_data(
                "BTCUSDT", instrument_id, "2024-01-01", "2024-01-10"
            )

            self.assertEqual(result, [])
            mock_logger.warning.assert_called()

    @patch("pandas.read_csv")
    def test_load_funding_data_success(self, mock_read_csv):
        """测试成功加载 Funding Rate 数据"""
        instrument_id = MagicMock()

        # 模拟有效的 DataFrame
        mock_df = pd.DataFrame(
            {"timestamp": [1704067200000, 1704070800000], "funding_rate": [0.0001, 0.00015]}
        )
        mock_read_csv.return_value = mock_df

        with patch.object(Path, "exists", return_value=True):
            result = self.loader.load_funding_data(
                "BTCUSDT", instrument_id, "2024-01-01", "2024-01-10"
            )

            self.assertEqual(len(result), 2)

    @patch("utils.oi_funding_adapter.logger")
    @patch("pandas.read_csv")
    def test_load_funding_data_exception(self, mock_read_csv, mock_logger):
        """测试加载 Funding Rate 数据时发生异常"""
        instrument_id = MagicMock()

        mock_read_csv.side_effect = Exception("Read error")

        with patch.object(Path, "exists", return_value=True):
            result = self.loader.load_funding_data(
                "BTCUSDT", instrument_id, "2024-01-01", "2024-01-10"
            )

            self.assertEqual(result, [])
            mock_logger.error.assert_called()

    def test_symbol_with_slash(self):
        """测试处理带斜杠的符号"""
        with patch.object(Path, "exists", return_value=False):
            files = self.loader._find_available_oi_files("BTC/USDT", "binance")
            # 应该将 / 替换为空字符串
            self.assertEqual(files, [])


if __name__ == "__main__":
    unittest.main()
