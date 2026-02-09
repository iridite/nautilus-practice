"""
网络工具模块单元测试

测试内容：
1. retry_fetch() - 重试机制函数
2. 网络错误处理和重试逻辑
3. 延时和指数退避机制
4. 边界情况测试

Usage:
    uv run python -m unittest tests.test_network -v
"""

import time
import unittest
from unittest.mock import Mock

import ccxt

from utils.network import retry_fetch


class TestNetwork(unittest.TestCase):
    """网络工具测试类"""

    def test_retry_fetch_success_first_try(self):
        """测试第一次尝试就成功的情况"""
        mock_func = Mock(return_value="success")

        result = retry_fetch(mock_func, "arg1", "arg2", retries=3, delay=1)

        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 1)
        mock_func.assert_called_once_with("arg1", "arg2")

    def test_retry_fetch_success_after_retries(self):
        """测试重试后成功的情况"""
        mock_func = Mock()
        # 前两次失败，第三次成功
        mock_func.side_effect = [
            ccxt.NetworkError("网络错误"),
            ccxt.ExchangeError("交易所错误"),
            "success"
        ]

        start_time = time.time()
        result = retry_fetch(mock_func, retries=3, delay=0.1)
        end_time = time.time()

        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 3)
        # 验证确实有延时（至少2次延时）
        self.assertGreater(end_time - start_time, 0.15)

    def test_retry_fetch_all_attempts_failed(self):
        """测试所有重试都失败的情况"""
        mock_func = Mock()
        mock_func.side_effect = ccxt.NetworkError("持续网络错误")

        with self.assertRaises(ccxt.NetworkError):
            retry_fetch(mock_func, retries=3, delay=0.1)

        self.assertEqual(mock_func.call_count, 3)

    def test_retry_fetch_rate_limit_handling(self):
        """测试API限速错误的特殊处理"""
        mock_func = Mock()
        # 模拟418或-1003错误码（应该有更长的延时）
        mock_func.side_effect = [
            ccxt.ExchangeError("418 - Too Many Requests"),
            "success"
        ]

        start_time = time.time()
        result = retry_fetch(mock_func, retries=3, delay=0.1)
        end_time = time.time()

        self.assertEqual(result, "success")
        # 应该有双倍延时（0.2秒而不是0.1秒）
        self.assertGreater(end_time - start_time, 0.15)

    def test_retry_fetch_binance_rate_limit(self):
        """测试Binance特有的-1003错误码处理"""
        mock_func = Mock()
        mock_func.side_effect = [
            ccxt.ExchangeError("-1003 - Rate limit exceeded"),
            "success"
        ]

        start_time = time.time()
        result = retry_fetch(mock_func, retries=3, delay=0.1)
        end_time = time.time()

        self.assertEqual(result, "success")
        # 应该有双倍延时
        self.assertGreater(end_time - start_time, 0.15)

    def test_retry_fetch_with_kwargs(self):
        """测试带关键字参数的函数调用"""
        mock_func = Mock(return_value="success")

        result = retry_fetch(
            mock_func,
            "positional_arg",
            retries=2,
            delay=0.1,
            keyword_arg="test",
            another_kwarg=42
        )

        self.assertEqual(result, "success")
        mock_func.assert_called_once_with(
            "positional_arg",
            keyword_arg="test",
            another_kwarg=42
        )

    def test_retry_fetch_non_network_error(self):
        """测试非网络错误不会重试"""
        mock_func = Mock()
        mock_func.side_effect = ValueError("普通错误，不应重试")

        with self.assertRaises(ValueError):
            retry_fetch(mock_func, retries=3, delay=0.1)

        # 非网络错误应该直接抛出，不重试
        self.assertEqual(mock_func.call_count, 1)

    def test_retry_fetch_zero_retries(self):
        """测试retries=0的情况"""
        mock_func = Mock()
        mock_func.side_effect = ccxt.NetworkError("网络错误")

        with self.assertRaises(ccxt.NetworkError):
            retry_fetch(mock_func, retries=0, delay=0.1)

        # retries=0意味着不重试，只执行一次
        self.assertEqual(mock_func.call_count, 1)

    def test_retry_fetch_custom_delay(self):
        """测试自定义延时设置"""
        mock_func = Mock()
        mock_func.side_effect = [
            ccxt.NetworkError("网络错误"),
            "success"
        ]

        start_time = time.time()
        result = retry_fetch(mock_func, retries=2, delay=0.2)
        end_time = time.time()

        self.assertEqual(result, "success")
        # 应该有大约0.2秒的延时
        self.assertGreater(end_time - start_time, 0.15)
        self.assertLess(end_time - start_time, 0.35)

    def test_retry_fetch_return_none_on_failure(self):
        """测试所有重试失败后返回None的边界情况"""
        # 这个测试确保函数在理论上的边界情况下能正确处理
        # 虽然当前实现会抛出异常，但这是正确的行为
        mock_func = Mock()
        mock_func.side_effect = ccxt.NetworkError("持续网络错误")

        with self.assertRaises(ccxt.NetworkError):
            retry_fetch(mock_func, retries=1, delay=0.05)

    def test_retry_fetch_mixed_error_types(self):
        """测试混合错误类型的处理"""
        mock_func = Mock()
        mock_func.side_effect = [
            ccxt.NetworkError("网络错误"),
            ccxt.ExchangeError("交易所错误"),
            "success"
        ]

        result = retry_fetch(mock_func, retries=3, delay=0.05)
        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 3)


if __name__ == "__main__":
    unittest.main()
