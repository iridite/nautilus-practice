"""
Profile Reporter

性能分析报告生成器。
"""

from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime


class ProfileReporter:
    """
    性能分析报告生成器

    生成格式化的性能分析报告。
    """

    def __init__(self, output_dir: Path | None = None):
        """
        初始化报告生成器

        Args:
            output_dir: 输出目录
        """
        self.output_dir = output_dir or Path("output/profiling")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_text_report(
        self,
        hotspots: List[Dict[str, Any]],
        bottlenecks: List[Dict[str, Any]],
        io_operations: List[Dict[str, Any]],
        summary: Dict[str, Any] | None = None,
    ) -> str:
        """
        生成文本格式的报告

        Args:
            hotspots: 性能热点列表
            bottlenecks: 性能瓶颈列表
            io_operations: I/O 操作列表
            summary: 摘要信息

        Returns:
            格式化的文本报告
        """
        lines = [
            "=" * 80,
            "性能分析报告",
            "=" * 80,
            "",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        # 添加摘要
        if summary:
            lines.extend([
                "📊 总体统计",
                "-" * 80,
                f"总耗时:           {summary.get('total_elapsed_time', 0):.4f} 秒",
                f"总调用次数:       {summary.get('total_calls', 0):,}",
                f"唯一函数数量:     {summary.get('unique_functions', 0):,}",
                "",
            ])

        # 性能热点
        lines.extend([
            "🔥 性能热点（前 20 个最耗时的函数）",
            "-" * 80,
            f"{'函数名':<40} {'调用次数':>10} {'累计时间':>12} {'占比':>8}",
            "-" * 80,
        ])

        for hotspot in hotspots[:20]:
            lines.append(
                f"{hotspot['function']:<40} "
                f"{hotspot['calls']:>10,} "
                f"{hotspot['cumulative_time']:>12.4f} "
                f"{hotspot.get('percentage', 0):>7.2f}%"
            )

        lines.append("")

        # 性能瓶颈
        lines.extend([
            "⚠️  性能瓶颈（占用时间 > 5%）",
            "-" * 80,
        ])

        if bottlenecks:
            for bottleneck in bottlenecks:
                lines.append(
                    f"  {bottleneck['function']:<40} "
                    f"{bottleneck['percentage']:>6.2f}% "
                    f"({bottleneck['cumulative_time']:.4f}s)"
                )
        else:
            lines.append("  未发现明显瓶颈")

        lines.append("")

        # I/O 操作
        lines.extend([
            "💾 I/O 操作（前 10 个）",
            "-" * 80,
        ])

        if io_operations:
            for op in io_operations[:10]:
                lines.append(
                    f"  {op['function']:<40} "
                    f"{op['calls']:>6} 次 "
                    f"({op['cumulative_time']:.4f}s)"
                )
        else:
            lines.append("  未发现明显的 I/O 操作")

        lines.extend([
            "",
            "=" * 80,
        ])

        return "\n".join(lines)

    def generate_markdown_report(
        self,
        hotspots: List[Dict[str, Any]],
        bottlenecks: List[Dict[str, Any]],
        io_operations: List[Dict[str, Any]],
        summary: Dict[str, Any] | None = None,
    ) -> str:
        """
        生成 Markdown 格式的报告

        Args:
            hotspots: 性能热点列表
            bottlenecks: 性能瓶颈列表
            io_operations: I/O 操作列表
            summary: 摘要信息

        Returns:
            Markdown 格式的报告
        """
        lines = [
            "# 性能分析报告",
            "",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        # 添加摘要
        if summary:
            lines.extend([
                "## 📊 总体统计",
                "",
                f"- **总耗时**: {summary.get('total_elapsed_time', 0):.4f} 秒",
                f"- **总调用次数**: {summary.get('total_calls', 0):,}",
                f"- **唯一函数数量**: {summary.get('unique_functions', 0):,}",
                "",
            ])

        # 性能热点
        lines.extend([
            "## 🔥 性能热点",
            "",
            "前 20 个最耗时的函数：",
            "",
            "| 函数名 | 调用次数 | 累计时间 (s) | 占比 (%) |",
            "|--------|----------|--------------|----------|",
        ])

        for hotspot in hotspots[:20]:
            lines.append(
                f"| {hotspot['function']} | "
                f"{hotspot['calls']:,} | "
                f"{hotspot['cumulative_time']:.4f} | "
                f"{hotspot.get('percentage', 0):.2f} |"
            )

        lines.append("")

        # 性能瓶颈
        lines.extend([
            "## ⚠️ 性能瓶颈",
            "",
            "占用时间超过 5% 的函数：",
            "",
        ])

        if bottlenecks:
            for bottleneck in bottlenecks:
                lines.append(
                    f"- **{bottleneck['function']}**: "
                    f"{bottleneck['percentage']:.2f}% "
                    f"({bottleneck['cumulative_time']:.4f}s)"
                )
        else:
            lines.append("未发现明显瓶颈")

        lines.append("")

        # I/O 操作
        lines.extend([
            "## 💾 I/O 操作",
            "",
            "前 10 个 I/O 操作：",
            "",
        ])

        if io_operations:
            for op in io_operations[:10]:
                lines.append(
                    f"- **{op['function']}**: "
                    f"{op['calls']} 次 "
                    f"({op['cumulative_time']:.4f}s)"
                )
        else:
            lines.append("未发现明显的 I/O 操作")

        lines.append("")

        return "\n".join(lines)

    def save_report(
        self,
        report_content: str,
        filename: str,
        format: str = "txt"
    ) -> Path:
        """
        保存报告到文件

        Args:
            report_content: 报告内容
            filename: 文件名（不含扩展名）
            format: 格式（txt 或 md）

        Returns:
            保存的文件路径
        """
        filepath = self.output_dir / f"{filename}.{format}"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report_content)

        return filepath
