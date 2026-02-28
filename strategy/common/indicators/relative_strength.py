"""
Relative Strength (RS) Calculator

计算标的相对于 BTC 的相对强度，用于过滤强势币种。
"""

from collections import OrderedDict


class RelativeStrengthCalculator:
    """
    相对强度计算器

    计算标的相对于基准（通常是 BTC）的相对强度：
    RS = (Symbol% - Benchmark%)
    其中 Symbol% 和 Benchmark% 是百分比收益率

    支持多周期加权组合：
    Combined RS = short_weight * RS(short) + long_weight * RS(long)
    """

    def __init__(
        self,
        short_lookback_days: int = 5,
        long_lookback_days: int = 20,
        short_weight: float = 0.4,
        long_weight: float = 0.6,
        max_history_size: int = 500,
    ):
        """
        初始化相对强度计算器

        Args:
            short_lookback_days: 短期回溯天数
            long_lookback_days: 长期回溯天数
            short_weight: 短期权重
            long_weight: 长期权重
            max_history_size: 历史数据最大保存数量
        """
        self.short_lookback_days = short_lookback_days
        self.long_lookback_days = long_lookback_days
        self.short_weight = short_weight
        self.long_weight = long_weight
        self.max_history_size = max_history_size

        # 价格历史（使用 OrderedDict 保持插入顺序）
        self.symbol_price_history = OrderedDict()  # {timestamp: price}
        self.benchmark_price_history = OrderedDict()  # {timestamp: price}

    def update_symbol_price(self, timestamp: int, price: float) -> None:
        """
        更新标的价格历史

        Args:
            timestamp: 时间戳（纳秒）
            price: 价格
        """
        self.symbol_price_history[timestamp] = price

        # 清理过期数据
        if len(self.symbol_price_history) > self.max_history_size:
            self.symbol_price_history.popitem(last=False)

    def update_benchmark_price(self, timestamp: int, price: float) -> None:
        """
        更新基准价格历史

        Args:
            timestamp: 时间戳（纳秒）
            price: 价格
        """
        self.benchmark_price_history[timestamp] = price

        # 清理过期数据
        if len(self.benchmark_price_history) > self.max_history_size:
            self.benchmark_price_history.popitem(last=False)

    def _get_common_timestamps(self) -> list[int] | None:
        """
        获取标的和基准的共同时间戳

        Returns:
            排序后的共同时间戳列表，如果数据不足则返回 None
        """
        max_lookback = max(self.short_lookback_days, self.long_lookback_days)

        if len(self.symbol_price_history) < max_lookback + 1:
            return None
        if len(self.benchmark_price_history) < max_lookback + 1:
            return None

        common_timestamps = sorted(
            set(self.symbol_price_history.keys()) & set(self.benchmark_price_history.keys())
        )

        if len(common_timestamps) < max_lookback + 1:
            return None

        return common_timestamps

    def _calculate_period_rs(
        self, common_timestamps: list[int], lookback_days: int
    ) -> float | None:
        """
        计算指定周期的 RS 值

        Args:
            common_timestamps: 共同时间戳列表
            lookback_days: 回溯天数

        Returns:
            RS 值，如果数据不足或无效则返回 None
        """
        # 边界检查：确保有足够的时间戳（需要 lookback_days + 1 个点）
        if len(common_timestamps) < lookback_days + 1:
            return None

        period_ts = common_timestamps[-(lookback_days + 1) :]

        # 边界检查：确保切片后仍有足够的数据点
        if len(period_ts) < lookback_days + 1:
            return None

        symbol_prices = [self.symbol_price_history[ts] for ts in period_ts]
        benchmark_prices = [self.benchmark_price_history[ts] for ts in period_ts]

        # 边界检查：确保价格列表不为空
        if not symbol_prices or not benchmark_prices:
            return None

        # 检查价格有效性
        if symbol_prices[0] <= 0 or benchmark_prices[0] <= 0:
            return None

        # 计算收益率
        symbol_perf = (symbol_prices[-1] / symbol_prices[0]) - 1
        benchmark_perf = (benchmark_prices[-1] / benchmark_prices[0]) - 1

        # RS = Symbol% - Benchmark%
        return symbol_perf - benchmark_perf

    def calculate_rs(self) -> float | None:
        """
        计算加权组合 RS 分数

        Returns:
            Combined RS = short_weight * RS(short) + long_weight * RS(long)
            如果数据不足则返回 None
        """
        common_timestamps = self._get_common_timestamps()
        if common_timestamps is None:
            return None

        # 计算短期 RS
        short_rs = self._calculate_period_rs(common_timestamps, self.short_lookback_days)
        if short_rs is None:
            return None

        # 计算长期 RS
        long_rs = self._calculate_period_rs(common_timestamps, self.long_lookback_days)
        if long_rs is None:
            return None

        # 加权组合
        combined_rs = self.short_weight * short_rs + self.long_weight * long_rs
        return combined_rs

    def is_strong(self, threshold: float = 0.0) -> bool:
        """
        判断标的是否相对强势

        Args:
            threshold: RS 阈值（默认 0，表示跑赢基准）

        Returns:
            True 表示标的相对强势
        """
        rs = self.calculate_rs()
        return rs is not None and rs > threshold

    def get_symbol_history_size(self) -> int:
        """获取标的价格历史数量"""
        return len(self.symbol_price_history)

    def get_benchmark_history_size(self) -> int:
        """获取基准价格历史数量"""
        return len(self.benchmark_price_history)

    def clear_history(self) -> None:
        """清空所有历史数据"""
        self.symbol_price_history.clear()
        self.benchmark_price_history.clear()
