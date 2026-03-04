#!/usr/bin/env python3
"""验证所有策略配置"""
import sys
import yaml
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.adapter import get_adapter

def verify_strategy(strategy_name: str, overrides: dict = None) -> bool:
    """验证单个策略配置"""
    try:
        # 修改 active.yaml
        active_file = Path('config/active.yaml')
        config = {
            'environment': 'dev',
            'strategy': strategy_name
        }
        if overrides:
            config['overrides'] = overrides

        with open(active_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

        # 加载配置
        adapter = get_adapter()
        adapter.reload()

        # 验证关键配置
        env_config = adapter.env_config

        print(f"✅ {strategy_name}")
        print(f"   - Initial balance: {env_config.trading.initial_balance}")
        print(f"   - Venue: {env_config.trading.venue}")

        return True
    except Exception as e:
        print(f"❌ {strategy_name}: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """验证所有策略"""
    print("=" * 60)
    print("验证所有策略配置")
    print("=" * 60)

    strategies = [
        ('keltner_rs_breakout', None),
        ('dual_thrust', None),
        ('funding_arbitrage', None),
        ('spot_futures_arbitrage', None),
    ]

    results = []
    for strategy, overrides in strategies:
        success = verify_strategy(strategy, overrides)
        results.append((strategy, success))
        print()

    # 总结
    print("=" * 60)
    print("验证结果总结")
    print("=" * 60)
    passed = sum(1 for _, success in results if success)
    total = len(results)
    print(f"通过: {passed}/{total}")

    if passed == total:
        print("✅ 所有策略配置验证通过！")
        return 0
    else:
        print("❌ 部分策略配置验证失败！")
        return 1

if __name__ == '__main__':
    sys.exit(main())
