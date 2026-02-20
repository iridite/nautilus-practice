"""
Report Generator

生成格式化的策略分析报告。
"""

import pandas as pd
from typing import List
from datetime import datetime
from .analyzer import StrategyAnalyzer


class ReportGenerator:
    """
    报告生成器

    生成格式化的策略分析报告，支持多种输出格式。
    """

    def __init__(self, analyzer: StrategyAnalyzer):
        """
        初始化报告生成器

        Args:
            analyzer: 策略分析器实例
        """
        self.analyzer = analyzer

    def generate_text_report(
        self,
        strategy_name: str | None = None,
        risk_free_rate: float = 0.0,
        trading_days: int = 365,
    ) -> str:
        """
        生成文本格式的报告

        Args:
            strategy_name: 策略名称（None 表示生成所有策略的对比报告）
            risk_free_rate: 无风险利率
            trading_days: 每年交易天数

        Returns:
            格式化的文本报告
        """
        if strategy_name:
            return self._generate_single_strategy_report(
                strategy_name, risk_free_rate, trading_days
            )
        else:
            return self._generate_comparison_report(risk_free_rate, trading_days)

    def _generate_single_strategy_report(
        self,
        strategy_name: str,
        risk_free_rate: float,
        trading_days: int,
    ) -> str:
        """生成单个策略的详细报告"""
        metrics = self.analyzer.calculate_metrics(
            strategy_name, risk_free_rate, trading_days
        )

        report_lines = [
            "=" * 80,
            f"策略分析报告: {strategy_name}",
            "=" * 80,
            "",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "📊 收益指标",
            "-" * 80,
            f"  总收益率:           {metrics['total_return']:>12.2f}%",
            f"  年化收益率:         {metrics['annualized_return']:>12.2f}%",
            "",
            "⚠️  风险指标",
            "-" * 80,
            f"  最大回撤:           {metrics['max_drawdown']:>12.2f}%",
            f"  回撤持续天数:       {metrics['max_drawdown_duration']:>12} 天",
            f"  波动率 (年化):      {metrics['volatility']:>12.2f}%",
            f"  下行波动率 (年化):  {metrics['downside_volatility']:>12.2f}%",
            "",
            "📈 风险调整收益指标",
            "-" * 80,
            f"  夏普比率:           {metrics['sharpe_ratio']:>12.2f}",
            f"  索提诺比率:         {metrics['sortino_ratio']:>12.2f}",
            f"  卡玛比率:           {metrics['calmar_ratio']:>12.2f}",
            "",
            "💼 交易统计",
            "-" * 80,
            f"  总交易次数:         {metrics['total_trades']:>12}",
            f"  胜率:               {metrics['win_rate']:>12.2f}%",
            f"  盈亏比:             {metrics['profit_factor']:>12.2f}",
            f"  平均每笔盈亏:       {metrics['average_trade']:>12.2f}",
            "",
            "📅 时间信息",
            "-" * 80,
            f"  开始日期:           {metrics['start_date']}",
            f"  结束日期:           {metrics['end_date']}",
            f"  总天数:             {metrics['total_days']} 天",
            "",
            "=" * 80,
        ]

        return "\n".join(report_lines)

    def _generate_comparison_report(
        self,
        risk_free_rate: float,
        trading_days: int,
    ) -> str:
        """生成多策略对比报告"""
        comparison = self.analyzer.compare_strategies(
            risk_free_rate=risk_free_rate,
            trading_days=trading_days,
        )

        if len(comparison) == 0:
            return "没有可用的策略数据"

        report_lines = [
            "=" * 120,
            "策略对比分析报告",
            "=" * 120,
            "",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"策略数量: {len(comparison)}",
            "",
            "📊 关键指标对比",
            "-" * 120,
        ]

        # 选择关键指标
        key_metrics = [
            "total_return",
            "annualized_return",
            "max_drawdown",
            "sharpe_ratio",
            "sortino_ratio",
            "win_rate",
            "total_trades",
        ]

        # 格式化对比表格
        display_comparison = comparison[
            [m for m in key_metrics if m in comparison.columns]
        ].copy()

        # 重命名列以便显示
        column_names = {
            "total_return": "总收益%",
            "annualized_return": "年化收益%",
            "max_drawdown": "最大回撤%",
            "sharpe_ratio": "夏普率",
            "sortino_ratio": "索提诺率",
            "win_rate": "胜率%",
            "total_trades": "交易次数",
        }

        display_comparison.rename(columns=column_names, inplace=True)

        # 转换为字符串表格
        report_lines.append(display_comparison.to_string())
        report_lines.append("")

        # 添加排名信息
        report_lines.extend([
            "",
            "🏆 策略排名",
            "-" * 120,
        ])

        # 按夏普率排名
        if "sharpe_ratio" in comparison.columns:
            ranked = comparison.sort_values("sharpe_ratio", ascending=False)
            report_lines.append("\n按夏普比率排名:")
            for i, (name, row) in enumerate(ranked.iterrows(), 1):
                report_lines.append(
                    f"  {i}. {name:<30} (夏普率: {row['sharpe_ratio']:>6.2f})"
                )

        # 按年化收益排名
        if "annualized_return" in comparison.columns:
            ranked = comparison.sort_values("annualized_return", ascending=False)
            report_lines.append("\n按年化收益率排名:")
            for i, (name, row) in enumerate(ranked.iterrows(), 1):
                report_lines.append(
                    f"  {i}. {name:<30} (年化收益: {row['annualized_return']:>6.2f}%)"
                )

        # 添加相关性分析
        correlation = self.analyzer.get_correlation_matrix()
        if len(correlation) > 1:
            report_lines.extend([
                "",
                "",
                "🔗 策略收益率相关性矩阵",
                "-" * 120,
                correlation.to_string(),
            ])

        report_lines.extend([
            "",
            "=" * 120,
        ])

        return "\n".join(report_lines)

    def generate_summary_table(
        self,
        metrics: List[str] | None = None,
        risk_free_rate: float = 0.0,
        trading_days: int = 365,
    ) -> pd.DataFrame:
        """
        生成汇总表格

        Args:
            metrics: 要包含的指标列表
            risk_free_rate: 无风险利率
            trading_days: 每年交易天数

        Returns:
            汇总表格 DataFrame
        """
        return self.analyzer.compare_strategies(
            metrics=metrics,
            risk_free_rate=risk_free_rate,
            trading_days=trading_days,
        )

    def export_to_csv(
        self,
        filepath: str,
        risk_free_rate: float = 0.0,
        trading_days: int = 365,
    ):
        """
        导出对比结果到 CSV 文件

        Args:
            filepath: 输出文件路径
            risk_free_rate: 无风险利率
            trading_days: 每年交易天数
        """
        comparison = self.analyzer.compare_strategies(
            risk_free_rate=risk_free_rate,
            trading_days=trading_days,
        )
        comparison.to_csv(filepath)

    def export_to_excel(
        self,
        filepath: str,
        risk_free_rate: float = 0.0,
        trading_days: int = 365,
    ):
        """
        导出对比结果到 Excel 文件

        Args:
            filepath: 输出文件路径
            risk_free_rate: 无风险利率
            trading_days: 每年交易天数
        """
        comparison = self.analyzer.compare_strategies(
            risk_free_rate=risk_free_rate,
            trading_days=trading_days,
        )

        # 创建 Excel writer
        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            # 写入对比数据
            comparison.to_excel(writer, sheet_name="策略对比")

            # 写入相关性矩阵
            correlation = self.analyzer.get_correlation_matrix()
            if len(correlation) > 0:
                correlation.to_excel(writer, sheet_name="相关性矩阵")

            # 写入汇总统计
            summary = self.analyzer.get_summary_statistics(
                risk_free_rate=risk_free_rate,
                trading_days=trading_days,
            )
            if summary:
                summary_df = pd.DataFrame(summary)
                summary_df.to_excel(writer, sheet_name="汇总统计")

    def generate_markdown_report(
        self,
        strategy_name: str | None = None,
        risk_free_rate: float = 0.0,
        trading_days: int = 365,
    ) -> str:
        """
        生成 Markdown 格式的报告

        Args:
            strategy_name: 策略名称（None 表示生成对比报告）
            risk_free_rate: 无风险利率
            trading_days: 每年交易天数

        Returns:
            Markdown 格式的报告
        """
        if strategy_name:
            return self._generate_single_strategy_markdown(
                strategy_name, risk_free_rate, trading_days
            )
        else:
            return self._generate_comparison_markdown(risk_free_rate, trading_days)

    def _generate_single_strategy_markdown(
        self,
        strategy_name: str,
        risk_free_rate: float,
        trading_days: int,
    ) -> str:
        """生成单个策略的 Markdown 报告"""
        metrics = self.analyzer.calculate_metrics(
            strategy_name, risk_free_rate, trading_days
        )

        md_lines = [
            f"# 策略分析报告: {strategy_name}",
            "",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 📊 收益指标",
            "",
            f"- **总收益率**: {metrics['total_return']:.2f}%",
            f"- **年化收益率**: {metrics['annualized_return']:.2f}%",
            "",
            "## ⚠️ 风险指标",
            "",
            f"- **最大回撤**: {metrics['max_drawdown']:.2f}%",
            f"- **回撤持续天数**: {metrics['max_drawdown_duration']} 天",
            f"- **波动率 (年化)**: {metrics['volatility']:.2f}%",
            f"- **下行波动率 (年化)**: {metrics['downside_volatility']:.2f}%",
            "",
            "## 📈 风险调整收益指标",
            "",
            f"- **夏普比率**: {metrics['sharpe_ratio']:.2f}",
            f"- **索提诺比率**: {metrics['sortino_ratio']:.2f}",
            f"- **卡玛比率**: {metrics['calmar_ratio']:.2f}",
            "",
            "## 💼 交易统计",
            "",
            f"- **总交易次数**: {metrics['total_trades']}",
            f"- **胜率**: {metrics['win_rate']:.2f}%",
            f"- **盈亏比**: {metrics['profit_factor']:.2f}",
            f"- **平均每笔盈亏**: {metrics['average_trade']:.2f}",
            "",
            "## 📅 时间信息",
            "",
            f"- **开始日期**: {metrics['start_date']}",
            f"- **结束日期**: {metrics['end_date']}",
            f"- **总天数**: {metrics['total_days']} 天",
            "",
        ]

        return "\n".join(md_lines)

    def _generate_comparison_markdown(
        self,
        risk_free_rate: float,
        trading_days: int,
    ) -> str:
        """生成多策略对比的 Markdown 报告"""
        comparison = self.analyzer.compare_strategies(
            risk_free_rate=risk_free_rate,
            trading_days=trading_days,
        )

        if len(comparison) == 0:
            return "# 策略对比分析报告\n\n没有可用的策略数据"

        md_lines = [
            "# 策略对比分析报告",
            "",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**策略数量**: {len(comparison)}",
            "",
            "## 📊 关键指标对比",
            "",
        ]

        # 生成 Markdown 表格
        key_metrics = [
            "total_return",
            "annualized_return",
            "max_drawdown",
            "sharpe_ratio",
            "sortino_ratio",
            "win_rate",
            "total_trades",
        ]

        display_comparison = comparison[
            [m for m in key_metrics if m in comparison.columns]
        ].copy()

        # 转换为 Markdown 表格
        md_lines.append(display_comparison.to_markdown())
        md_lines.append("")

        # 添加排名
        md_lines.extend([
            "## 🏆 策略排名",
            "",
            "### 按夏普比率排名",
            "",
        ])

        if "sharpe_ratio" in comparison.columns:
            ranked = comparison.sort_values("sharpe_ratio", ascending=False)
            for i, (name, row) in enumerate(ranked.iterrows(), 1):
                md_lines.append(
                    f"{i}. **{name}** (夏普率: {row['sharpe_ratio']:.2f})"
                )

        md_lines.extend([
            "",
            "### 按年化收益率排名",
            "",
        ])

        if "annualized_return" in comparison.columns:
            ranked = comparison.sort_values("annualized_return", ascending=False)
            for i, (name, row) in enumerate(ranked.iterrows(), 1):
                md_lines.append(
                    f"{i}. **{name}** (年化收益: {row['annualized_return']:.2f}%)"
                )

        md_lines.append("")

        return "\n".join(md_lines)
