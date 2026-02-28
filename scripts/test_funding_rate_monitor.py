#!/usr/bin/env python3
"""测试资金费率监控模块"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from live.funding_rate_monitor import FundingRateMonitor, StaleDataError


async def test_funding_rate_monitor():
    """测试资金费率监控器"""
    print("=" * 60)
    print("测试资金费率监控模块")
    print("=" * 60)
    print()

    # 创建监控器
    monitor = FundingRateMonitor(
        refresh_interval_sec=300,  # 5分钟缓存
        max_staleness_sec=900,  # 15分钟最大延迟
        timeout_sec=5,
    )

    # 测试单个标的
    print("📊 测试 1: 获取单个标的资金费率")
    print("-" * 60)
    try:
        snapshot = await monitor.get_rate("ETHUSDT")
        print(f"✅ 成功获取 {snapshot.symbol}")
        print(f"   8小时费率: {snapshot.rate_8h:.6f}")
        print(f"   年化费率: {snapshot.rate_annual:.2f}%")
        print(f"   标记价格: ${snapshot.mark_price:,.2f}")
        print(f"   数据新鲜度: {snapshot.staleness_sec}s")
        print()
    except Exception as e:
        print(f"❌ 失败: {e}")
        print()

    # 测试缓存
    print("📊 测试 2: 测试缓存机制")
    print("-" * 60)
    try:
        snapshot2 = await monitor.get_rate("ETHUSDT")
        print(f"✅ 从缓存获取 {snapshot2.symbol}")
        print(f"   数据新鲜度: {snapshot2.staleness_sec}s")
        print()
    except Exception as e:
        print(f"❌ 失败: {e}")
        print()

    # 测试批量刷新
    print("📊 测试 3: 批量刷新多个标的")
    print("-" * 60)
    symbols = ["BTCUSDT", "SOLUSDT", "BNBUSDT"]
    try:
        snapshots = await monitor.refresh(symbols)
        print(f"✅ 成功刷新 {len(snapshots)}/{len(symbols)} 个标的")
        for symbol, snapshot in snapshots.items():
            print(f"   {symbol}: {snapshot.rate_annual:.2f}% 年化")
        print()
    except Exception as e:
        print(f"❌ 失败: {e}")
        print()

    # 测试过期检查
    print("📊 测试 4: 数据新鲜度检查")
    print("-" * 60)
    for symbol in ["ETHUSDT", "BTCUSDT"]:
        is_stale = monitor.is_stale(symbol, max_age_sec=600)  # 10分钟
        status = "过期" if is_stale else "新鲜"
        print(f"   {symbol}: {status}")
    print()

    print("=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_funding_rate_monitor())
