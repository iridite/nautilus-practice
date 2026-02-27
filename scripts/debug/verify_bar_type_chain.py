#!/usr/bin/env python3
"""
验证 bar_type 生成链路，确保 timeframe: "1d" 正确转换为 DAY 聚合
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from nautilus_trader.model.enums import BarAggregation
from core.loader import ConfigLoader
from core.adapter import ConfigAdapter
from utils.symbol_parser import parse_timeframe
from utils.instrument_helpers import build_bar_type_from_timeframe


def test_parse_timeframe():
    """测试 parse_timeframe 函数"""
    print("\n" + "=" * 60)
    print("1. 测试 parse_timeframe() 函数")
    print("=" * 60)

    test_cases = [
        ("1d", BarAggregation.DAY, 1),
        ("1h", BarAggregation.HOUR, 1),
        ("5m", BarAggregation.MINUTE, 5),
        ("1w", BarAggregation.WEEK, 1),
    ]

    for timeframe, expected_agg, expected_period in test_cases:
        agg, period = parse_timeframe(timeframe)
        status = "✅" if (agg == expected_agg and period == expected_period) else "❌"
        print(f"  {status} parse_timeframe('{timeframe}') -> ({agg.name}, {period})")
        if agg != expected_agg or period != expected_period:
            print(f"      期望: ({expected_agg.name}, {expected_period})")


def test_build_bar_type():
    """测试 build_bar_type_from_timeframe 函数"""
    print("\n" + "=" * 60)
    print("2. 测试 build_bar_type_from_timeframe() 函数")
    print("=" * 60)

    test_cases = [
        ("BTCUSDT-PERP.BINANCE", "1d", "BTCUSDT-PERP.BINANCE-1-DAY-LAST-EXTERNAL"),
        ("ETHUSDT-PERP.BINANCE", "1h", "ETHUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL"),
        ("SOLUSDT-PERP.BINANCE", "5m", "SOLUSDT-PERP.BINANCE-5-MINUTE-LAST-EXTERNAL"),
    ]

    for instrument_id, timeframe, expected_bar_type in test_cases:
        bar_type = build_bar_type_from_timeframe(instrument_id, timeframe)
        status = "✅" if bar_type == expected_bar_type else "❌"
        print(f"  {status} build_bar_type_from_timeframe('{instrument_id}', '{timeframe}')")
        print(f"      结果: {bar_type}")
        if bar_type != expected_bar_type:
            print(f"      期望: {expected_bar_type}")


def test_config_adapter():
    """测试 ConfigAdapter 的 bar_type 生成"""
    print("\n" + "=" * 60)
    print("3. 测试 ConfigAdapter.create_data_config()")
    print("=" * 60)

    adapter = ConfigAdapter()

    # 测试创建数据配置
    data_config = adapter.create_data_config("BTCUSDT", "1d", "main")

    print(f"\n  输入: symbol='BTCUSDT', timeframe='1d'")
    print(f"  输出:")
    print(f"    csv_file_name: {data_config.csv_file_name}")
    print(f"    bar_aggregation: {data_config.bar_aggregation.name}")
    print(f"    bar_period: {data_config.bar_period}")
    print(f"    bar_type_str: {data_config.bar_type_str}")

    # 验证
    if data_config.bar_aggregation == BarAggregation.DAY and data_config.bar_period == 1:
        print(f"\n  ✅ 正确: timeframe='1d' 转换为 DAY 聚合")
    else:
        print(f"\n  ❌ 错误: 期望 DAY/1, 实际 {data_config.bar_aggregation.name}/{data_config.bar_period}")


def test_strategy_config():
    """测试策略配置中的 timeframe 和 bar_type"""
    print("\n" + "=" * 60)
    print("4. 测试策略配置的 timeframe 和 bar_type")
    print("=" * 60)

    adapter = ConfigAdapter()
    strategy_config = adapter.strategy_config

    print(f"\n  策略配置 (keltner_rs_breakout.yaml):")
    print(f"    timeframe: {strategy_config.parameters.get('timeframe', 'NOT SET')}")

    # 检查 bar_type 是否会被自动生成
    strategy_params = strategy_config.parameters

    if "bar_type" in strategy_params:
        print(f"    bar_type (自动生成): {strategy_params['bar_type']}")

        # 验证 bar_type 是否包含 DAY
        if "-DAY-" in strategy_params["bar_type"]:
            print(f"\n  ✅ 正确: bar_type 包含 DAY 聚合")
        else:
            print(f"\n  ❌ 错误: bar_type 不包含 DAY 聚合")
    else:
        print(f"    bar_type: NOT SET (将在运行时生成)")


def test_backtest_data_loading():
    """测试回测引擎的数据加载配置"""
    print("\n" + "=" * 60)
    print("5. 测试回测引擎数据加载配置")
    print("=" * 60)

    loader = ConfigLoader(project_root / "config")
    adapter = ConfigAdapter(loader, "dev", "keltner_rs_breakout")

    # 获取回测配置
    backtest_config = adapter.get_backtest_config()

    print(f"\n  回测配置:")
    print(f"    时间范围: {backtest_config.start_date} 至 {backtest_config.end_date}")
    print(f"    数据源数量: {len(backtest_config.data_feeds)}")

    if backtest_config.data_feeds:
        print(f"\n  数据源详情:")
        for i, feed in enumerate(backtest_config.data_feeds[:3]):  # 只显示前3个
            print(f"\n    数据源 {i+1}:")
            print(f"      csv_file_name: {feed.csv_file_name}")
            print(f"      bar_aggregation: {feed.bar_aggregation.name}")
            print(f"      bar_period: {feed.bar_period}")
            print(f"      bar_type_str: {feed.bar_type_str}")
            print(f"      label: {feed.label}")

            # 验证
            if feed.bar_aggregation == BarAggregation.DAY:
                print(f"      ✅ 使用 DAY 聚合")
            else:
                print(f"      ❌ 警告: 使用 {feed.bar_aggregation.name} 聚合 (期望 DAY)")

        if len(backtest_config.data_feeds) > 3:
            print(f"\n    ... 还有 {len(backtest_config.data_feeds) - 3} 个数据源")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("Bar Type 生成链路验证")
    print("=" * 60)
    print("\n目标: 验证 timeframe='1d' 正确转换为 BarAggregation.DAY")

    try:
        test_parse_timeframe()
        test_build_bar_type()
        test_config_adapter()
        test_strategy_config()
        test_backtest_data_loading()

        print("\n" + "=" * 60)
        print("验证完成")
        print("=" * 60)
        print("\n结论:")
        print("  如果所有测试都显示 ✅，则说明策略严格使用日线数据")
        print("  如果有 ❌，则需要检查对应的配置或代码")

    except Exception as e:
        print(f"\n❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
