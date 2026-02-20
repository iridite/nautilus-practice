"""
使用示例：策略性能分析工具

演示如何使用性能分析工具来分析和对比策略回测结果。
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from utils.performance import PerformanceMetrics, StrategyAnalyzer, ReportGenerator


def create_sample_equity_curve(
    start_value: float = 100000,
    days: int = 365,
    daily_return: float = 0.001,
    volatility: float = 0.02,
) -> pd.Series:
    """
    创建示例权益曲线

    Args:
        start_value: 初始资金
        days: 天数
        daily_return: 日均收益率
        volatility: 波动率

    Returns:
        权益曲线 Series
    """
    dates = pd.date_range(start=datetime.now() - timedelta(days=days), periods=days, freq="D")

    # 生成随机收益率
    returns = np.random.normal(daily_return, volatility, days)

    # 计算权益曲线
    equity = start_value * (1 + returns).cumprod()

    return pd.Series(equity, index=dates)


def create_sample_trades(num_trades: int = 50, win_rate: float = 0.6) -> pd.DataFrame:
    """
    创建示例交易记录

    Args:
        num_trades: 交易次数
        win_rate: 胜率

    Returns:
        交易记录 DataFrame
    """
    trades = []

    for i in range(num_trades):
        # 根据胜率决定盈亏
        if np.random.random() < win_rate:
            # 盈利交易
            pnl = np.random.uniform(100, 500)
        else:
            # 亏损交易
            pnl = -np.random.uniform(50, 300)

        trades.append({"pnl": pnl})

    return pd.DataFrame(trades)


def example_single_strategy_analysis():
    """示例 1：单个策略分析"""
    print("=" * 80)
    print("示例 1：单个策略分析")
    print("=" * 80)

    # 创建示例数据
    equity_curve = create_sample_equity_curve(
        start_value=100000,
        days=365,
        daily_return=0.002,
        volatility=0.015,
    )

    trades = create_sample_trades(num_trades=100, win_rate=0.65)

    # 计算性能指标
    metrics = PerformanceMetrics(equity_curve, trades)
    all_metrics = metrics.get_all_metrics(risk_free_rate=2.0, trading_days=365)

    # 打印关键指标
    print(f"\n总收益率: {all_metrics['total_return']:.2f}%")
    print(f"年化收益率: {all_metrics['annualized_return']:.2f}%")
    print(f"最大回撤: {all_metrics['max_drawdown']:.2f}%")
    print(f"夏普比率: {all_metrics['sharpe_ratio']:.2f}")
    print(f"索提诺比率: {all_metrics['sortino_ratio']:.2f}")
    print(f"胜率: {all_metrics['win_rate']:.2f}%")
    print(f"盈亏比: {all_metrics['profit_factor']:.2f}")
    print(f"总交易次数: {all_metrics['total_trades']}")
    print()


def example_multiple_strategies_comparison():
    """示例 2：多策略对比分析"""
    print("=" * 80)
    print("示例 2：多策略对比分析")
    print("=" * 80)

    # 创建分析器
    analyzer = StrategyAnalyzer()

    # 添加多个策略
    # 策略 A：高收益高风险
    equity_a = create_sample_equity_curve(
        start_value=100000,
        days=365,
        daily_return=0.003,
        volatility=0.025,
    )
    trades_a = create_sample_trades(num_trades=150, win_rate=0.60)
    analyzer.add_strategy("激进策略", equity_a, trades_a)

    # 策略 B：中等收益中等风险
    equity_b = create_sample_equity_curve(
        start_value=100000,
        days=365,
        daily_return=0.002,
        volatility=0.015,
    )
    trades_b = create_sample_trades(num_trades=100, win_rate=0.65)
    analyzer.add_strategy("稳健策略", equity_b, trades_b)

    # 策略 C：低收益低风险
    equity_c = create_sample_equity_curve(
        start_value=100000,
        days=365,
        daily_return=0.001,
        volatility=0.008,
    )
    trades_c = create_sample_trades(num_trades=80, win_rate=0.70)
    analyzer.add_strategy("保守策略", equity_c, trades_c)

    # 生成对比报告
    generator = ReportGenerator(analyzer)
    report = generator.generate_text_report()
    print(report)

    # 按夏普率排名
    print("\n" + "=" * 80)
    print("按夏普比率排名:")
    print("=" * 80)
    ranked = analyzer.rank_strategies(by="sharpe_ratio")
    print(ranked[["sharpe_ratio", "total_return", "max_drawdown", "win_rate"]])
    print()


def example_strategy_filtering():
    """示例 3：策略筛选"""
    print("=" * 80)
    print("示例 3：策略筛选")
    print("=" * 80)

    # 创建分析器
    analyzer = StrategyAnalyzer()

    # 添加 5 个策略
    for i in range(5):
        equity = create_sample_equity_curve(
            start_value=100000,
            days=365,
            daily_return=0.001 + i * 0.0005,
            volatility=0.01 + i * 0.005,
        )
        trades = create_sample_trades(num_trades=50 + i * 20, win_rate=0.55 + i * 0.03)
        analyzer.add_strategy(f"策略 {i+1}", equity, trades)

    # 筛选条件：夏普率 > 1.0，最大回撤 < 15%，胜率 > 60%
    filtered = analyzer.filter_strategies(
        min_sharpe=1.0,
        max_drawdown=15.0,
        min_win_rate=60.0,
    )

    print(f"\n符合条件的策略（夏普率 > 1.0, 最大回撤 < 15%, 胜率 > 60%）:")
    print(f"共 {len(filtered)} 个策略:")
    for name in filtered:
        print(f"  - {name}")
    print()


def example_export_reports():
    """示例 4：导出报告"""
    print("=" * 80)
    print("示例 4：导出报告")
    print("=" * 80)

    # 创建分析器
    analyzer = StrategyAnalyzer()

    # 添加策略
    equity = create_sample_equity_curve(start_value=100000, days=365)
    trades = create_sample_trades(num_trades=100, win_rate=0.65)
    analyzer.add_strategy("示例策略", equity, trades)

    # 生成报告生成器
    generator = ReportGenerator(analyzer)

    # 生成 Markdown 报告
    md_report = generator.generate_markdown_report("示例策略")
    print("\nMarkdown 报告预览（前 500 字符）:")
    print(md_report[:500])
    print("...")

    # 可以保存到文件
    # with open("strategy_report.md", "w", encoding="utf-8") as f:
    #     f.write(md_report)
    # print("\n✅ Markdown 报告已保存到 strategy_report.md")

    # 导出 CSV
    # generator.export_to_csv("strategy_comparison.csv")
    # print("✅ CSV 报告已保存到 strategy_comparison.csv")

    print()


def main():
    """运行所有示例"""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "策略性能分析工具使用示例" + " " * 32 + "║")
    print("╚" + "=" * 78 + "╝")
    print()

    # 运行示例
    example_single_strategy_analysis()
    example_multiple_strategies_comparison()
    example_strategy_filtering()
    example_export_reports()

    print("=" * 80)
    print("所有示例运行完成！")
    print("=" * 80)
    print()
    print("💡 提示：")
    print("  1. 使用 PerformanceMetrics 计算单个策略的性能指标")
    print("  2. 使用 StrategyAnalyzer 对比多个策略")
    print("  3. 使用 ReportGenerator 生成格式化报告")
    print("  4. 支持导出 CSV、Excel、Markdown 等格式")
    print()


if __name__ == "__main__":
    main()
