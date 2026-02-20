"""
使用示例：性能分析工具

演示如何使用性能分析工具来分析回测引擎的性能。
"""

from pathlib import Path
from utils.profiling import BacktestProfiler, ProfileAnalyzer, ProfileReporter


def example_1_profile_function():
    """示例 1：分析单个函数的性能"""
    print("=" * 80)
    print("示例 1：分析单个函数的性能")
    print("=" * 80)

    # 创建性能分析器
    profiler = BacktestProfiler()

    # 定义要分析的函数
    def slow_function():
        """一个模拟的慢函数"""
        import time
        total = 0
        for i in range(1000000):
            total += i
        time.sleep(0.1)
        return total

    # 分析函数性能
    result, stats = profiler.profile_function(slow_function)

    # 打印摘要
    profiler.print_summary(top_n=10)

    # 保存性能数据
    filepath = profiler.save_stats("example_1.prof")
    print(f"性能数据已保存到: {filepath}")


def example_2_profile_with_context():
    """示例 2：使用上下文管理器分析代码块"""
    print("\n" + "=" * 80)
    print("示例 2：使用上下文管理器分析代码块")
    print("=" * 80)

    profiler = BacktestProfiler()

    # 使用上下文管理器
    with profiler.profile_with_context("example_2"):
        # 模拟回测过程
        import time
        import pandas as pd
        import numpy as np

        # 模拟数据加载
        data = pd.DataFrame({
            'close': np.random.randn(10000),
            'volume': np.random.randint(1000, 10000, 10000)
        })

        # 模拟计算
        data['sma'] = data['close'].rolling(20).mean()
        data['std'] = data['close'].rolling(20).std()

        time.sleep(0.1)

    # 打印摘要
    profiler.print_summary(top_n=15)


def example_3_analyze_profile_file():
    """示例 3：分析已有的性能数据文件"""
    print("\n" + "=" * 80)
    print("示例 3：分析已有的性能数据文件")
    print("=" * 80)

    # 首先生成一个性能数据文件
    profiler = BacktestProfiler()

    def sample_function():
        import pandas as pd
        import numpy as np
        data = pd.DataFrame(np.random.randn(5000, 10))
        result = data.sum().sum()
        return result

    profiler.profile_function(sample_function)
    profile_file = profiler.save_stats("example_3.prof")

    # 使用分析器分析
    analyzer = ProfileAnalyzer(profile_file)

    # 打印摘要
    analyzer.print_summary(top_n=15)

    # 获取性能热点
    hotspots = analyzer.get_hotspots(10)
    print("\n性能热点详情:")
    for i, hotspot in enumerate(hotspots, 1):
        print(f"{i}. {hotspot['function']}: {hotspot['cumulative_time']:.4f}s")

    # 查找瓶颈
    bottlenecks = analyzer.find_bottlenecks(threshold_pct=5.0)
    print(f"\n发现 {len(bottlenecks)} 个性能瓶颈")

    # 导出到 JSON
    json_file = Path("output/profiling/example_3.json")
    analyzer.export_to_json(json_file)
    print(f"\n分析结果已导出到: {json_file}")


def example_4_generate_report():
    """示例 4：生成性能分析报告"""
    print("\n" + "=" * 80)
    print("示例 4：生成性能分析报告")
    print("=" * 80)

    # 生成性能数据
    profiler = BacktestProfiler()

    def complex_function():
        import pandas as pd
        import numpy as np

        # 模拟复杂计算
        data = pd.DataFrame(np.random.randn(10000, 5))
        data['sma_20'] = data[0].rolling(20).mean()
        data['sma_50'] = data[0].rolling(50).mean()
        data['std'] = data[0].rolling(20).std()

        # 模拟条件筛选
        filtered = data[data['sma_20'] > data['sma_50']]

        return len(filtered)

    profiler.profile_function(complex_function)
    profile_file = profiler.save_stats("example_4.prof")

    # 分析性能数据
    analyzer = ProfileAnalyzer(profile_file)
    hotspots = analyzer.get_hotspots(20)
    bottlenecks = analyzer.find_bottlenecks(threshold_pct=5.0)
    io_operations = analyzer.get_io_operations()
    summary = profiler.get_summary()

    # 生成报告
    reporter = ProfileReporter()

    # 生成文本报告
    text_report = reporter.generate_text_report(
        hotspots=hotspots,
        bottlenecks=bottlenecks,
        io_operations=io_operations,
        summary=summary,
    )
    print(text_report)

    # 保存文本报告
    text_file = reporter.save_report(text_report, "example_4_report", format="txt")
    print(f"\n文本报告已保存到: {text_file}")

    # 生成 Markdown 报告
    md_report = reporter.generate_markdown_report(
        hotspots=hotspots,
        bottlenecks=bottlenecks,
        io_operations=io_operations,
        summary=summary,
    )
    md_file = reporter.save_report(md_report, "example_4_report", format="md")
    print(f"Markdown ���告已保存到: {md_file}")


def example_5_profile_backtest():
    """示例 5：分析实际回测（示例）"""
    print("\n" + "=" * 80)
    print("示例 5：分析实际回测（示例）")
    print("=" * 80)

    print("""
要分析实际回测，可以这样使用：

```python
from utils.profiling import BacktestProfiler
from backtest.engine_high import run_high_level
from core.schemas import BacktestConfig

# 创建性能分析器
profiler = BacktestProfiler()

# 加载回测配置
cfg = BacktestConfig.from_yaml("config/backtest/my_strategy.yaml")

# 使用上下文管理器分析回测
with profiler.profile_with_context("my_strategy_backtest"):
    run_high_level(cfg, Path.cwd())

# 打印摘要
profiler.print_summary(top_n=30)

# 生成报告
from utils.profiling import ProfileAnalyzer, ProfileReporter

analyzer = ProfileAnalyzer("output/profiling/my_strategy_backtest.prof")
reporter = ProfileReporter()

hotspots = analyzer.get_hotspots(30)
bottlenecks = analyzer.find_bottlenecks(threshold_pct=3.0)
io_operations = analyzer.get_io_operations()

report = reporter.generate_text_report(
    hotspots=hotspots,
    bottlenecks=bottlenecks,
    io_operations=io_operations,
)

print(report)
```

这样就可以找出回测过程中的性能瓶颈了！
    """)


def main():
    """运行所有示例"""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "性能分析工具使用示例" + " " * 36 + "║")
    print("╚" + "=" * 78 + "╝")
    print()

    # 运行示例
    example_1_profile_function()
    example_2_profile_with_context()
    example_3_analyze_profile_file()
    example_4_generate_report()
    example_5_profile_backtest()

    print("\n" + "=" * 80)
    print("所有示例运行完成！")
    print("=" * 80)
    print()
    print("💡 提示：")
    print("  1. 使用 BacktestProfiler 分析函数或代码块的性能")
    print("  2. 使用 ProfileAnalyzer 分析已有的性能数据文件")
    print("  3. 使用 ProfileReporter 生成格式化的报告")
    print("  4. 性能数据保存在 output/profiling/ 目录")
    print()


if __name__ == "__main__":
    main()
