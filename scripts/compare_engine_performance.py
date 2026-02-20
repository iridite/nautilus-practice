"""
Engine Performance Comparison

对比高低回测引擎的性能。
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.profiling import BacktestProfiler, ProfileAnalyzer, ProfileReporter
from core.schemas import BacktestConfig
from backtest.engine_high import run_high_level
from backtest.engine_low import run_low_level


def create_test_config() -> BacktestConfig:
    """
    创建测试用的回测配置

    使用较小的数据集和较短的时间范围，以便快速测试。
    """
    # 这里需要根据实际情况创建配置
    # 可以从 YAML 文件加载，或者手动创建

    # 示例：从 YAML 加载
    config_path = project_root / "config" / "strategies" / "keltner_rs_breakout.yaml"

    if config_path.exists():
        cfg = BacktestConfig.from_yaml(str(config_path))
        return cfg
    else:
        raise FileNotFoundError(f"配置文件不存在: {config_path}")


def profile_high_level_engine(cfg: BacktestConfig, base_dir: Path) -> Path:
    """
    分析高级引擎性能

    Args:
        cfg: 回测配置
        base_dir: 项目根目录

    Returns:
        性能数据文件路径
    """
    print("\n" + "=" * 80)
    print("🔍 分析高级引擎性能 (BacktestNode)")
    print("=" * 80)

    profiler = BacktestProfiler()

    try:
        with profiler.profile_with_context("high_level_engine"):
            run_high_level(cfg, base_dir)

        # 打印摘要
        profiler.print_summary(top_n=20)

        # 保存性能数据
        profile_file = profiler.save_stats("high_level_engine.prof")
        print(f"\n✅ 高级引擎性能数据已保存: {profile_file}")

        return profile_file

    except Exception as e:
        print(f"\n❌ 高级引擎分析失败: {e}")
        raise


def profile_low_level_engine(cfg: BacktestConfig, base_dir: Path) -> Path:
    """
    分析低级引擎性能

    Args:
        cfg: 回测配置
        base_dir: 项目根目录

    Returns:
        性能数据文件路径
    """
    print("\n" + "=" * 80)
    print("🔍 分析低级引擎性能 (BacktestEngine)")
    print("=" * 80)

    profiler = BacktestProfiler()

    try:
        with profiler.profile_with_context("low_level_engine"):
            run_low_level(cfg, base_dir)

        # 打印摘要
        profiler.print_summary(top_n=20)

        # 保存性能数据
        profile_file = profiler.save_stats("low_level_engine.prof")
        print(f"\n✅ 低级引擎性能数据已保存: {profile_file}")

        return profile_file

    except Exception as e:
        print(f"\n❌ 低级引擎分析失败: {e}")
        raise


def compare_engines(high_profile: Path, low_profile: Path):
    """
    对比两个引擎的性能

    Args:
        high_profile: 高级引擎性能数据文件
        low_profile: 低级引擎性能数据文件
    """
    print("\n" + "=" * 80)
    print("📊 引擎性能对比")
    print("=" * 80)

    # 加载分析器
    high_analyzer = ProfileAnalyzer(high_profile)
    low_analyzer = ProfileAnalyzer(low_profile)

    # 获取摘要
    high_summary = high_analyzer.stats.total_tt if hasattr(high_analyzer.stats, 'total_tt') else 0
    low_summary = low_analyzer.stats.total_tt if hasattr(low_analyzer.stats, 'total_tt') else 0

    # 获取热点
    high_hotspots = high_analyzer.get_hotspots(10)
    low_hotspots = low_analyzer.get_hotspots(10)

    # 获取瓶颈
    high_bottlenecks = high_analyzer.find_bottlenecks(threshold_pct=5.0)
    low_bottlenecks = low_analyzer.find_bottlenecks(threshold_pct=5.0)

    # 打印对比
    print("\n总体对比:")
    print("-" * 80)
    print(f"高级引擎总耗时: {high_summary:.4f} 秒")
    print(f"低级引擎总耗时: {low_summary:.4f} 秒")

    if high_summary > 0 and low_summary > 0:
        speedup = high_summary / low_summary
        print(f"速度对比: 低级引擎是高级引擎的 {speedup:.2f} 倍")

    print("\n高级引擎性能瓶颈:")
    print("-" * 80)
    for bottleneck in high_bottlenecks[:5]:
        print(f"  {bottleneck['function']:<40} {bottleneck['percentage']:>6.2f}%")

    print("\n低级引擎性能瓶颈:")
    print("-" * 80)
    for bottleneck in low_bottlenecks[:5]:
        print(f"  {bottleneck['function']:<40} {bottleneck['percentage']:>6.2f}%")

    # 生成对比报告
    reporter = ProfileReporter()

    # 高级引擎报告
    high_report = reporter.generate_text_report(
        hotspots=high_hotspots,
        bottlenecks=high_bottlenecks,
        io_operations=high_analyzer.get_io_operations(),
    )
    reporter.save_report(high_report, "high_level_engine_report", format="txt")

    # 低级引擎报告
    low_report = reporter.generate_text_report(
        hotspots=low_hotspots,
        bottlenecks=low_bottlenecks,
        io_operations=low_analyzer.get_io_operations(),
    )
    reporter.save_report(low_report, "low_level_engine_report", format="txt")

    print("\n✅ 详细报告已保存到 output/profiling/")


def main():
    """主函数"""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "回测引擎性能对比测试" + " " * 36 + "║")
    print("╚" + "=" * 78 + "╝")
    print()

    base_dir = project_root

    try:
        # 创建测试配置
        print("📋 加载回测配置...")
        cfg = create_test_config()
        print(f"✅ 配置加载成功: {cfg.strategy.name}")

        # 分析高级引擎
        high_profile = profile_high_level_engine(cfg, base_dir)

        # 分析低级引擎
        low_profile = profile_low_level_engine(cfg, base_dir)

        # 对比结果
        compare_engines(high_profile, low_profile)

        print("\n" + "=" * 80)
        print("✅ 性能对比测试完成！")
        print("=" * 80)
        print()
        print("📁 结果文件:")
        print(f"  - 高级引擎性能数据: {high_profile}")
        print(f"  - 低级引擎性能数据: {low_profile}")
        print("  - 高级引擎报告: output/profiling/high_level_engine_report.txt")
        print("  - 低级引擎报告: output/profiling/low_level_engine_report.txt")
        print()

    except FileNotFoundError as e:
        print(f"\n❌ 错误: {e}")
        print("\n💡 提示:")
        print("  请确保配置文件存在，或者修改 create_test_config() 函数")
        print("  来创建适合你的测试配置。")
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
