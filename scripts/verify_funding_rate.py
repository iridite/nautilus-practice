#!/usr/bin/env python3
"""
验证资金费率获取功能

测试从 Binance API 获取实时资金费率数据
"""

import asyncio
import sys
from datetime import datetime
from decimal import Decimal

import aiohttp


async def fetch_funding_rate(symbol: str = "ETHUSDT") -> dict:
    """
    从 Binance API 获取资金费率

    API 文档: https://binance-docs.github.io/apidocs/futures/en/#get-current-funding-rate
    """
    url = "https://fapi.binance.com/fapi/v1/premiumIndex"
    params = {"symbol": symbol}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "success": True,
                        "data": data,
                        "error": None
                    }
                else:
                    error_text = await response.text()
                    return {
                        "success": False,
                        "data": None,
                        "error": f"HTTP {response.status}: {error_text}"
                    }
        except asyncio.TimeoutError:
            return {
                "success": False,
                "data": None,
                "error": "Request timeout (>5s)"
            }
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }


def calculate_annual_rate(funding_rate_8h: float) -> float:
    """
    计算年化资金费率

    假设每 8 小时结算一次:
    - 每天 3 次
    - 每年 365 天
    - 转换为百分比
    """
    return funding_rate_8h * 3 * 365 * 100


async def main():
    """主函数"""
    print("=" * 60)
    print("资金费率获取验证脚本")
    print("=" * 60)
    print()

    # 测试多个标的
    test_symbols = ["ETHUSDT", "BTCUSDT", "SOLUSDT"]

    for symbol in test_symbols:
        print(f"📊 测试标的: {symbol}")
        print("-" * 60)

        result = await fetch_funding_rate(symbol)

        if result["success"]:
            data = result["data"]

            # 解析数据
            funding_rate_8h = float(data.get("lastFundingRate", 0))
            funding_rate_annual = calculate_annual_rate(funding_rate_8h)
            next_funding_time = int(data.get("nextFundingTime", 0))
            mark_price = float(data.get("markPrice", 0))

            # 格式化时间
            next_funding_dt = datetime.fromtimestamp(next_funding_time / 1000)

            # 输出结果
            print(f"✅ 成功获取资金费率")
            print(f"   标记价格: ${mark_price:,.2f}")
            print(f"   8小时费率: {funding_rate_8h:.6f} ({funding_rate_8h * 100:.4f}%)")
            print(f"   年化费率: {funding_rate_annual:.2f}%")
            print(f"   下次结算: {next_funding_dt.strftime('%Y-%m-%d %H:%M:%S')}")

            # 判断阈值
            if funding_rate_annual > 100:
                print(f"   ⚠️  状态: DANGER (>{100}%) - 触发熔断器")
            elif funding_rate_annual > 50:
                print(f"   ⚠️  状态: WARNING (>{50}%) - 建议现货替代")
            else:
                print(f"   ✅ 状态: NORMAL (<{50}%)")

        else:
            print(f"❌ 获取失败: {result['error']}")

        print()

    print("=" * 60)
    print("验证完成")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
