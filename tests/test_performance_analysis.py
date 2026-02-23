"""
Tests for Performance Analysis Tools

测试性能分析工具的各项功能。
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from utils.performance import PerformanceMetrics, StrategyAnalyzer, ReportGenerator


class TestPerformanceMetrics:
    """测试 PerformanceMetrics 类"""

    def test_total_return(self):
        """测试总收益率计算"""
        # 创建简单的权益曲线：从 100 涨到 150
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        equity = pd.Series([100 + i * 5 for i in range(10)], index=dates)

        metrics = PerformanceMetrics(equity)
        total_ret = metrics.total_return()

        # 预期收益率：(145 - 100) / 100 * 100 = 45%
        assert abs(total_ret - 45.0) < 0.01

    def test_max_drawdown(self):
        """测试最大回撤计算"""
        # 创建有回撤的权益曲线
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        equity = pd.Series([100, 110, 120, 110, 100, 90, 100, 110, 120, 130], index=dates)

        metrics = PerformanceMetrics(equity)
        dd_info = metrics.max_drawdown()

        # 最大回撤应该是从 120 跌到 90，回撤 25%
        assert abs(dd_info["max_drawdown"] - 25.0) < 0.01

    def test_sharpe_ratio(self):
        """测试夏普率计算"""
        # 创建稳定增长的权益曲线
        dates = pd.date_range("2024-01-01", periods=365, freq="D")
        equity = pd.Series([100 * (1.001**i) for i in range(365)], index=dates)

        metrics = PerformanceMetrics(equity)
        sharpe = metrics.sharpe_ratio(risk_free_rate=0.0, trading_days=365)

        # 夏普率应该为正
        assert sharpe > 0

    def test_win_rate_with_trades(self):
        """测试胜率计算（有交易记录）"""
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        equity = pd.Series([100 + i * 5 for i in range(10)], index=dates)

        # 创建交易记录：6 胜 4 负
        trades = pd.DataFrame({"pnl": [10, -5, 15, -3, 20, -8, 12, -4, 18, -6]})

        metrics = PerformanceMetrics(equity, trades)
        win_rate = metrics.win_rate()

        # 胜率应该是 50%（5 胜 5 负）
        assert abs(win_rate - 50.0) < 0.01

    def test_profit_factor(self):
        """测试盈亏比计算"""
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        equity = pd.Series([100 + i * 5 for i in range(10)], index=dates)

        # 创建交易记录
        trades = pd.DataFrame({"pnl": [10, -5, 20, -10, 30, -5]})

        metrics = PerformanceMetrics(equity, trades)
        pf = metrics.profit_factor()

        # 盈亏比 = (10 + 20 + 30) / (5 + 10 + 5) = 60 / 20 = 3.0
        assert abs(pf - 3.0) < 0.01

    def test_empty_equity_curve(self):
        """测试空权益曲线"""
        equity = pd.Series([], dtype=float)
        metrics = PerformanceMetrics(equity)

        assert metrics.total_return() == 0.0
        assert metrics.max_drawdown()["max_drawdown"] == 0.0


class TestStrategyAnalyzer:
    """测试 StrategyAnalyzer 类"""

    def test_add_strategy(self):
        """测试添加策略"""
        analyzer = StrategyAnalyzer()

        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        equity = pd.Series([100 + i * 5 for i in range(10)], index=dates)

        analyzer.add_strategy("Strategy A", equity)

        assert "Strategy A" in analyzer.get_strategy_names()

    def test_calculate_metrics(self):
        """测试计算指标"""
        analyzer = StrategyAnalyzer()

        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        equity = pd.Series([100 + i * 5 for i in range(10)], index=dates)

        analyzer.add_strategy("Strategy A", equity)
        metrics = analyzer.calculate_metrics("Strategy A")

        assert "total_return" in metrics
        assert "sharpe_ratio" in metrics
        assert "max_drawdown" in metrics

    def test_compare_strategies(self):
        """测试策略对比"""
        analyzer = StrategyAnalyzer()

        dates = pd.date_range("2024-01-01", periods=10, freq="D")

        # 添加两个策略
        equity_a = pd.Series([100 + i * 5 for i in range(10)], index=dates)
        equity_b = pd.Series([100 + i * 3 for i in range(10)], index=dates)

        analyzer.add_strategy("Strategy A", equity_a)
        analyzer.add_strategy("Strategy B", equity_b)

        comparison = analyzer.compare_strategies()

        assert len(comparison) == 2
        assert "Strategy A" in comparison.index
        assert "Strategy B" in comparison.index

    def test_rank_strategies(self):
        """测试策略排名"""
        analyzer = StrategyAnalyzer()

        dates = pd.date_range("2024-01-01", periods=100, freq="D")

        # 策略 A：高收益高波动
        equity_a = pd.Series([100 * (1.01**i) for i in range(100)], index=dates)

        # 策略 B：低收益低波动
        equity_b = pd.Series([100 * (1.005**i) for i in range(100)], index=dates)

        analyzer.add_strategy("Strategy A", equity_a)
        analyzer.add_strategy("Strategy B", equity_b)

        ranked = analyzer.rank_strategies(by="total_return")

        # Strategy A 应该排在第一（收益更高）
        assert ranked.index[0] == "Strategy A"

    def test_get_best_strategy(self):
        """测试获取最佳策略"""
        analyzer = StrategyAnalyzer()

        dates = pd.date_range("2024-01-01", periods=100, freq="D")

        equity_a = pd.Series([100 * (1.01**i) for i in range(100)], index=dates)
        equity_b = pd.Series([100 * (1.005**i) for i in range(100)], index=dates)

        analyzer.add_strategy("Strategy A", equity_a)
        analyzer.add_strategy("Strategy B", equity_b)

        best_name, best_metrics = analyzer.get_best_strategy(by="total_return")

        assert best_name == "Strategy A"
        assert "total_return" in best_metrics

    def test_filter_strategies(self):
        """测试策略筛选"""
        analyzer = StrategyAnalyzer()

        dates = pd.date_range("2024-01-01", periods=100, freq="D")

        # 策略 A：高夏普率
        equity_a = pd.Series([100 + i * 2 for i in range(100)], index=dates)

        # 策略 B：低夏普率（高波动）
        equity_b = pd.Series(
            [100 + i * 2 + np.random.randn() * 10 for i in range(100)], index=dates
        )

        analyzer.add_strategy("Strategy A", equity_a)
        analyzer.add_strategy("Strategy B", equity_b)

        # 筛选夏普率 > 1 的策略
        filtered = analyzer.filter_strategies(min_sharpe=1.0)

        # Strategy A 应该被筛选出来
        assert "Strategy A" in filtered


class TestReportGenerator:
    """测试 ReportGenerator 类"""

    def test_generate_text_report_single_strategy(self):
        """测试生成单个策略的文本报告"""
        analyzer = StrategyAnalyzer()

        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        equity = pd.Series([100 + i * 5 for i in range(10)], index=dates)

        analyzer.add_strategy("Strategy A", equity)

        generator = ReportGenerator(analyzer)
        report = generator.generate_text_report("Strategy A")

        assert "Strategy A" in report
        assert "总收益率" in report
        assert "夏普比率" in report

    def test_generate_text_report_comparison(self):
        """测试生成对比报告"""
        analyzer = StrategyAnalyzer()

        dates = pd.date_range("2024-01-01", periods=10, freq="D")

        equity_a = pd.Series([100 + i * 5 for i in range(10)], index=dates)
        equity_b = pd.Series([100 + i * 3 for i in range(10)], index=dates)

        analyzer.add_strategy("Strategy A", equity_a)
        analyzer.add_strategy("Strategy B", equity_b)

        generator = ReportGenerator(analyzer)
        report = generator.generate_text_report()

        assert "策略对比分析报告" in report
        assert "Strategy A" in report
        assert "Strategy B" in report

    def test_generate_markdown_report(self):
        """测试生成 Markdown 报告"""
        analyzer = StrategyAnalyzer()

        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        equity = pd.Series([100 + i * 5 for i in range(10)], index=dates)

        analyzer.add_strategy("Strategy A", equity)

        generator = ReportGenerator(analyzer)
        report = generator.generate_markdown_report("Strategy A")

        assert "# 策略分析报告" in report
        assert "Strategy A" in report
        assert "##" in report  # 应该有 Markdown 标题

    def test_generate_summary_table(self):
        """测试生成汇总表格"""
        analyzer = StrategyAnalyzer()

        dates = pd.date_range("2024-01-01", periods=10, freq="D")

        equity_a = pd.Series([100 + i * 5 for i in range(10)], index=dates)
        equity_b = pd.Series([100 + i * 3 for i in range(10)], index=dates)

        analyzer.add_strategy("Strategy A", equity_a)
        analyzer.add_strategy("Strategy B", equity_b)

        generator = ReportGenerator(analyzer)
        table = generator.generate_summary_table()

        assert len(table) == 2
        assert "total_return" in table.columns
        assert "sharpe_ratio" in table.columns


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
