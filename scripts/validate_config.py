#!/usr/bin/env python3
"""
配置验证脚本

在启动前验证所有配置文件的正确性，包括：
- YAML 语法检查
- Pydantic 模型验证
- 字段名匹配检查
- 继承关系验证
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.adapter import ConfigAdapter
from core.loader import ConfigLoader
from core.schemas import ConfigPaths


def validate_all_configs():
    """验证所有配置文件"""
    print("🔍 开始配置验证...\n")

    errors = []
    warnings = []

    loader = ConfigLoader()
    paths = ConfigPaths()

    # 1. 验证 active.yaml
    print("📋 验证 active.yaml...")
    try:
        active_config = loader.load_active_config()
        print(f"  ✅ 当前环境: {active_config.environment}")
        print(f"  ✅ 当前策略: {active_config.strategy}")
        if active_config.overrides:
            print(f"  ℹ️  包含 overrides: {list(active_config.overrides.keys())}")
    except Exception as e:
        errors.append(f"active.yaml 验证失败: {e}")
        print(f"  ❌ 失败: {e}")

    print()

    # 2. 验证所有环境配置
    print("🌍 验证环境配置...")
    for env_name in paths.list_environments():
        try:
            env_config = loader.load_environment_config(env_name)
            print(f"  ✅ {env_name}.yaml")

            # 检查关键字段
            if not env_config.trading.main_timeframe:
                warnings.append(f"{env_name}: main_timeframe 未设置")
            if not env_config.backtest.start_date:
                warnings.append(f"{env_name}: start_date 未设置")

        except Exception as e:
            errors.append(f"{env_name}.yaml 验证失败: {e}")
            print(f"  ❌ {env_name}.yaml: {e}")

    print()

    # 3. 验证所有策略配置
    print("🎯 验证策略配置...")
    for strategy_name in paths.list_strategies():
        try:
            strategy_config = loader.load_strategy_config(strategy_name)
            print(f"  ✅ {strategy_name}.yaml")

            # 检查必需字段
            if not strategy_config.name:
                errors.append(f"{strategy_name}: name 字段缺失")
            if not strategy_config.module_path:
                errors.append(f"{strategy_name}: module_path 字段缺失")

        except Exception as e:
            errors.append(f"{strategy_name}.yaml 验证失败: {e}")
            print(f"  ❌ {strategy_name}.yaml: {e}")

    print()

    # 4. 验证完整的配置加载（包括 overrides）
    print("🔧 验证完整配置加载...")
    try:
        adapter = ConfigAdapter()
        print("  ✅ ConfigAdapter 初始化成功")
        print(f"  ✅ 环境: {adapter.active_config.environment}")
        print(f"  ✅ 策略: {adapter.active_config.strategy}")
        print(f"  ✅ 主时间框架: {adapter.get_main_timeframe()}")
        print(f"  ✅ 回测时间: {adapter.get_start_date()} 到 {adapter.get_end_date()}")
        print(
            f"  ✅ 初始资金: {adapter.env_config.trading.initial_balance} {adapter.env_config.trading.currency}"
        )

        # 收集验证警告（兼容旧版本 loader）
        if hasattr(loader, "get_validation_warnings"):
            validation_warnings = loader.get_validation_warnings()
            if validation_warnings:
                warnings.extend([f"{name}: {w.message}" for name, w in validation_warnings])
    except Exception as e:
        errors.append(f"ConfigAdapter 初始化失败: {e}")
        print(f"  ❌ 失败: {e}")

    print()

    # 5. 输出总结
    print("=" * 60)
    if errors:
        print(f"❌ 验证失败，发现 {len(errors)} 个错误:")
        for error in errors:
            print(f"  • {error}")
        print()

    if warnings:
        print(f"⚠️  发现 {len(warnings)} 个警告:")
        for warning in warnings:
            print(f"  • {warning}")
        print()

    if not errors and not warnings:
        print("✅ 所有配置验证通过！")
        return 0
    elif not errors:
        print("✅ 配置验证通过（有警告）")
        return 0
    else:
        print("❌ 配置验证失败")
        return 1


if __name__ == "__main__":
    sys.exit(validate_all_configs())
