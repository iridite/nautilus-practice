"""
指标计算和提取工具
"""

from datetime import datetime
from typing import Dict

from ..state import BacktestMetrics, OptimizationTarget


def extract_metrics_from_report(report: dict) -> BacktestMetrics:
    """
    从回测报告中提取标准化指标

    JSON 结构:
    - returns: 收益指标
    - trade_metrics: 交易指标
    - strategy_config: 策略配置和参数
    - filter_stats: 信号过滤统计
    - summary: 总体统计
    """
    returns = report.get("returns", {})
    trade_metrics = report.get("trade_metrics", {})
    analysis = trade_metrics.get("analysis", {})
    summary = report.get("summary", {})
    performance = report.get("performance", {})

    # 优先从 performance 字段提取指标（如果可用）
    sharpe = performance.get("sharpe_ratio")
    if sharpe is None:
        sharpe = next((v for k, v in returns.items() if "Sharpe Ratio" in k), 0.0)

    total_return = performance.get("total_pnl_pct")
    if total_return is None:
        total_return = next((v for k, v in returns.items() if "Total Return" in k), 0.0)

    # 最大回撤从 returns 提取
    max_dd = abs(next((v for k, v in returns.items() if "Max Drawdown" in k), 0.0))

    # 交易统计 - 优先从 performance，其次 analysis
    total_trades = performance.get("total_trades", analysis.get("total_trades", 0))
    if total_trades == 0:
        total_trades = summary.get("total_positions", 0)

    winning_trades = analysis.get("winning_trades", 0)
    losing_trades = analysis.get("losing_trades", 0)

    # 盈亏统计 - 优先从 performance
    avg_win = performance.get(
        "avg_winning_trade", analysis.get("avg_winning_trade", 0.0)
    )
    avg_loss = abs(
        performance.get("avg_losing_trade", analysis.get("avg_losing_trade", 0.0))
    )
    max_win = analysis.get("max_winning_trade", 0.0)
    max_loss = abs(analysis.get("max_losing_trade", 0.0))
    profit_factor = analysis.get("profit_factor", 0.0)

    # 计算衍生指标 - 优先使用 performance 中的值
    win_rate = performance.get("win_rate")
    if win_rate is None:
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

    profit_loss_ratio = performance.get("profit_loss_ratio")
    if profit_loss_ratio is None:
        profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0

    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

    # 信号统计 - 优先从 performance，其次 filter_stats
    total_signals = performance.get("total_signals", 0)
    filtered_signals = performance.get("signals_passed", 0)

    # 如果 performance 中没有，从 filter_stats 提取
    if total_signals == 0:
        filter_stats = report.get("filter_stats", {})
        total_stats = filter_stats.get("total", {})
        total_signals = total_stats.get("signal_checks", 0)
        filtered_signals = total_stats.get("all_passed", 0)

    # 如果还是为空，使用 summary 中的订单数
    if total_signals == 0:
        total_signals = summary.get("total_orders", total_trades)
        filtered_signals = total_trades

    # 按标的过滤统计（从 filter_stats.by_instrument 提取）
    filter_stats = report.get("filter_stats", {})
    filtered_by_symbol = filter_stats.get("by_instrument", {})

    # 策略参数 - 直接从 strategy_config 读取
    strategy_config = report.get("strategy_config", {})
    if isinstance(strategy_config, dict):
        strategy_parameters = strategy_config
    else:
        strategy_parameters = {}

    return BacktestMetrics(
        sharpe=sharpe,
        total_trades=total_trades,
        profit_pct=total_return,
        profit_loss_ratio=profit_loss_ratio,
        win_rate=win_rate,
        expectancy=expectancy,
        avg_profit=avg_win,
        avg_loss=avg_loss,
        max_profit=max_win,
        max_loss=max_loss,
        max_drawdown=max_dd,
        profit_factor=profit_factor,
        total_signals=total_signals,
        filtered_signals=filtered_signals,
        filtered_by_symbol=filtered_by_symbol,
        strategy_parameters=strategy_parameters,
        timestamp=datetime.now().isoformat(),
    )


def calculate_goal_distance(
    current: BacktestMetrics,
    target: OptimizationTarget,
) -> Dict[str, float]:
    """
    计算当前指标与目标的距离
    """
    distances = {}

    if target.get("target_sharpe") is not None:
        distances["sharpe"] = abs(current["sharpe"] - target["target_sharpe"])

    if target.get("target_trades") is not None:
        distances["trades"] = abs(current["total_trades"] - target["target_trades"])

    if target.get("target_win_rate") is not None:
        distances["win_rate"] = abs(current["win_rate"] - target["target_win_rate"])

    if target.get("target_profit_loss_ratio") is not None:
        distances["profit_loss_ratio"] = abs(
            current["profit_loss_ratio"] - target["target_profit_loss_ratio"]
        )

    if target.get("target_expectancy") is not None:
        distances["expectancy"] = abs(
            current["expectancy"] - target["target_expectancy"]
        )

    if target.get("target_profit_pct") is not None:
        distances["profit_pct"] = abs(
            current["profit_pct"] - target["target_profit_pct"]
        )

    return distances
