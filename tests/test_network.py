"""
测试 utils/network.py 网络工具模块
"""

import unittest
from unittest.mock import Mock, patch
import time

import ccxt

from utils.network import retry_fetch


class TestRetryFetch(unittest.TestCase):
    """测试 retry_fetch 函数"""

    def test_successful_call(self):
        """测试成功调用"""
        mock_func = Mock(return_value="success")
        result = retry_fetch(mock_func)
        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 1)

    def test_successful_call_with_args(self):
        """测试带参数的成功调用"""
        mock_func = Mock(return_value="result")
        result = retry_fetch(mock_func, "arg1", "arg2", key="value")
        self.assertEqual(result, "result")
        mock_func.assert_called_once_with("arg1", "arg2", key="value")

    def test_retry_on_network_error(self):
        """测试网络错误重试"""
        mock_func = Mock(side_effect=[
            ccxt.NetworkError("Connection timeout"),
            "success"
        ])

        with patch('time.sleep'):  # 跳过实际延迟
            result = retry_fetch(mock_func, retries=3, delay=1.0)

        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 2)

    def test_retry_on_exchange_error(self):
        """测试��易所错误重试"""
        mock_func = Mock(side_effect=[
            ccxt.ExchangeError("Temporary error"),
            "success"
        ])

        with patch('time.sleep'):
            result = retry_fetch(mock_func, retries=3, delay=1.0)

        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 2)

    def test_max_retries_exceeded(self):
        """测试超过最大重试次数"""
        mock_func = Mock(side_effect=ccxt.NetworkError("Persistent error"))

        with patch('time.sleep'):
            with self.assertRaises(ccxt.NetworkError):
                retry_fetch(mock_func, retries=3, delay=0.1)

        self.assertEqual(mock_func.call_count, 3)

    def test_rate_limit_error_delay(self):
        """测试限流错误的延迟策略"""
        mock_func = Mock(side_effect=[
            ccxt.ExchangeError("418 rate limit exceeded"),
            "success"
        ])

        with patch('time.sleep') as mock_sleep:
            result = retry_fetch(mock_func, retries=3, delay=1.0, backoff_factor=2.0)

        self.assertEqual(result, "success")
        # 限流错误应该使用更长的延迟: delay * backoff_factor * 2
        mock_sleep.assert_called_once_with(4.0)

    def test_rate_limit_error_with_1003_code(self):
        """测试 -1003 限流错误码"""
        mock_func = Mock(side_effect=[
            ccxt.ExchangeError("-1003 Too many requests"),
            "success"
        ])

        with patch('time.sleep') as mock_sleep:
            result = retry_fetch(mock_func, retries=3, delay=1.0, backoff_factor=2.0)

        self.assertEqual(result, "success")
        mock_sleep.assert_called_once_with(4.0)

    def test_rate_limit_error_with_text(self):
        """测试文本形式的限流错误"""
        mock_func = Mock(side_effect=[
            ccxt.ExchangeError("rate limit exceeded"),
            "success"
        ])

        with patch('time.sleep') as mock_sleep:
            result = retry_fetch(mock_func, retries=3, delay=1.0, backoff_factor=2.0)

        self.assertEqual(result, "success")
        mock_sleep.assert_called_once_with(4.0)

    def test_connection_error_backoff(self):
        """测试连接错误的指数退避"""
        mock_func = Mock(side_effect=[
            ccxt.NetworkError("connection timeout"),
            ccxt.NetworkError("connection timeout"),
            "success"
        ])

        with patch('time.sleep') as mock_sleep:
            result = retry_fetch(mock_func, retries=3, delay=1.0, backoff_factor=2.0)

        self.assertEqual(result, "success")
        # 第一次重试: delay * (backoff_factor ** 0) = 1.0
        # 第二次重试: delay * (backoff_factor ** 1) = 2.0
        self.assertEqual(mock_sleep.call_count, 2)
        calls = [call[0][0] for call in mock_sleep.call_args_list]
        self.assertEqual(calls, [1.0, 2.0])

    def test_network_error_backoff(self):
        """测试网络错误的指数退避"""
        mock_func = Mock(side_effect=[
            ccxt.NetworkError("network error"),
            "success"
        ])

        with patch('time.sleep') as mock_sleep:
            result = retry_fetch(mock_func, retries=3, delay=2.0, backoff_factor=2.0)

        self.assertEqual(result, "success")
        mock_sleep.assert_called_once_with(2.0)

    def test_custom_exceptions(self):
        """测试自定义异常类型"""
        class CustomError(Exception):
            pass

        mock_func = Mock(side_effect=[
            CustomError("Custom error"),
            "success"
        ])

        with patch('time.sleep'):
            result = retry_fetch(
                mock_func,
                retries=3,
                delay=1.0,
                exceptions=(CustomError,)
            )

        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 2)

    def test_non_retryable_exception(self):
        """测试不可重试的异常"""
        mock_func = Mock(side_effect=ValueError("Invalid value"))

        with self.assertRaises(ValueError):
            retry_fetch(mock_func, retries=3, delay=0.1)

        # 不应该重试，只调用一次
        self.assertEqual(mock_func.call_count, 1)

    def test_zero_retries(self):
        """测试零重试次数（至少执行一次）"""
        mock_func = Mock(return_value="success")
        result = retry_fetch(mock_func, retries=0)
        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 1)

    def test_negative_retries(self):
        """测试负数重试次数（至少执行一次）"""
        mock_func = Mock(return_value="success")
        result = retry_fetch(mock_func, retries=-1)
        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 1)

    def test_backoff_factor(self):
        """测试不同的退避因子"""
        mock_func = Mock(side_effect=[
            ccxt.NetworkError("timeout"),
            ccxt.NetworkError("timeout"),
            "success"
        ])

        with patch('time.sleep') as mock_sleep:
            result = retry_fetch(mock_func, retries=3, delay=1.0, backoff_factor=3.0)

        self.assertEqual(result, "success")
        # 第一次: 1.0 * (3.0 ** 0) = 1.0
        # 第二次: 1.0 * (3.0 ** 1) = 3.0
        calls = [call[0][0] for call in mock_sleep.call_args_list]
        self.assertEqual(calls, [1.0, 3.0])

    def test_last_attempt_raises_exception(self):
        """测试最后一次尝试失败抛出异常"""
        error_msg = "Final error"
        mock_func = Mock(side_effect=ccxt.NetworkError(error_msg))

        with patch('time.sleep'):
            with self.assertRaises(ccxt.NetworkError) as context:
                retry_fetch(mock_func, retries=2, delay=0.1)

        self.assertIn(error_msg, str(context.exception))

    def test_multiple_error_types(self):
        """测试多种错误类型"""
        mock_func = Mock(side_effect=[
            ccxt.NetworkError("Network error"),
            ccxt.ExchangeError("Exchange error"),
            "success"
        ])

        with patch('time.sleep'):
            result = retry_fetch(
                mock_func,
                retries=3,
                delay=0.1,
                exceptions=(ccxt.NetworkError, ccxt.ExchangeError)
            )

        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 3)


if __name__ == "__main__":
    unittest.main()
