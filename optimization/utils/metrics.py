"""
指标计算和提取工具
"""

from datetime import datetime
from typing import Dict

from ..state import BacktestMetrics, OptimizationTarget


def extract_metrics_from_report(report: dict) -> BacktestMetrics:
    """
    从回测报告中提取标准化指标
    """
    returns = report.get("returns", {})
    trade_metrics = report.get("trade_metrics", {})
    analysis = trade_metrics.get("analysis", {})

    # 提取基础指标
    sharpe = next((v for k, v in returns.items() if "Sharpe Ratio" in k), 0.0)
    total_return = next((v for k, v in returns.items() if "Total Return" in k), 0.0)
    max_dd = abs(next((v for k, v in returns.items() if "Max Drawdown" in k), 0.0))

    # 交易统计
    total_trades = analysis.get("total_trades", 0)
    winning_trades = analysis.get("winning_trades", 0)
    losing_trades = analysis.get("losing_trades", 0)

    # 盈亏统计
    avg_win = analysis.get("avg_winning_trade", 0.0)
    avg_loss = abs(analysis.get("avg_losing_trade", 0.0))
    max_win = analysis.get("max_winning_trade", 0.0)
    max_loss = abs(analysis.get("max_losing_trade", 0.0))
    profit_factor = analysis.get("profit_factor", 0.0)

    # 计算衍生指标
    win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
    profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

    # 信号统计
    total_signals = report.get("total_signals", total_trades)
    filtered_signals = report.get("filtered_signals", 0)
    filtered_by_symbol = report.get("filtered_by_symbol", {})

    # 策略参数
    strategy_parameters = report.get("strategy_parameters", {})

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
