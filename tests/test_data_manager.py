"""
Tests for Data Manager
"""
import unittest
from pathlib import Path
from unittest.mock import patch

from utils.data_management.data_manager import DataManager


class TestDataManager(unittest.TestCase):
    def setUp(self):
        self.base_dir = Path("/tmp/test_data")
        self.manager = DataManager(self.base_dir)

    def test_initialization(self):
        self.assertEqual(self.manager.base_dir, self.base_dir)
        self.assertEqual(self.manager.data_dir, self.base_dir / "data" / "raw")

    @patch('utils.data_management.data_manager.check_single_data_file')
    def test_check_data_availability(self, mock_check):
        mock_check.return_value = (True, None)
        available, missing = self.manager.check_data_availability(
            ["BTCUSDT"], "2024-01-01", "2024-12-31", "1h", "binance"
        )
        self.assertEqual(len(available), 1)
        self.assertEqual(len(missing), 0)


if __name__ == "__main__":
    unittest.main()
