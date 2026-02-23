"""
Profile Analyzer

性能分析结果分析器，用于分析和可视化性能数据。
"""

import pstats
from pathlib import Path
from typing import Dict, Any, List
import json


class ProfileAnalyzer:
    """
    性能分析结果分析器

    加载和分析 cProfile 生成的性能数据。
    """

    def __init__(self, profile_file: Path | str):
        """
        初始化分析器

        Args:
            profile_file: 性能数据文件路径
        """
        self.profile_file = Path(profile_file)
        if not self.profile_file.exists():
            raise FileNotFoundError(f"Profile file not found: {profile_file}")

        self.stats = pstats.Stats(str(self.profile_file))

    def get_hotspots(self, top_n: int = 20) -> List[Dict[str, Any]]:
        """
        获取性能热点（最耗时的函数）

        Args:
            top_n: 返回前 N 个热点

        Returns:
            热点函数列表
        """
        self.stats.sort_stats("cumulative")

        hotspots = []
        for func, (cc, nc, tt, ct, callers) in list(self.stats.stats.items())[:top_n]:
            filename, line, func_name = func

            hotspots.append(
                {
                    "function": func_name,
                    "filename": filename,
                    "line": line,
                    "calls": nc,
                    "total_time": tt,
                    "cumulative_time": ct,
                    "percentage": 0,  # 稍后计算
                }
            )

        # 计算百分比
        total_time = sum(h["cumulative_time"] for h in hotspots)
        for hotspot in hotspots:
            hotspot["percentage"] = (
                (hotspot["cumulative_time"] / total_time * 100) if total_time > 0 else 0
            )

        return hotspots

    def get_call_tree(self, func_name: str, max_depth: int = 3) -> Dict[str, Any]:
        """
        获取函数调用树

        Args:
            func_name: 函数名
            max_depth: 最大深度

        Returns:
            调用树字典
        """
        # 查找匹配的函数
        matching_funcs = [func for func in self.stats.stats.keys() if func[2] == func_name]

        if not matching_funcs:
            return {"error": f"Function '{func_name}' not found"}

        func = matching_funcs[0]
        cc, nc, tt, ct, callers = self.stats.stats[func]

        tree = {
            "function": func_name,
            "filename": func[0],
            "line": func[1],
            "calls": nc,
            "total_time": tt,
            "cumulative_time": ct,
            "callers": [],
        }

        # 添加调用者信息
        if callers and max_depth > 0:
            for caller_func, caller_stats in callers.items():
                caller_tree = {
                    "function": caller_func[2],
                    "filename": caller_func[0],
                    "line": caller_func[1],
                    "calls": caller_stats[0],
                }
                tree["callers"].append(caller_tree)

        return tree

    def find_bottlenecks(self, threshold_pct: float = 5.0) -> List[Dict[str, Any]]:
        """
        查找性能瓶颈（占用时间超过阈值的函数）

        Args:
            threshold_pct: 时间占比阈值（百分比）

        Returns:
            瓶颈函数列表
        """
        self.stats.sort_stats("cumulative")

        # 计算总时间
        total_time = sum(stat[3] for stat in self.stats.stats.values())

        bottlenecks = []
        for func, (cc, nc, tt, ct, callers) in self.stats.stats.items():
            percentage = (ct / total_time * 100) if total_time > 0 else 0

            if percentage >= threshold_pct:
                filename, line, func_name = func

                bottlenecks.append(
                    {
                        "function": func_name,
                        "filename": filename,
                        "line": line,
                        "calls": nc,
                        "cumulative_time": ct,
                        "percentage": percentage,
                    }
                )

        # 按百分比排序
        bottlenecks.sort(key=lambda x: x["percentage"], reverse=True)

        return bottlenecks

    def compare_with(self, other_profile: "ProfileAnalyzer") -> Dict[str, Any]:
        """
        与另一个性能分析结果对比

        Args:
            other_profile: 另一个分析器实例

        Returns:
            对比结果
        """
        # 获取两个分析的热点
        hotspots_a = {h["function"]: h for h in self.get_hotspots(50)}
        hotspots_b = {h["function"]: h for h in other_profile.get_hotspots(50)}

        # 找出共同的函数
        common_funcs = set(hotspots_a.keys()) & set(hotspots_b.keys())

        comparison = []
        for func_name in common_funcs:
            a = hotspots_a[func_name]
            b = hotspots_b[func_name]

            time_diff = b["cumulative_time"] - a["cumulative_time"]
            time_diff_pct = (
                (time_diff / a["cumulative_time"] * 100) if a["cumulative_time"] > 0 else 0
            )

            comparison.append(
                {
                    "function": func_name,
                    "time_before": a["cumulative_time"],
                    "time_after": b["cumulative_time"],
                    "time_diff": time_diff,
                    "time_diff_pct": time_diff_pct,
                    "calls_before": a["calls"],
                    "calls_after": b["calls"],
                }
            )

        # 按时间差异排序
        comparison.sort(key=lambda x: abs(x["time_diff"]), reverse=True)

        return {
            "common_functions": len(common_funcs),
            "comparison": comparison[:20],  # 返回前 20 个差异最大的
        }

    def get_io_operations(self) -> List[Dict[str, Any]]:
        """
        获取 I/O 操作相关的函数

        Returns:
            I/O 操作函数列表
        """
        io_keywords = ["read", "write", "open", "load", "save", "fetch", "download"]

        io_operations = []
        for func, (cc, nc, tt, ct, callers) in self.stats.stats.items():
            filename, line, func_name = func

            # 检查函数名是否包含 I/O 关键字
            if any(keyword in func_name.lower() for keyword in io_keywords):
                io_operations.append(
                    {
                        "function": func_name,
                        "filename": filename,
                        "line": line,
                        "calls": nc,
                        "cumulative_time": ct,
                    }
                )

        # 按累计时间排序
        io_operations.sort(key=lambda x: x["cumulative_time"], reverse=True)

        return io_operations

    def export_to_json(self, output_file: Path | str, top_n: int = 100):
        """
        导出分析结果到 JSON 文件

        Args:
            output_file: 输出文件路径
            top_n: 导出前 N 个函数
        """
        output_file = Path(output_file)

        data = {
            "hotspots": self.get_hotspots(top_n),
            "bottlenecks": self.find_bottlenecks(threshold_pct=1.0),
            "io_operations": self.get_io_operations(),
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def print_summary(self, top_n: int = 20):
        """
        打印分析摘要

        Args:
            top_n: 显示前 N 个热点
        """
        print("\n" + "=" * 80)
        print("性能分析结果")
        print("=" * 80)

        # 热点函数
        print(f"\n🔥 前 {top_n} 个性能热点:")
        print("-" * 80)
        print(f"{'函数名':<40} {'调用次数':>10} {'累计时间':>12} {'占比':>8}")
        print("-" * 80)

        hotspots = self.get_hotspots(top_n)
        for hotspot in hotspots:
            print(
                f"{hotspot['function']:<40} "
                f"{hotspot['calls']:>10,} "
                f"{hotspot['cumulative_time']:>12.4f} "
                f"{hotspot['percentage']:>7.2f}%"
            )

        # 性能瓶颈
        print("\n⚠️  性能瓶颈（占用时间 > 5%）:")
        print("-" * 80)

        bottlenecks = self.find_bottlenecks(threshold_pct=5.0)
        if bottlenecks:
            for bottleneck in bottlenecks:
                print(
                    f"  {bottleneck['function']:<40} "
                    f"{bottleneck['percentage']:>6.2f}% "
                    f"({bottleneck['cumulative_time']:.4f}s)"
                )
        else:
            print("  未发现明显瓶颈")

        # I/O 操作
        print("\n💾 I/O 操作:")
        print("-" * 80)

        io_ops = self.get_io_operations()[:10]
        if io_ops:
            for op in io_ops:
                print(f"  {op['function']:<40} {op['calls']:>6} 次 ({op['cumulative_time']:.4f}s)")
        else:
            print("  未发现明显的 I/O 操作")

        print("=" * 80 + "\n")
