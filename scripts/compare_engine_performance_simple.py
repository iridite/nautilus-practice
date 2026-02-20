"""
简化版引擎性能对比脚本

使用最小配置测试高低回测引擎的性能差异。
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 直接导入 profiling 模块，避免导入整个 utils 包
sys.path.insert(0, str(project_root / "utils" / "profiling"))
from profiler import BacktestProfiler
from analyzer import ProfileAnalyzer
from reporter import ProfileReporter


def create_minimal_test():
    """
    创建一个最小的性能测试

    模拟回测引擎的主要操作：
    1. 数据加载
    2. 指标计算
    3. 信号生成
    """
    import pandas as pd
    import numpy as np
    import time

    print("模拟回测过程...")

    # 模拟数据加载（CSV 读取）
    data_size = 10000
    data = pd.DataFrame({
        'timestamp': pd.date_range('2023-01-01', periods=data_size, freq='1h'),
        'open': np.random.randn(data_size).cumsum() + 100,
        'high': np.random.randn(data_size).cumsum() + 102,
        'low': np.random.randn(data_size).cumsum() + 98,
        'close': np.random.randn(data_size).cumsum() + 100,
        'volume': np.random.randint(1000, 10000, data_size),
    })

    # 模拟指标计算
    data['sma_20'] = data['close'].rolling(20).mean()
    data['sma_50'] = data['close'].rolling(50).mean()
    data['sma_200'] = data['close'].rolling(200).mean()
    data['ema_20'] = data['close'].ewm(span=20).mean()
    data['std_20'] = data['close'].rolling(20).std()

    # 模拟 ATR 计算
    data['tr'] = np.maximum(
        data['high'] - data['low'],
        np.maximum(
            abs(data['high'] - data['close'].shift(1)),
            abs(data['low'] - data['close'].shift(1))
        )
    )
    data['atr'] = data['tr'].rolling(20).mean()

    # 模拟信号生成
    data['signal'] = 0
    data.loc[data['sma_20'] > data['sma_50'], 'signal'] = 1
    data.loc[data['sma_20'] < data['sma_50'], 'signal'] = -1

    # 模拟一些延迟
    time.sleep(0.1)

    return len(data)


def profile_simulated_high_level():
    """模拟高级引擎的性能特征"""
    print("\n" + "=" * 80)
    print("🔍 模拟高级引擎性能测试")
    print("=" * 80)

    profiler = BacktestProfiler()

    def simulated_high_level():
        # 高级引擎特点：更多的���据验证和转换
        import time

        # 模拟 Parquet 转换
        print("  - 检查 Parquet 数据...")
        time.sleep(0.05)

        # 模拟数据验证
        print("  - 验证数据一致性...")
        time.sleep(0.03)

        # 执行回测
        print("  - 执行回测...")
        result = create_minimal_test()

        return result

    with profiler.profile_with_context("simulated_high_level"):
        result = simulated_high_level()

    print(f"\n✅ 处理了 {result} 条数据")
    profiler.print_summary(top_n=15)

    return profiler.save_stats("simulated_high_level.prof")


def profile_simulated_low_level():
    """模拟低级引擎的性能特征"""
    print("\n" + "=" * 80)
    print("🔍 模拟低级引擎性能测试")
    print("=" * 80)

    profiler = BacktestProfiler()

    def simulated_low_level():
        # 低级引擎特点：更直接的数据加载
        import time

        # 直接加载数据
        print("  - 直接加载数据...")
        time.sleep(0.02)

        # 执行回测
        print("  - 执行回测...")
        result = create_minimal_test()

        return result

    with profiler.profile_with_context("simulated_low_level"):
        result = simulated_low_level()

    print(f"\n✅ 处理了 {result} 条数据")
    profiler.print_summary(top_n=15)

    return profiler.save_stats("simulated_low_level.prof")


def compare_results(high_profile: Path, low_profile: Path):
    """对比两个引擎的性能"""
    print("\n" + "=" * 80)
    print("📊 性能对比分析")
    print("=" * 80)

    # 加载分析器
    high_analyzer = ProfileAnalyzer(high_profile)
    low_analyzer = ProfileAnalyzer(low_profile)

    # 获取热点
    high_hotspots = high_analyzer.get_hotspots(15)
    low_hotspots = low_analyzer.get_hotspots(15)

    # 获取瓶颈
    high_bottlenecks = high_analyzer.find_bottlenecks(threshold_pct=3.0)
    low_bottlenecks = low_analyzer.find_bottlenecks(threshold_pct=3.0)

    # 计算总时间
    high_total_time = sum(h['cumulative_time'] for h in high_hotspots[:5])
    low_total_time = sum(h['cumulative_time'] for h in low_hotspots[:5])

    print("\n📈 总体对比:")
    print("-" * 80)
    print(f"高级引擎前5个热点总耗时: {high_total_time:.4f} 秒")
    print(f"低级引擎前5个热点总耗时: {low_total_time:.4f} 秒")

    if high_total_time > 0 and low_total_time > 0:
        if high_total_time > low_total_time:
            speedup = high_total_time / low_total_time
            print(f"速度对比: 低级引擎比高级引擎快 {speedup:.2f} 倍")
        else:
            speedup = low_total_time / high_total_time
            print(f"速度对比: 高级引擎比低级引擎快 {speedup:.2f} 倍")

    print("\n🔥 高级引擎性能热点:")
    print("-" * 80)
    for i, hotspot in enumerate(high_hotspots[:10], 1):
        print(f"{i:2d}. {hotspot['function']:<40} {hotspot['cumulative_time']:>8.4f}s ({hotspot['percentage']:>5.2f}%)")

    print("\n🔥 低级引擎性能热点:")
    print("-" * 80)
    for i, hotspot in enumerate(low_hotspots[:10], 1):
        print(f"{i:2d}. {hotspot['function']:<40} {hotspot['cumulative_time']:>8.4f}s ({hotspot['percentage']:>5.2f}%)")

    if high_bottlenecks:
        print("\n⚠️  高级引擎性能瓶颈 (>3%):")
        print("-" * 80)
        for bottleneck in high_bottlenecks[:5]:
            print(f"  {bottleneck['function']:<40} {bottleneck['percentage']:>6.2f}%")

    if low_bottlenecks:
        print("\n⚠️  低级引擎性能瓶颈 (>3%):")
        print("-" * 80)
        for bottleneck in low_bottlenecks[:5]:
            print(f"  {bottleneck['function']:<40} {bottleneck['percentage']:>6.2f}%")

    # 生成报告
    reporter = ProfileReporter()

    high_report = reporter.generate_text_report(
        hotspots=high_hotspots,
        bottlenecks=high_bottlenecks,
        io_operations=high_analyzer.get_io_operations(),
    )
    high_report_file = reporter.save_report(high_report, "simulated_high_level_report", format="txt")

    low_report = reporter.generate_text_report(
        hotspots=low_hotspots,
        bottlenecks=low_bottlenecks,
        io_operations=low_analyzer.get_io_operations(),
    )
    low_report_file = reporter.save_report(low_report, "simulated_low_level_report", format="txt")

    print(f"\n✅ 详细报告已保存:")
    print(f"  - 高级引擎: {high_report_file}")
    print(f"  - 低级引擎: {low_report_file}")


def main():
    """主函数"""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "回测引擎性能对比测试（模拟）" + " " * 30 + "║")
    print("╚" + "=" * 78 + "╝")
    print()
    print("💡 说明：")
    print("  这是一个模拟测试，用于演示性能分析工具的使用。")
    print("  实际的引擎性能对比需要真实的回测配置和数据。")
    print()

    try:
        # 模拟高级引擎
        high_profile = profile_simulated_high_level()

        # 模拟低级引擎
        low_profile = profile_simulated_low_level()

        # 对比结果
        compare_results(high_profile, low_profile)

        print("\n" + "=" * 80)
        print("✅ 性能对比测试完成！")
        print("=" * 80)
        print()
        print("📁 结果文件:")
        print(f"  - 高级引擎性能数据: {high_profile}")
        print(f"  - 低级引擎性能数据: {low_profile}")
        print(f"  - 详细报告: output/profiling/")
        print()
        print("💡 下一步:")
        print("  1. 查看生成的报告文件")
        print("  2. 使用真实的回测配置运行实际测试")
        print("  3. 根据瓶颈分析结果优化代码")
        print()

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
