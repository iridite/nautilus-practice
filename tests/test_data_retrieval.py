"""
测试 data_retrieval.py 模块

测试数据获取功能，包括 OHLCV、OI 和 Funding Rate 数据。
使用 mock 避免实际的网络请求。
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call
import pandas as pd
import tempfile
import shutil

from utils.data_management.data_retrieval import (
    fetch_ohlcv_data,
    _fetch_ohlcv_ccxt,
    batch_fetch_ohlcv,
    fetch_binance_oi_history,
    fetch_okx_oi_history,
    fetch_binance_funding_rate_history,
    fetch_okx_funding_rate_history,
    batch_fetch_oi_and_funding,
)


class TestFetchOHLCVData(unittest.TestCase):
    """测试 fetch_ohlcv_data 函数"""

    def setUp(self):
        self.mock_exchange = Mock()
        self.mock_exchange.id = "binance"
        self.mock_exchange.rateLimit = 100

    @patch("utils.data_management.data_retrieval._fetch_ohlcv_ccxt")
    def test_fetch_ohlcv_auto_success(self, mock_ccxt):
        """测试 auto 模式成功获取数据"""
        expected_df = pd.DataFrame(
            {
                "timestamp": [1000, 2000],
                "open": [100, 101],
                "high": [102, 103],
                "low": [99, 100],
                "close": [101, 102],
                "volume": [1000, 1100],
            }
        )
        mock_ccxt.return_value = expected_df

        result = fetch_ohlcv_data(self.mock_exchange, "BTC/USDT", "1h", 1000, 3000, source="auto")

        pd.testing.assert_frame_equal(result, expected_df)
        mock_ccxt.assert_called_once_with(self.mock_exchange, "BTC/USDT", "1h", 1000, 3000)

    @patch("utils.data_management.data_fetcher.DataFetcher")
    @patch("utils.data_management.data_retrieval._fetch_ohlcv_ccxt")
    def test_fetch_ohlcv_auto_fallback(self, mock_ccxt, mock_fetcher_class):
        """测试 auto 模式在 CCXT 失败时回退到 DataFetcher"""
        mock_ccxt.side_effect = ConnectionError("Network error")

        mock_fetcher = Mock()
        mock_fetcher_class.return_value = mock_fetcher

        fallback_df = pd.DataFrame(
            {
                "timestamp": [1000, 2000, 3500],
                "open": [100, 101, 102],
                "high": [102, 103, 104],
                "low": [99, 100, 101],
                "close": [101, 102, 103],
                "volume": [1000, 1100, 1200],
            }
        )
        mock_fetcher.fetch_ohlcv.return_value = fallback_df

        result = fetch_ohlcv_data(self.mock_exchange, "BTC/USDT", "1h", 1000, 3000, source="auto")

        # 应该过滤掉 timestamp >= 3000 的数据
        expected_df = fallback_df[fallback_df["timestamp"] < 3000]
        pd.testing.assert_frame_equal(result, expected_df)

    @patch("utils.data_management.data_retrieval._fetch_ohlcv_ccxt")
    def test_fetch_ohlcv_ccxt_direct(self, mock_ccxt):
        """测试直接使用 CCXT 源"""
        expected_df = pd.DataFrame(
            {
                "timestamp": [1000],
                "open": [100],
                "high": [102],
                "low": [99],
                "close": [101],
                "volume": [1000],
            }
        )
        mock_ccxt.return_value = expected_df

        result = fetch_ohlcv_data(self.mock_exchange, "BTC/USDT", "1h", 1000, 3000, source="ccxt")

        pd.testing.assert_frame_equal(result, expected_df)


class TestFetchOHLCVCCXT(unittest.TestCase):
    """测试 _fetch_ohlcv_ccxt 函数"""

    def setUp(self):
        self.mock_exchange = Mock()
        self.mock_exchange.id = "binance"
        self.mock_exchange.rateLimit = 100

    @patch("utils.data_management.data_retrieval.retry_fetch")
    @patch("time.sleep")
    def test_fetch_single_batch(self, mock_sleep, mock_retry):
        """测试单批次数据获取"""
        # 第一次调用返回数据，第二次返回空（结束循环）
        mock_retry.side_effect = [
            [
                [1000, 100, 102, 99, 101, 1000],
                [2000, 101, 103, 100, 102, 1100],
            ],
            [],  # 第二次调用返回空，结束循环
        ]

        result = _fetch_ohlcv_ccxt(self.mock_exchange, "BTC/USDT", "1h", 1000, 3000)

        self.assertEqual(len(result), 2)
        self.assertEqual(result["timestamp"].tolist(), [1000, 2000])

    @patch("utils.data_management.data_retrieval.retry_fetch")
    @patch("time.sleep")
    def test_fetch_multiple_batches(self, mock_sleep, mock_retry):
        """测试多批次数据获取"""
        mock_retry.side_effect = [
            [[1000, 100, 102, 99, 101, 1000]],
            [[2000, 101, 103, 100, 102, 1100]],
            [],  # 结束
        ]

        result = _fetch_ohlcv_ccxt(self.mock_exchange, "BTC/USDT", "1h", 1000, 3000)

        self.assertEqual(len(result), 2)
        self.assertEqual(mock_retry.call_count, 3)

    @patch("utils.data_management.data_retrieval.retry_fetch")
    def test_fetch_empty_result(self, mock_retry):
        """测试空结果"""
        mock_retry.return_value = []

        result = _fetch_ohlcv_ccxt(self.mock_exchange, "BTC/USDT", "1h", 1000, 3000)

        self.assertTrue(result.empty)

    @patch("utils.data_management.data_retrieval.retry_fetch")
    @patch("time.sleep")
    def test_fetch_filters_future_data(self, mock_sleep, mock_retry):
        """测试过滤未来数据"""
        mock_retry.return_value = [
            [1000, 100, 102, 99, 101, 1000],
            [2000, 101, 103, 100, 102, 1100],
            [3000, 102, 104, 101, 103, 1200],  # 应该被过滤
            [4000, 103, 105, 102, 104, 1300],  # 应该被过滤
        ]

        result = _fetch_ohlcv_ccxt(self.mock_exchange, "BTC/USDT", "1h", 1000, 3000)

        self.assertEqual(len(result), 2)
        self.assertTrue(all(result["timestamp"] < 3000))

    @patch("utils.data_management.data_retrieval.retry_fetch")
    def test_fetch_okx_uses_smaller_limit(self, mock_retry):
        """测试 OKX 使用较小的 limit 参数"""
        self.mock_exchange.id = "okx"
        mock_retry.return_value = [[1000, 100, 102, 99, 101, 1000]]

        _fetch_ohlcv_ccxt(self.mock_exchange, "BTC/USDT", "1h", 1000, 3000)

        # 验证使用了 limit=100
        call_args = mock_retry.call_args
        self.assertEqual(call_args[1]["limit"], 100)


class TestBatchFetchOHLCV(unittest.TestCase):
    """测试 batch_fetch_ohlcv 函数"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.base_dir = Path(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    @patch("utils.data_management.data_retrieval.fetch_ohlcv_data")
    @patch("ccxt.binance")
    def test_batch_fetch_success(self, mock_exchange_class, mock_fetch):
        """测试批量获取成功"""
        mock_exchange = Mock()
        mock_exchange.load_markets = Mock()
        mock_exchange_class.return_value = mock_exchange

        mock_fetch.return_value = pd.DataFrame(
            {
                "timestamp": [1000, 2000],
                "open": [100, 101],
                "high": [102, 103],
                "low": [99, 100],
                "close": [101, 102],
                "volume": [1000, 1100],
            }
        )

        symbols = ["BTCUSDT", "ETHUSDT"]
        result = batch_fetch_ohlcv(
            symbols=symbols,
            start_date="2024-01-01",
            end_date="2024-01-02",
            timeframe="1h",
            exchange_id="binance",
            base_dir=self.base_dir,
            source="auto",
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(mock_fetch.call_count, 2)

    @patch("utils.data_management.data_retrieval.fetch_ohlcv_data")
    @patch("ccxt.binance")
    def test_batch_fetch_handles_errors(self, mock_exchange_class, mock_fetch):
        """测试批量获取处理错误"""
        mock_exchange = Mock()
        mock_exchange.load_markets = Mock()
        mock_exchange_class.return_value = mock_exchange

        # 第一个成功，第二个返回空 DataFrame（模拟失败）
        mock_fetch.side_effect = [
            pd.DataFrame(
                {
                    "timestamp": [1000],
                    "open": [100],
                    "high": [102],
                    "low": [99],
                    "close": [101],
                    "volume": [1000],
                }
            ),
            pd.DataFrame(),  # 空 DataFrame 表示失败
        ]

        symbols = ["BTCUSDT", "ETHUSDT"]
        result = batch_fetch_ohlcv(
            symbols=symbols,
            start_date="2024-01-01",
            end_date="2024-01-02",
            timeframe="1h",
            exchange_id="binance",
            base_dir=self.base_dir,
            source="auto",
        )

        # 应该只返回成功的一个
        self.assertEqual(len(result), 1)


class TestFetchOIHistory(unittest.TestCase):
    """测试 OI 历史数据获取函数"""

    @patch("utils.data_management.data_retrieval.retry_fetch")
    def test_fetch_binance_oi_success(self, mock_retry):
        """测试 Binance OI 数据获取成功"""
        mock_exchange = Mock()
        mock_exchange.rateLimit = 100

        # Binance 返回的实际格式
        mock_retry.return_value = [
            {"timestamp": 1000, "sumOpenInterest": "1000000", "sumOpenInterestValue": "50000000"},
            {"timestamp": 2000, "sumOpenInterest": "1100000", "sumOpenInterestValue": "55000000"},
        ]

        result = fetch_binance_oi_history(mock_exchange, "BTCUSDT", 1000, 3000)

        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 2)
        self.assertIn("timestamp", result.columns)
        self.assertIn("open_interest", result.columns)

    @patch("utils.data_management.data_retrieval.retry_fetch")
    def test_fetch_binance_oi_empty(self, mock_retry):
        """测试 Binance OI 空结果"""
        mock_exchange = Mock()
        mock_retry.return_value = []

        result = fetch_binance_oi_history(mock_exchange, "BTCUSDT", 1000, 3000)

        self.assertTrue(result.empty)

    @patch("utils.data_management.data_retrieval.retry_fetch")
    def test_fetch_okx_oi_success(self, mock_retry):
        """测试 OKX OI 数据获取成功"""
        mock_exchange = Mock()
        mock_exchange.rateLimit = 100

        # OKX 返回的实际格式
        mock_retry.return_value = {
            "data": [
                {"ts": "1000", "oi": "1000000", "oiVol": "50000000"},
                {"ts": "2000", "oi": "1100000", "oiVol": "55000000"},
            ]
        }

        result = fetch_okx_oi_history(mock_exchange, "BTC-USDT-SWAP", 1000, 3000)

        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 2)
        self.assertIn("timestamp", result.columns)
        self.assertIn("open_interest", result.columns)


class TestFetchFundingRateHistory(unittest.TestCase):
    """测试 Funding Rate 历史数据获取函数"""

    @patch("utils.data_management.data_retrieval.retry_fetch")
    def test_fetch_binance_funding_success(self, mock_retry):
        """测试 Binance Funding Rate 数据获取成功"""
        mock_exchange = Mock()
        mock_exchange.rateLimit = 100

        # Binance 返回的实际格式
        mock_retry.return_value = [
            {"fundingTime": 1000, "fundingRate": "0.0001"},
            {"fundingTime": 2000, "fundingRate": "0.0002"},
        ]

        result = fetch_binance_funding_rate_history(mock_exchange, "BTCUSDT", 1000, 3000)

        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 2)
        self.assertIn("timestamp", result.columns)
        self.assertIn("funding_rate", result.columns)

    @patch("utils.data_management.data_retrieval.retry_fetch")
    def test_fetch_okx_funding_success(self, mock_retry):
        """测试 OKX Funding Rate 数据获取成功"""
        mock_exchange = Mock()
        mock_exchange.rateLimit = 100

        # OKX 返回的实际格式
        mock_retry.return_value = {
            "data": [
                {"fundingTime": "1000", "fundingRate": "0.0001", "realizedRate": "0.00009"},
                {"fundingTime": "2000", "fundingRate": "0.0002", "realizedRate": "0.00019"},
            ]
        }

        result = fetch_okx_funding_rate_history(mock_exchange, "BTC-USDT-SWAP", 1000, 3000)

        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 2)
        self.assertIn("timestamp", result.columns)
        self.assertIn("funding_rate", result.columns)


class TestBatchFetchOIAndFunding(unittest.TestCase):
    """测试 batch_fetch_oi_and_funding 函数"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.base_dir = Path(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    @patch("utils.data_management.data_retrieval.fetch_binance_oi_history")
    @patch("utils.data_management.data_retrieval.fetch_binance_funding_rate_history")
    @patch("ccxt.binance")
    def test_batch_fetch_binance(self, mock_exchange_class, mock_funding, mock_oi):
        """测试批量获取 Binance OI 和 Funding Rate"""
        mock_exchange = Mock()
        mock_exchange.load_markets = Mock()
        mock_exchange.markets = {"BTC/USDT:USDT": {}}  # 添加 markets 属性
        mock_exchange_class.return_value = mock_exchange

        mock_oi.return_value = pd.DataFrame(
            {"timestamp": [1000, 2000], "open_interest": [1000000, 1100000]}
        )

        mock_funding.return_value = pd.DataFrame(
            {"timestamp": [1000, 2000], "funding_rate": [0.0001, 0.0002]}
        )

        symbols = ["BTCUSDT"]
        result = batch_fetch_oi_and_funding(
            symbols=symbols,
            start_date="2024-01-01",
            end_date="2024-01-02",
            exchange_id="binance",
            base_dir=self.base_dir,
        )

        # 返回的是字典，包含 oi_files 和 funding_files
        self.assertIsInstance(result, dict)
        self.assertIn("oi_files", result)
        self.assertIn("funding_files", result)
        # OI 数据获取已禁用，所以只有 funding_files
        self.assertEqual(len(result["funding_files"]), 1)
        mock_funding.assert_called_once()

    @patch("utils.data_management.data_retrieval.fetch_okx_oi_history")
    @patch("utils.data_management.data_retrieval.fetch_okx_funding_rate_history")
    @patch("ccxt.okx")
    def test_batch_fetch_okx(self, mock_exchange_class, mock_funding, mock_oi):
        """测试批量获取 OKX OI 和 Funding Rate"""
        mock_exchange = Mock()
        mock_exchange.load_markets = Mock()
        # OKX 使用 BTC/USDT:USDT 格式
        mock_exchange.markets = {"BTC/USDT:USDT": {}}
        mock_exchange_class.return_value = mock_exchange

        mock_oi.return_value = pd.DataFrame(
            {"timestamp": [1000, 2000], "open_interest": [1000000, 1100000]}
        )

        mock_funding.return_value = pd.DataFrame(
            {"timestamp": [1000, 2000], "funding_rate": [0.0001, 0.0002]}
        )

        # 使用标准格式的符号，会被 resolve_symbol_and_type 转换
        symbols = ["BTCUSDT"]
        result = batch_fetch_oi_and_funding(
            symbols=symbols,
            start_date="2024-01-01",
            end_date="2024-01-02",
            exchange_id="okx",
            base_dir=self.base_dir,
        )

        # 返回的是字典，包含 oi_files 和 funding_files
        self.assertIsInstance(result, dict)
        self.assertIn("oi_files", result)
        self.assertIn("funding_files", result)
        # OI 数据获取已禁用，所以只有 funding_files
        self.assertEqual(len(result["funding_files"]), 1)
        mock_funding.assert_called_once()


if __name__ == "__main__":
    unittest.main()
