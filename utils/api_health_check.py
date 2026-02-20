"""
API 健康检查模块

在运行实盘或模拟盘之前，测试 API 连接的可用性。
"""

import asyncio
import time
from typing import Dict, Optional, Tuple

import httpx
import logging

logger = logging.getLogger(__name__)


class APIHealthChecker:
    """API 健康检查器"""

    def __init__(self, timeout: float = 10.0):
        """
        初始化健康检查器

        Args:
            timeout: 请求超时时间（秒）
        """
        self.timeout = timeout
        self.results: Dict[str, Dict] = {}

    async def check_binance_api(self, base_url: str = "https://api.binance.com") -> Tuple[bool, str, Optional[float]]:
        """
        检查 Binance API 连接

        Args:
            base_url: Binance API 基础 URL

        Returns:
            (是否成功, 消息, 响应时间ms)
        """
        endpoint = f"{base_url}/api/v3/ping"

        try:
            start_time = time.time()
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(endpoint)
                elapsed_ms = (time.time() - start_time) * 1000

                if response.status_code == 200:
                    return True, "连接成功", elapsed_ms
                else:
                    return False, f"HTTP {response.status_code}: {response.text[:200]}", elapsed_ms

        except httpx.TimeoutException:
            return False, f"连接超时（>{self.timeout}秒）", None
        except httpx.ConnectError as e:
            return False, f"连接失败: {str(e)}", None
        except Exception as e:
            return False, f"未知错误: {type(e).__name__}: {str(e)}", None

    async def check_binance_time_sync(self, base_url: str = "https://api.binance.com") -> Tuple[bool, str, Optional[int]]:
        """
        检查本地时间与 Binance 服务器时间的同步情况

        Args:
            base_url: Binance API 基础 URL

        Returns:
            (是否同步, 消息, 时间差ms)
        """
        endpoint = f"{base_url}/api/v3/time"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                local_time = int(time.time() * 1000)
                response = await client.get(endpoint)

                if response.status_code == 200:
                    server_time = response.json()["serverTime"]
                    time_diff = abs(server_time - local_time)

                    if time_diff > 5000:  # 超过 5 秒
                        return False, f"时间差过大: {time_diff}ms（建议 <1000ms）", time_diff
                    elif time_diff > 1000:  # 超过 1 秒
                        return True, f"时间差较大: {time_diff}ms（建议 <1000ms）", time_diff
                    else:
                        return True, f"时间同步正常: {time_diff}ms", time_diff
                else:
                    return False, f"无法获取服务器时间: HTTP {response.status_code}", None

        except Exception as e:
            return False, f"时间同步检查失败: {str(e)}", None

    async def check_binance_authenticated(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        base_url: str = "https://api.binance.com"
    ) -> Tuple[bool, str]:
        """
        检查 Binance API 认证

        Args:
            api_key: API Key
            api_secret: API Secret
            base_url: Binance API 基础 URL

        Returns:
            (是否成功, 消息)
        """
        if not api_key or not api_secret:
            return True, "未配置 API Key，跳过认证检查"

        endpoint = f"{base_url}/api/v3/account"

        try:
            import hmac
            import hashlib
            from urllib.parse import urlencode

            timestamp = int(time.time() * 1000)
            params = {"timestamp": timestamp}
            query_string = urlencode(params)
            signature = hmac.new(
                api_secret.encode("utf-8"),
                query_string.encode("utf-8"),
                hashlib.sha256
            ).hexdigest()

            headers = {"X-MBX-APIKEY": api_key}
            full_url = f"{endpoint}?{query_string}&signature={signature}"

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(full_url, headers=headers)

                if response.status_code == 200:
                    return True, "API 认证成功"
                elif response.status_code == 401:
                    return False, "API Key 无效或已过期"
                elif response.status_code == 403:
                    return False, "API 权限不足"
                else:
                    error_msg = response.json().get("msg", response.text[:200])
                    return False, f"认证失败: {error_msg}"

        except Exception as e:
            return False, f"认证检查失败: {str(e)}"

    async def run_all_checks(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        base_url: str = "https://api.binance.com"
    ) -> Dict[str, Dict]:
        """
        运行所有健康检查

        Args:
            api_key: API Key（可选）
            api_secret: API Secret（可选）
            base_url: Binance API 基础 URL

        Returns:
            检查结果字典
        """
        logger.info("开始 API 健康检查...")

        # 1. 基础连接测试
        success, message, response_time = await self.check_binance_api(base_url)
        self.results["connectivity"] = {
            "success": success,
            "message": message,
            "response_time_ms": response_time
        }

        if not success:
            logger.error(f"❌ 连接测试失败: {message}")
            return self.results

        logger.info(f"✓ 连接测试通过 ({response_time:.0f}ms)")

        # 2. 时间同步测试
        success, message, time_diff = await self.check_binance_time_sync(base_url)
        self.results["time_sync"] = {
            "success": success,
            "message": message,
            "time_diff_ms": time_diff
        }

        if not success:
            logger.error(f"❌ 时间同步失败: {message}")
        else:
            logger.info(f"✓ 时间同步检查通过: {message}")

        # 3. API 认证测试（如果提供了密钥）
        if api_key and api_secret:
            success, message = await self.check_binance_authenticated(api_key, api_secret, base_url)
            self.results["authentication"] = {
                "success": success,
                "message": message
            }

            if not success:
                logger.error(f"❌ API 认证失败: {message}")
            else:
                logger.info("✓ API 认证通过")
        else:
            self.results["authentication"] = {
                "success": True,
                "message": "未配置 API Key，跳过认证检查"
            }
            logger.info("⊘ 跳过 API 认证检查（未配置密钥）")

        return self.results

    def is_healthy(self) -> bool:
        """
        判断 API 是否健康

        Returns:
            True 如果所有关键检查都通过
        """
        if not self.results:
            return False

        # 连接必须成功
        if not self.results.get("connectivity", {}).get("success", False):
            return False

        # 时间同步必须成功（允许警告）
        if not self.results.get("time_sync", {}).get("success", False):
            return False

        # 如果配置了认证，认证必须成功
        auth_result = self.results.get("authentication", {})
        if "API Key" in auth_result.get("message", "") and not auth_result.get("success", False):
            return False

        return True

    def get_summary(self) -> str:
        """
        获取检查结果摘要

        Returns:
            格式化的摘要字符串
        """
        if not self.results:
            return "未执行健康检查"

        lines = ["\n" + "="*60]
        lines.append("API 健康检查结果")
        lines.append("="*60)

        # 连接测试
        conn = self.results.get("connectivity", {})
        status = "✓" if conn.get("success") else "✗"
        lines.append(f"{status} 连接测试: {conn.get('message', 'N/A')}")
        if conn.get("response_time_ms"):
            lines.append(f"  响应时间: {conn['response_time_ms']:.0f}ms")

        # 时间同步
        time_sync = self.results.get("time_sync", {})
        status = "✓" if time_sync.get("success") else "✗"
        lines.append(f"{status} 时间同步: {time_sync.get('message', 'N/A')}")

        # 认证
        auth = self.results.get("authentication", {})
        if "跳过" not in auth.get("message", ""):
            status = "✓" if auth.get("success") else "✗"
            lines.append(f"{status} API 认证: {auth.get('message', 'N/A')}")

        lines.append("="*60)

        if self.is_healthy():
            lines.append("✓ 所有检查通过，可以开始交易")
        else:
            lines.append("✗ 检查未通过，请修复上述问题后重试")

        lines.append("="*60 + "\n")

        return "\n".join(lines)


async def check_api_health(
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    base_url: str = "https://api.binance.com",
    timeout: float = 10.0
) -> Tuple[bool, str]:
    """
    便捷函数：执行 API 健康检查

    Args:
        api_key: API Key（可选）
        api_secret: API Secret（可选）
        base_url: Binance API 基础 URL
        timeout: 请求超时时间（秒）

    Returns:
        (是否健康, 摘要信息)
    """
    checker = APIHealthChecker(timeout=timeout)
    await checker.run_all_checks(api_key, api_secret, base_url)
    return checker.is_healthy(), checker.get_summary()


if __name__ == "__main__":
    # 测试用例
    async def main():
        is_healthy, summary = await check_api_health()
        print(summary)
        print(f"\n健康状态: {'健康' if is_healthy else '不健康'}")

    asyncio.run(main())
