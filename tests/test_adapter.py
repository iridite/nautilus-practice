"""
Tests for Config Adapter
"""
import unittest
from unittest.mock import Mock, patch

from core.adapter import ConfigAdapter


class TestConfigAdapter(unittest.TestCase):
    @patch('core.adapter.ConfigLoader')
    def setUp(self, mock_loader):
        self.adapter = ConfigAdapter()

    def test_initialization(self):
        self.assertIsNotNone(self.adapter.loader)

    @patch('core.adapter.ConfigLoader')
    def test_get_venue(self, mock_loader):
        adapter = ConfigAdapter()
        adapter.env_config = Mock()
        adapter.env_config.trading.venue = "BINANCE"
        self.assertEqual(adapter.get_venue(), "BINANCE")


if __name__ == "__main__":
    unittest.main()
