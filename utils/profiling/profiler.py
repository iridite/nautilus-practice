"""
Backtest Profiler

回测性能分析器，使用 cProfile 分析回测过程的性能瓶颈。
"""

import cProfile
import pstats
import io
import time
from pathlib import Path
from typing import Callable, Any, Dict
from datetime import datetime


class BacktestProfiler:
    """
    回测性能分析器

    使用 cProfile 分析回测过程，生成详细的性能报告。
    """

    def __init__(self, output_dir: Path | None = None):
        """
        初始化性能分析器

        Args:
            output_dir: 输出目录（默认为 output/profiling）
        """
        self.output_dir = output_dir or Path("output/profiling")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.profiler = cProfile.Profile()
        self.start_time = None
        self.end_time = None
        self.stats = None

    def profile_function(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> tuple[Any, pstats.Stats]:
        """
        分析单个函数的性能

        Args:
            func: 要分析的函数
            *args: 函数参数
            **kwargs: 函数关键字参数

        Returns:
            (函数返回值, 性能统计对象)
        """
        self.start_time = time.time()

        # 启动性能分析
        self.profiler.enable()

        try:
            result = func(*args, **kwargs)
        finally:
            # 停止性能分析
            self.profiler.disable()
            self.end_time = time.time()

        # 生成统计信息
        self.stats = pstats.Stats(self.profiler)

        return result, self.stats

    def save_stats(self, filename: str | None = None) -> Path:
        """
        保存性能统计数据到文件

        Args:
            filename: 文件名（默认自动生成）

        Returns:
            保存的文件路径
        """
        if self.stats is None:
            raise ValueError("No profiling data available. Run profile_function first.")

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"profile_{timestamp}.prof"

        filepath = self.output_dir / filename
        self.profiler.dump_stats(str(filepath))

        return filepath

    def get_stats_string(
        self,
        sort_by: str = "cumulative",
        top_n: int = 50
    ) -> str:
        """
        获取性能统计的字符串表示

        Args:
            sort_by: 排序方式（cumulative, time, calls 等）
            top_n: 显示前 N 个函数

        Returns:
            格式化的统计字符串
        """
        if self.stats is None:
            raise ValueError("No profiling data available. Run profile_function first.")

        # 创建字符串缓冲区
        stream = io.StringIO()

        # 输出统计信息到缓冲区
        stats = pstats.Stats(self.profiler, stream=stream)
        stats.strip_dirs()
        stats.sort_stats(sort_by)
        stats.print_stats(top_n)

        return stream.getvalue()

    def get_function_stats(self, top_n: int = 20) -> list[Dict[str, Any]]:
        """
        获取函数级别的性能统计

        Args:
            top_n: 返回前 N 个最耗时的函数

        Returns:
            函数统计列表
        """
        if self.stats is None:
            raise ValueError("No profiling data available. Run profile_function first.")

        # 按累计时间排序
        self.stats.sort_stats("cumulative")

        function_stats = []
        for func, (cc, nc, tt, ct, callers) in list(self.stats.stats.items())[:top_n]:
            filename, line, func_name = func

            function_stats.append({
                "function": func_name,
                "filename": filename,
                "line": line,
                "calls": nc,
                "total_time": tt,
                "cumulative_time": ct,
                "time_per_call": tt / nc if nc > 0 else 0,
                "cumulative_per_call": ct / nc if nc > 0 else 0,
            })

        return function_stats

    def get_summary(self) -> Dict[str, Any]:
        """
        获取性能分析摘要

        Returns:
            包含总体统计的字典
        """
        if self.stats is None or self.start_time is None or self.end_time is None:
            raise ValueError("No profiling data available. Run profile_function first.")

        total_time = self.end_time - self.start_time

        # 统计总调用次数和总时间
        total_calls = sum(stat[1] for stat in self.stats.stats.values())
        total_primitive_calls = sum(stat[0] for stat in self.stats.stats.values())

        return {
            "total_elapsed_time": total_time,
            "total_calls": total_calls,
            "total_primitive_calls": total_primitive_calls,
            "unique_functions": len(self.stats.stats),
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "end_time": datetime.fromtimestamp(self.end_time).isoformat(),
        }

    def print_summary(self, top_n: int = 20):
        """
        打印性能分析摘要

        Args:
            top_n: 显示前 N 个最耗时的函数
        """
        summary = self.get_summary()

        print("\n" + "=" * 80)
        print("性能分析摘要")
        print("=" * 80)
        print(f"总耗时:           {summary['total_elapsed_time']:.4f} 秒")
        print(f"总调用次数:       {summary['total_calls']:,}")
        print(f"原始调用次数:     {summary['total_primitive_calls']:,}")
        print(f"唯一函数数量:     {summary['unique_functions']:,}")
        print(f"开始时间:         {summary['start_time']}")
        print(f"结束时间:         {summary['end_time']}")
        print("=" * 80)

        print(f"\n前 {top_n} 个最耗时的函数:")
        print("-" * 80)

        function_stats = self.get_function_stats(top_n)

        print(f"{'函数名':<40} {'调用次数':>10} {'累计时间':>12} {'单次时间':>12}")
        print("-" * 80)

        for stat in function_stats:
            print(
                f"{stat['function']:<40} "
                f"{stat['calls']:>10,} "
                f"{stat['cumulative_time']:>12.4f} "
                f"{stat['cumulative_per_call']:>12.6f}"
            )

        print("=" * 80 + "\n")

    def compare_runs(
        self,
        func: Callable,
        configs: list[tuple[str, tuple, dict]],
    ) -> Dict[str, Any]:
        """
        对比多次运行的性能

        Args:
            func: 要分析的函数
            configs: 配置列表，每个元素为 (名称, args, kwargs)

        Returns:
            对比结果字典
        """
        results = {}

        for name, args, kwargs in configs:
            print(f"\n运行配置: {name}")
            print("-" * 80)

            profiler = BacktestProfiler(self.output_dir)
            _, stats = profiler.profile_function(func, *args, **kwargs)

            summary = profiler.get_summary()
            function_stats = profiler.get_function_stats(10)

            results[name] = {
                "summary": summary,
                "top_functions": function_stats,
            }

            print(f"总耗时: {summary['total_elapsed_time']:.4f} 秒")

        return results

    def profile_with_context(self, name: str = "backtest"):
        """
        使用上下文管理器进行性能分析

        Args:
            name: 分析名称

        Example:
            profiler = BacktestProfiler()
            with profiler.profile_with_context("my_backtest"):
                run_backtest()
            profiler.print_summary()
        """
        return _ProfileContext(self, name)


class _ProfileContext:
    """性能分析上下文管理器"""

    def __init__(self, profiler: BacktestProfiler, name: str):
        self.profiler = profiler
        self.name = name

    def __enter__(self):
        self.profiler.start_time = time.time()
        self.profiler.profiler.enable()
        return self.profiler

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.profiler.profiler.disable()
        self.profiler.end_time = time.time()
        self.profiler.stats = pstats.Stats(self.profiler.profiler)

        # 自动保存
        filepath = self.profiler.save_stats(f"{self.name}.prof")
        print(f"\n性能分析数据已保存到: {filepath}")

        return False
