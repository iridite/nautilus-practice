"""
真实回测引擎性能对比

使用实际的回测配置对比高低引擎的性能。
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 直接导入 profiling 模块
sys.path.insert(0, str(project_root / "utils" / "profiling"))
from profiler import BacktestProfiler
from analyzer import ProfileAnalyzer
from reporter import ProfileReporter

# 导入回测相关模块
from core.adapter import get_adapter
from cli.commands import run_backtest
import argparse


def create_backtest_args(engine_type: str):
    """创建回测参数"""
    args = argparse.Namespace()
    args.command = "backtest"
    args.type = engine_type  # "high" 或 "low"
    args.skip_data_check = True  # 跳过数据检查以加快速度
    args.skip_oi_data = True  # 跳过 OI 数据
    args.force_oi_fetch = False
    args.oi_exchange = "auto"
    args.max_retries = 3
    return args


def profile_real_backtest(engine_type: str, base_dir: Path):
    """
    分析真实回测的性能

    Args:
        engine_type: 引擎类型（"high" 或 "low"）
        base_dir: 项目根目录

    Returns:
        性能数据文件路径
    """
    print("\n" + "=" * 80)
    print(f"🔍 分析 {engine_type.upper()} 级引擎性能（真实回测）")
    print("=" * 80)

    profiler = BacktestProfiler()
    args = create_backtest_args(engine_type)
    adapter = get_adapter()

    try:
        with profiler.profile_with_context(f"real_{engine_type}_level_engine"):
            # 运行真实回测
            run_backtest(args, adapter, base_dir)

        # 打印摘要
        profiler.print_summary(top_n=30)

        # 保存性能数据
        profile_file = profiler.save_stats(f"real_{engine_type}_level_engine.prof")
        print(f"\n✅ {engine_type.upper()} 级引擎性能数据已保存: {profile_file}")

        return profile_file

    except Exception as e:
        print(f"\n❌ {engine_type.upper()} 级引擎分析失败: {e}")
        import traceback
        traceback.print_exc()
        raise


def compare_real_engines(high_profile: Path, low_profile: Path):
    """
    对比两个引擎的真实性能

    Args:
        high_profile: 高级引擎性能数据文件
        low_profile: 低级引擎性能数据文件
    """
    print("\n" + "=" * 80)
    print("📊 真实回测引擎性能对比")
    print("=" * 80)

    # 加载分析器
    high_analyzer = ProfileAnalyzer(high_profile)
    low_analyzer = ProfileAnalyzer(low_profile)

    # 获取热点
    high_hotspots = high_analyzer.get_hotspots(30)
    low_hotspots = low_analyzer.get_hotspots(30)

    # 获取瓶颈
    high_bottlenecks = high_analyzer.find_bottlenecks(threshold_pct=3.0)
    low_bottlenecks = low_analyzer.find_bottlenecks(threshold_pct=3.0)

    # 获取 I/O 操作
    high_io = high_analyzer.get_io_operations()
    low_io = low_analyzer.get_io_operations()

    # 计算总时间
    high_total_time = sum(h['cumulative_time'] for h in high_hotspots[:10])
    low_total_time = sum(h['cumulative_time'] for h in low_hotspots[:10])

    print("\n📈 总体对比:")
    print("-" * 80)
    print(f"高级引擎前10个热点总耗时: {high_total_time:.4f} 秒")
    print(f"低级引擎前10个热点总耗时: {low_total_time:.4f} 秒")

    if high_total_time > 0 and low_total_time > 0:
        if high_total_time > low_total_time:
            speedup = high_total_time / low_total_time
            print(f"速度对比: 低级引擎比高级引擎快 {speedup:.2f} 倍")
        else:
            speedup = low_total_time / high_total_time
            print(f"速度对比: 高级引擎比低级引擎快 {speedup:.2f} 倍")

    print("\n🔥 高级引擎性能热点（前 20 个）:")
    print("-" * 80)
    for i, hotspot in enumerate(high_hotspots[:20], 1):
        print(f"{i:2d}. {hotspot['function']:<50} {hotspot['cumulative_time']:>8.4f}s ({hotspot['percentage']:>5.2f}%)")

    print("\n🔥 低级引擎性能热点（前 20 个）:")
    print("-" * 80)
    for i, hotspot in enumerate(low_hotspots[:20], 1):
        print(f"{i:2d}. {hotspot['function']:<50} {hotspot['cumulative_time']:>8.4f}s ({hotspot['percentage']:>5.2f}%)")

    if high_bottlenecks:
        print("\n⚠️  高级引擎性能瓶颈 (>3%):")
        print("-" * 80)
        for bottleneck in high_bottlenecks[:10]:
            print(f"  {bottleneck['function']:<50} {bottleneck['percentage']:>6.2f}%")

    if low_bottlenecks:
        print("\n⚠️  低级引擎性能瓶颈 (>3%):")
        print("-" * 80)
        for bottleneck in low_bottlenecks[:10]:
            print(f"  {bottleneck['function']:<50} {bottleneck['percentage']:>6.2f}%")

    if high_io:
        print("\n💾 高级引擎 I/O 操作（前 10 个）:")
        print("-" * 80)
        for op in high_io[:10]:
            print(f"  {op['function']:<50} {op['calls']:>6} 次 ({op['cumulative_time']:.4f}s)")

    if low_io:
        print("\n💾 低级引擎 I/O 操作（前 10 个）:")
        print("-" * 80)
        for op in low_io[:10]:
            print(f"  {op['function']:<50} {op['calls']:>6} 次 ({op['cumulative_time']:.4f}s)")

    # 生成报告
    reporter = ProfileReporter()

    high_report = reporter.generate_text_report(
        hotspots=high_hotspots,
        bottlenecks=high_bottlenecks,
        io_operations=high_io,
    )
    high_report_file = reporter.save_report(high_report, "real_high_level_engine_report", format="txt")

    low_report = reporter.generate_text_report(
        hotspots=low_hotspots,
        bottlenecks=low_bottlenecks,
        io_operations=low_io,
    )
    low_report_file = reporter.save_report(low_report, "real_low_level_engine_report", format="txt")

    # 生成 Markdown 报告
    high_md = reporter.generate_markdown_report(
        hotspots=high_hotspots,
        bottlenecks=high_bottlenecks,
        io_operations=high_io,
    )
    reporter.save_report(high_md, "real_high_level_engine_report", format="md")

    low_md = reporter.generate_markdown_report(
        hotspots=low_hotspots,
        bottlenecks=low_bottlenecks,
        io_operations=low_io,
    )
    reporter.save_report(low_md, "real_low_level_engine_report", format="md")

    print(f"\n✅ 详细报告已保存:")
    print(f"  - 高级引擎: {high_report_file}")
    print(f"  - 低级引擎: {low_report_file}")


def main():
    """主函数"""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "真实回测引擎性能对比" + " " * 36 + "║")
    print("╚" + "=" * 78 + "╝")
    print()
    print("💡 说明：")
    print("  使用实际的回测配置对比高低引擎的性能。")
    print("  这将运行真实的回测，可能需要几分钟时间。")
    print()

    base_dir = project_root

    try:
        # 分析高级引擎
        print("📋 步骤 1/3: 分析高级引擎...")
        high_profile = profile_real_backtest("high", base_dir)

        # 分析低级引擎
        print("\n📋 步骤 2/3: 分析低级引擎...")
        low_profile = profile_real_backtest("low", base_dir)

        # 对比结果
        print("\n📋 步骤 3/3: 对比分析结果...")
        compare_real_engines(high_profile, low_profile)

        print("\n" + "=" * 80)
        print("✅ 真实回测性能对比完成！")
        print("=" * 80)
        print()
        print("📁 结果文件:")
        print(f"  - 高级引擎性能数据: {high_profile}")
        print(f"  - 低级引擎性能数据: {low_profile}")
        print(f"  - 详细报告: output/profiling/real_*_report.txt")
        print(f"  - Markdown 报告: output/profiling/real_*_report.md")
        print()

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
