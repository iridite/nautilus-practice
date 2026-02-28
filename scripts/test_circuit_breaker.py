#!/usr/bin/env python3
"""测试资金费率熔断器和现货替代功能"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from live.circuit_breaker import CircuitBreakerManager, InstrumentType
from live.funding_rate_monitor import FundingRateMonitor


async def test_circuit_breaker():
    """测试熔断器功能"""
    print("=" * 60)
    print("测试资金费率熔断器")
    print("=" * 60)
    print()

    # 创建监控器和熔断器
    monitor = FundingRateMonitor()
    breaker = CircuitBreakerManager(
        funding_monitor=monitor,
        fallback_threshold_annual=50.0,  # 50% 触发现货回退
        circuit_breaker_annual=100.0,  # 100% 触发熔断
        venue="BINANCE",
    )

    # 测试场景
    test_cases = [
        ("ETHUSDT", "ETHUSDT-PERP.BINANCE"),
        ("BTCUSDT", "BTCUSDT-PERP.BINANCE"),
        ("SOLUSDT", "SOLUSDT-PERP.BINANCE"),
    ]

    print("📊 测试实时资金费率决策")
    print("-" * 60)

    for symbol, instrument_id in test_cases:
        try:
            decision = await breaker.evaluate_signal(symbol, instrument_id)

            print(f"\n标的: {symbol}")
            print(f"  原始标的: {instrument_id}")
            print(f"  年化费率: {decision.funding_rate_annual:.2f}%")
            print(f"  决策: {decision.decision.value}")
            print(f"  目标标的: {decision.instrument_id or 'N/A'}")
            print(f"  原因: {decision.reason}")

            # 判断决策类型
            if decision.decision == InstrumentType.REJECT:
                print(f"  ❌ 信号被拒绝 (熔断器触发)")
            elif decision.decision == InstrumentType.SPOT:
                print(f"  💱 切换到现货")
            else:
                print(f"  ✅ 正常执行永续合约")

        except Exception as e:
            print(f"\n❌ {symbol} 测试失败: {e}")

    # 输出统计信息
    print("\n" + "=" * 60)
    print("统计信息")
    print("=" * 60)
    stats = breaker.get_statistics()
    print(f"总信号数: {stats['total_signals']}")
    print(f"熔断拒绝: {stats['rejected_by_circuit_breaker']}")
    print(f"现货替代: {stats['switched_to_spot']}")
    print(f"正常执行: {stats['normal_perp_execution']}")

    if stats["total_signals"] > 0:
        print(f"\n拒绝率: {stats.get('rejection_rate', 0):.1%}")
        print(f"现货替代率: {stats.get('spot_fallback_rate', 0):.1%}")
        print(f"正常执行率: {stats.get('normal_execution_rate', 0):.1%}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_circuit_breaker())
