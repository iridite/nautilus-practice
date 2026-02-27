#!/usr/bin/env python3
"""
检查数据加载逻辑，确保策略使用的是真实的日线数据
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.loader import ConfigLoader
from nautilus_trader.model.enums import BarAggregation
import pandas as pd


def check_config():
    """检查配置文件中的时间周期设置"""
    print("=" * 60)
    print("1. 检查配置文件")
    print("=" * 60)

    loader = ConfigLoader(project_root / "config")

    # 加载环境配置
    env_config = loader.load_environment_config("dev")
    print(f"\n环境配置 (dev.yaml):")
    print(f"  回测时间范围: {env_config.backtest.start_date} 至 {env_config.backtest.end_date}")

    # 加载策略配置
    strategy_config = loader.load_strategy_config("keltner_rs_breakout")
    print(f"\n策略配置 (keltner_rs_breakout.yaml):")
    print(f"  策略名称: {strategy_config.name}")
    print(f"  timeframe 参数: {strategy_config.parameters.get('timeframe', 'NOT SET')}")

    # 检查数据源配置
    active_config = loader.load_active_config()
    print(f"\n活跃配置 (active.yaml):")
    print(f"  环境: {active_config.environment}")
    print(f"  策略: {active_config.strategy}")

    return strategy_config


def check_data_feeds():
    """检查数据源配置"""
    print("\n" + "=" * 60)
    print("2. 检查数据源配置")
    print("=" * 60)

    # 读取 active.yaml 来获取数据源配置
    import yaml
    active_path = project_root / "config" / "active.yaml"
    with open(active_path) as f:
        active_data = yaml.safe_load(f)

    # 读取环境配置
    env_name = active_data.get("environment", "dev")
    env_path = project_root / "config" / "environments" / f"{env_name}.yaml"

    # 检查是否有 extends
    with open(env_path) as f:
        env_data = yaml.safe_load(f)

    if "extends" in env_data:
        base_path = project_root / "config" / "environments" / env_data["extends"]
        with open(base_path) as f:
            base_data = yaml.safe_load(f)
        # 合并配置
        for key, value in base_data.items():
            if key not in env_data:
                env_data[key] = value

    # 检查数据源
    if "data_feeds" in env_data:
        print(f"\n找到 {len(env_data['data_feeds'])} 个数据源:")
        for i, feed in enumerate(env_data["data_feeds"]):
            print(f"\n  数据源 {i+1}:")
            print(f"    csv_file_name: {feed.get('csv_file_name', 'NOT SET')}")
            print(f"    bar_aggregation: {feed.get('bar_aggregation', 'NOT SET')}")
            print(f"    bar_period: {feed.get('bar_period', 'NOT SET')}")
            print(f"    label: {feed.get('label', 'NOT SET')}")
    else:
        print("\n⚠️  未找到 data_feeds 配置")


def check_raw_data():
    """检查原始数据文件"""
    print("\n" + "=" * 60)
    print("3. 检查原始数据文件")
    print("=" * 60)

    data_dir = project_root / "data" / "top"
    if not data_dir.exists():
        print(f"\n⚠️  数据目录不存在: {data_dir}")
        return

    csv_files = list(data_dir.glob("*_1d.csv"))
    print(f"\n找到 {len(csv_files)} 个日线数据文件")

    if csv_files:
        # 检查第一个文件
        sample_file = csv_files[0]
        print(f"\n检查样本文件: {sample_file.name}")

        df = pd.read_csv(sample_file, nrows=5)
        print(f"\n  列名: {list(df.columns)}")
        print(f"\n  前5行:")
        print(df.to_string(index=False))

        # 验证时间间隔
        if 'timestamp' in df.columns:
            ts1 = df['timestamp'].iloc[0]
            ts2 = df['timestamp'].iloc[1]
            interval_hours = (ts2 - ts1) / 1000 / 3600
            print(f"\n  时间间隔: {interval_hours} 小时")
            if interval_hours == 24:
                print("  ✅ 确认为日线数据 (24小时间隔)")
            else:
                print(f"  ⚠️  警告: 时间间隔不是24小时!")


def check_strategy_subscription():
    """检查策略订阅逻辑"""
    print("\n" + "=" * 60)
    print("4. 检查策略订阅逻辑")
    print("=" * 60)

    strategy_file = project_root / "strategy" / "keltner_rs_breakout.py"

    with open(strategy_file) as f:
        content = f.read()

    # 检查 bar_type 构建
    if "BarType.from_str" in content:
        print("\n✅ 策略使用 BarType.from_str() 构建 bar_type")

    # 检查订阅逻辑
    if "self.subscribe_bars(bar_type)" in content:
        print("✅ 策略订阅 Bar 数据")

    # 检查配置字段
    if 'timeframe: str = ""' in content:
        print("✅ 策略配置包含 timeframe 字段")

    # 检查 bar_type 生成
    if "self.config.bar_type" in content:
        print("✅ 策略使用 self.config.bar_type")
        print("\n  关键代码片段:")
        for line in content.split('\n'):
            if 'bar_type = BarType.from_str' in line or 'self.config.bar_type' in line:
                print(f"    {line.strip()}")


def check_indicator_calculation():
    """检查指标计算逻辑"""
    print("\n" + "=" * 60)
    print("5. 检查指标计算逻辑")
    print("=" * 60)

    strategy_file = project_root / "strategy" / "keltner_rs_breakout.py"

    with open(strategy_file) as f:
        lines = f.readlines()

    # 查找指标初始化
    print("\n指标初始化:")
    for i, line in enumerate(lines):
        if "KeltnerChannel(" in line or "self.keltner =" in line:
            print(f"  行 {i+1}: {line.strip()}")
            # 打印后续几行
            for j in range(1, 5):
                if i+j < len(lines):
                    print(f"  行 {i+j+1}: {lines[i+j].strip()}")
            break

    # 查找指标更新
    print("\n指标更新:")
    for i, line in enumerate(lines):
        if "self.keltner.update(" in line:
            print(f"  行 {i+1}: {line.strip()}")
            break


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("Keltner RS Breakout 策略 - 数据加载检查")
    print("=" * 60)

    try:
        check_config()
        check_data_feeds()
        check_raw_data()
        check_strategy_subscription()
        check_indicator_calculation()

        print("\n" + "=" * 60)
        print("检查完成")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
