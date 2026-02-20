"""
Strategy Analyzer

策略分析器，用于对比多个策略的回测结果。
"""

import pandas as pd
from typing import Dict, List, Any
from .metrics import PerformanceMetrics


class StrategyAnalyzer:
    """
    策略分析器

    用于加载、对比和分析多个策略的回测结果。
    """

    def __init__(self):
        """初始化策略分析器"""
        self.strategies: Dict[str, Dict[str, Any]] = {}

    def add_strategy(
        self,
        name: str,
        equity_curve: pd.Series,
        trades: pd.DataFrame | None = None,
        metadata: Dict[str, Any] | None = None,
    ):
        """
        添加策略回测结果

        Args:
            name: 策略名称
            equity_curve: 权益曲线
            trades: 交易记录
            metadata: 策略元数据（参数、描述等）
        """
        self.strategies[name] = {
            "equity_curve": equity_curve,
            "trades": trades,
            "metadata": metadata or {},
            "metrics": None,  # 延迟计算
        }

    def calculate_metrics(
        self,
        strategy_name: str | None = None,
        risk_free_rate: float = 0.0,
        trading_days: int = 365,
    ) -> Dict[str, Any]:
        """
        计算策略的性能指标

        Args:
            strategy_name: 策略名称（None 表示计算所有策略）
            risk_free_rate: 无风险利率
            trading_days: 每年交易天数

        Returns:
            策略指标字典
        """
        if strategy_name:
            # 计算单个策略
            if strategy_name not in self.strategies:
                raise ValueError(f"策略 '{strategy_name}' 不存在")

            strategy = self.strategies[strategy_name]
            metrics_calc = PerformanceMetrics(
                equity_curve=strategy["equity_curve"],
                trades=strategy["trades"],
            )
            strategy["metrics"] = metrics_calc.get_all_metrics(risk_free_rate, trading_days)
            return strategy["metrics"]
        else:
            # 计算所有策略
            results = {}
            for name in self.strategies:
                results[name] = self.calculate_metrics(name, risk_free_rate, trading_days)
            return results

    def compare_strategies(
        self,
        metrics: List[str] | None = None,
        risk_free_rate: float = 0.0,
        trading_days: int = 365,
    ) -> pd.DataFrame:
        """
        对比多个策略的性能指标

        Args:
            metrics: 要对比的指标列表（None 表示所有指标）
            risk_free_rate: 无风险利率
            trading_days: 每年交易天数

        Returns:
            对比结果 DataFrame
        """
        if not self.strategies:
            return pd.DataFrame()

        # 确保所有策略都已计算指标
        self.calculate_metrics(risk_free_rate=risk_free_rate, trading_days=trading_days)

        # 收集所有策略的指标
        comparison_data = {}
        for name, strategy in self.strategies.items():
            comparison_data[name] = strategy["metrics"]

        # 转换为 DataFrame
        df = pd.DataFrame(comparison_data).T

        # 筛选指定的指标
        if metrics:
            available_metrics = [m for m in metrics if m in df.columns]
            df = df[available_metrics]

        return df

    def rank_strategies(
        self,
        by: str = "sharpe_ratio",
        ascending: bool = False,
        risk_free_rate: float = 0.0,
        trading_days: int = 365,
    ) -> pd.DataFrame:
        """
        按指定指标对策略排名

        Args:
            by: 排名依据的指标
            ascending: 是否升序排列
            risk_free_rate: 无风险利率
            trading_days: 每年交易天数

        Returns:
            排名结果 DataFrame
        """
        comparison = self.compare_strategies(
            risk_free_rate=risk_free_rate,
            trading_days=trading_days,
        )

        if by not in comparison.columns:
            raise ValueError(f"指标 '{by}' 不存在")

        return comparison.sort_values(by=by, ascending=ascending)

    def get_best_strategy(
        self,
        by: str = "sharpe_ratio",
        risk_free_rate: float = 0.0,
        trading_days: int = 365,
    ) -> tuple[str, Dict[str, Any]]:
        """
        获取最佳策略

        Args:
            by: 评判标准（指标名称）
            risk_free_rate: 无风险利率
            trading_days: 每年交易天数

        Returns:
            (策略名称, 策略指标) 元组
        """
        ranked = self.rank_strategies(
            by=by,
            ascending=False,
            risk_free_rate=risk_free_rate,
            trading_days=trading_days,
        )

        if len(ranked) == 0:
            raise ValueError("没有可用的策略")

        best_name = ranked.index[0]
        best_metrics = ranked.iloc[0].to_dict()

        return best_name, best_metrics

    def get_correlation_matrix(self) -> pd.DataFrame:
        """
        计算策略收益率的相关性矩阵

        Returns:
            相关性矩阵 DataFrame
        """
        if not self.strategies:
            return pd.DataFrame()

        # 收集所有策略的收益率
        returns_data = {}
        for name, strategy in self.strategies.items():
            equity_curve = strategy["equity_curve"]
            returns = equity_curve.pct_change().dropna()
            returns_data[name] = returns

        # 对齐时间序列
        returns_df = pd.DataFrame(returns_data)

        # 计算相关性
        return returns_df.corr()

    def get_summary_statistics(
        self,
        risk_free_rate: float = 0.0,
        trading_days: int = 365,
    ) -> Dict[str, Any]:
        """
        获取所有策略的汇总统计

        Args:
            risk_free_rate: 无风险利率
            trading_days: 每年交易天数

        Returns:
            汇总统计字典
        """
        if not self.strategies:
            return {}

        comparison = self.compare_strategies(
            risk_free_rate=risk_free_rate,
            trading_days=trading_days,
        )

        # 数值型列
        numeric_cols = comparison.select_dtypes(include=["number"]).columns

        summary = {
            "count": len(self.strategies),
            "mean": comparison[numeric_cols].mean().to_dict(),
            "std": comparison[numeric_cols].std().to_dict(),
            "min": comparison[numeric_cols].min().to_dict(),
            "max": comparison[numeric_cols].max().to_dict(),
        }

        return summary

    def filter_strategies(
        self,
        min_sharpe: float | None = None,
        max_drawdown: float | None = None,
        min_win_rate: float | None = None,
        min_trades: int | None = None,
        risk_free_rate: float = 0.0,
        trading_days: int = 365,
    ) -> List[str]:
        """
        根据条件筛选策略

        Args:
            min_sharpe: 最小夏普率
            max_drawdown: 最大回撤上限
            min_win_rate: 最小胜率
            min_trades: 最小交易次数
            risk_free_rate: 无风险利率
            trading_days: 每年交易天数

        Returns:
            符合条件的策略名称列表
        """
        comparison = self.compare_strategies(
            risk_free_rate=risk_free_rate,
            trading_days=trading_days,
        )

        filtered = comparison.copy()

        if min_sharpe is not None:
            filtered = filtered[filtered["sharpe_ratio"] >= min_sharpe]

        if max_drawdown is not None:
            filtered = filtered[filtered["max_drawdown"] <= max_drawdown]

        if min_win_rate is not None:
            filtered = filtered[filtered["win_rate"] >= min_win_rate]

        if min_trades is not None:
            filtered = filtered[filtered["total_trades"] >= min_trades]

        return filtered.index.tolist()

    def clear(self):
        """清空所有策略数据"""
        self.strategies.clear()

    def remove_strategy(self, name: str):
        """
        移除指定策略

        Args:
            name: 策略名称
        """
        if name in self.strategies:
            del self.strategies[name]

    def get_strategy_names(self) -> List[str]:
        """
        获取所有策略名称

        Returns:
            策略名称列表
        """
        return list(self.strategies.keys())
