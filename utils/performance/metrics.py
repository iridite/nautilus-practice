"""
Performance Metrics Calculator

计算策略回测的关键性能指标。
"""

import numpy as np
import pandas as pd
from typing import Dict, Any


class PerformanceMetrics:
    """
    性能指标计算器

    计算策略回测的各项关键指标，包括：
    - 收益率指标（总收益、年化收益、月度收益等）
    - 风险指标（最大回撤、波动率、下行波动率等）
    - 风险调整收益指标（夏普率、索提诺比率、卡玛比率等）
    - 交易统计（胜率、盈亏比、交易次数等）
    """

    def __init__(self, equity_curve: pd.Series, trades: pd.DataFrame | None = None):
        """
        初始化性能指标计算器

        Args:
            equity_curve: 权益曲线（时间序列）
            trades: 交易记录（可选）
        """
        self.equity_curve = equity_curve
        self.trades = trades
        self.returns = equity_curve.pct_change().dropna()

    def total_return(self) -> float:
        """
        计算总收益率

        Returns:
            总收益率（百分比）
        """
        if len(self.equity_curve) == 0:
            return 0.0

        initial_equity = self.equity_curve.iloc[0]
        final_equity = self.equity_curve.iloc[-1]

        if initial_equity == 0:
            return 0.0

        return (final_equity / initial_equity - 1) * 100

    def annualized_return(self, trading_days: int = 365) -> float:
        """
        计算年化收益率

        Args:
            trading_days: 每年交易天数（默认 365）

        Returns:
            年化收益率（百分比）
        """
        if len(self.equity_curve) < 2:
            return 0.0

        total_days = (self.equity_curve.index[-1] - self.equity_curve.index[0]).days
        if total_days == 0:
            return 0.0

        total_ret = self.total_return() / 100
        years = total_days / trading_days

        if years == 0:
            return 0.0

        annualized = (1 + total_ret) ** (1 / years) - 1
        return annualized * 100

    def max_drawdown(self) -> Dict[str, Any]:
        """
        计算最大回撤

        Returns:
            包含最大回撤、开始时间、结束时间、恢复时间的字典
        """
        if len(self.equity_curve) == 0:
            return {
                "max_drawdown": 0.0,
                "start_date": None,
                "end_date": None,
                "recovery_date": None,
                "duration_days": 0,
            }

        # 计算累计最高点
        cummax = self.equity_curve.cummax()

        # 计算回撤
        drawdown = (self.equity_curve - cummax) / cummax * 100

        # 找到最大回撤
        max_dd = drawdown.min()
        max_dd_idx = drawdown.idxmin()

        # 找到最大回撤开始时间（之前的最高点）
        start_idx = self.equity_curve[:max_dd_idx].idxmax()

        # 找到恢复时间（之后权益超过开始时的最高点）
        recovery_idx = None
        peak_value = self.equity_curve.loc[start_idx]
        after_drawdown = self.equity_curve[max_dd_idx:]

        for idx, value in after_drawdown.items():
            if value >= peak_value:
                recovery_idx = idx
                break

        # 计算持续时间
        duration_days = (max_dd_idx - start_idx).days if start_idx else 0

        return {
            "max_drawdown": abs(max_dd),
            "start_date": start_idx,
            "end_date": max_dd_idx,
            "recovery_date": recovery_idx,
            "duration_days": duration_days,
        }

    def volatility(self, annualize: bool = True, trading_days: int = 365) -> float:
        """
        计算波动率（标准差）

        Args:
            annualize: 是否年化
            trading_days: 每年交易天数

        Returns:
            波动率（百分比）
        """
        if len(self.returns) == 0:
            return 0.0

        vol = self.returns.std() * 100

        if annualize:
            vol *= np.sqrt(trading_days)

        return vol

    def downside_volatility(self, annualize: bool = True, trading_days: int = 365) -> float:
        """
        计算下行波动率（只考虑负收益）

        Args:
            annualize: 是否年化
            trading_days: 每年交易天数

        Returns:
            下行波动率（百分比）
        """
        if len(self.returns) == 0:
            return 0.0

        negative_returns = self.returns[self.returns < 0]

        if len(negative_returns) == 0:
            return 0.0

        downside_vol = negative_returns.std() * 100

        if annualize:
            downside_vol *= np.sqrt(trading_days)

        return downside_vol

    def sharpe_ratio(self, risk_free_rate: float = 0.0, trading_days: int = 365) -> float:
        """
        计算夏普比率

        Args:
            risk_free_rate: 无风险利率（年化百分比）
            trading_days: 每年交易天数

        Returns:
            夏普比率
        """
        ann_return = self.annualized_return(trading_days)
        ann_vol = self.volatility(annualize=True, trading_days=trading_days)

        if ann_vol == 0:
            return 0.0

        return (ann_return - risk_free_rate) / ann_vol

    def sortino_ratio(self, risk_free_rate: float = 0.0, trading_days: int = 365) -> float:
        """
        计算索提诺比率（使用下行波动率）

        Args:
            risk_free_rate: 无风险利率（年化百分比）
            trading_days: 每年交易天数

        Returns:
            索提诺比率
        """
        ann_return = self.annualized_return(trading_days)
        downside_vol = self.downside_volatility(annualize=True, trading_days=trading_days)

        if downside_vol == 0:
            return 0.0

        return (ann_return - risk_free_rate) / downside_vol

    def calmar_ratio(self, trading_days: int = 365) -> float:
        """
        计算卡玛比率（年化收益 / 最大回撤）

        Args:
            trading_days: 每年交易天数

        Returns:
            卡玛比率
        """
        ann_return = self.annualized_return(trading_days)
        max_dd = self.max_drawdown()["max_drawdown"]

        if max_dd == 0:
            return 0.0

        return ann_return / max_dd

    def win_rate(self) -> float:
        """
        计算胜率

        Returns:
            胜率（百分比）
        """
        if self.trades is None or len(self.trades) == 0:
            return 0.0

        # 假设 trades DataFrame 有 'pnl' 列
        if "pnl" not in self.trades.columns:
            return 0.0

        winning_trades = len(self.trades[self.trades["pnl"] > 0])
        total_trades = len(self.trades)

        if total_trades == 0:
            return 0.0

        return (winning_trades / total_trades) * 100

    def profit_factor(self) -> float:
        """
        计算盈亏比（总盈利 / 总亏损）

        Returns:
            盈亏比
        """
        if self.trades is None or len(self.trades) == 0:
            return 0.0

        if "pnl" not in self.trades.columns:
            return 0.0

        gross_profit = self.trades[self.trades["pnl"] > 0]["pnl"].sum()
        gross_loss = abs(self.trades[self.trades["pnl"] < 0]["pnl"].sum())

        if gross_loss == 0:
            return 0.0 if gross_profit == 0 else float("inf")

        return gross_profit / gross_loss

    def average_trade(self) -> float:
        """
        计算平均每笔交易盈亏

        Returns:
            平均盈亏
        """
        if self.trades is None or len(self.trades) == 0:
            return 0.0

        if "pnl" not in self.trades.columns:
            return 0.0

        return self.trades["pnl"].mean()

    def total_trades(self) -> int:
        """
        计算总交易次数

        Returns:
            交易次数
        """
        if self.trades is None:
            return 0

        return len(self.trades)

    def get_all_metrics(
        self, risk_free_rate: float = 0.0, trading_days: int = 365
    ) -> Dict[str, Any]:
        """
        计算所有性能指标

        Args:
            risk_free_rate: 无风险利率（年化百分比）
            trading_days: 每年交易天数

        Returns:
            包含所有指标的字典
        """
        max_dd_info = self.max_drawdown()

        metrics = {
            # 收益指标
            "total_return": self.total_return(),
            "annualized_return": self.annualized_return(trading_days),
            # 风险指标
            "max_drawdown": max_dd_info["max_drawdown"],
            "max_drawdown_duration": max_dd_info["duration_days"],
            "volatility": self.volatility(annualize=True, trading_days=trading_days),
            "downside_volatility": self.downside_volatility(
                annualize=True, trading_days=trading_days
            ),
            # 风险调整收益指标
            "sharpe_ratio": self.sharpe_ratio(risk_free_rate, trading_days),
            "sortino_ratio": self.sortino_ratio(risk_free_rate, trading_days),
            "calmar_ratio": self.calmar_ratio(trading_days),
            # 交易统计
            "total_trades": self.total_trades(),
            "win_rate": self.win_rate(),
            "profit_factor": self.profit_factor(),
            "average_trade": self.average_trade(),
            # 时间信息
            "start_date": self.equity_curve.index[0] if len(self.equity_curve) > 0 else None,
            "end_date": self.equity_curve.index[-1] if len(self.equity_curve) > 0 else None,
            "total_days": (self.equity_curve.index[-1] - self.equity_curve.index[0]).days
            if len(self.equity_curve) > 1
            else 0,
        }

        return metrics
