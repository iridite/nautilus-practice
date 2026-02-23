"""
Dual Thrust Indicator

Dual Thrust 是一个经典的日内突破策略指标，基于前 N 天的价格范围计算动态通道。

计算逻辑：
- HH = 前 N 天最高价
- LL = 前 N 天最低价
- HC = 前 N 天最高收盘价
- LC = 前 N 天最低收盘价
- Range = Max(HH - LC, HC - LL)
- 上轨 = Open + k1 * Range
- 下轨 = Open - k2 * Range
"""

from collections import deque


class DualThrustIndicator:
    """
    Dual Thrust 指标计算器

    计算基于历史价格范围的动态突破通道。
    """

    def __init__(
        self,
        lookback_period: int = 4,
        k1: float = 0.5,
        k2: float = 0.5,
    ):
        """
        初始化 Dual Thrust 指标

        Args:
            lookback_period: 回溯周期（天数）
            k1: 上轨系数
            k2: 下轨系数
        """
        self.lookback_period = lookback_period
        self.k1 = k1
        self.k2 = k2

        # 价格历史
        self.highs = deque(maxlen=lookback_period + 1)
        self.lows = deque(maxlen=lookback_period + 1)
        self.closes = deque(maxlen=lookback_period + 1)

        # 指标值
        self.upper_band: float | None = None
        self.lower_band: float | None = None
        self.range_value: float | None = None

    def update(self, high: float, low: float, close: float, open_price: float) -> None:
        """
        更新指标数据

        Args:
            high: 最高价
            low: 最低价
            close: 收盘价
            open_price: 开盘价（用于计算当前通道）
        """
        self.highs.append(high)
        self.lows.append(low)
        self.closes.append(close)

        # 如果数据足够，计算通道
        if len(self.highs) > self.lookback_period:
            self._calculate_bands(open_price)

    def _calculate_bands(self, open_price: float) -> None:
        """
        计算上下轨

        Args:
            open_price: 当前开盘价
        """
        # 使用前 N 天的数据（不包括当前 bar）
        lookback_highs = list(self.highs)[:-1]
        lookback_lows = list(self.lows)[:-1]
        lookback_closes = list(self.closes)[:-1]

        # 计算关键价格
        hh = max(lookback_highs)  # 最高价
        ll = min(lookback_lows)  # 最低价
        hc = max(lookback_closes)  # 最高收盘价
        lc = min(lookback_closes)  # 最低收盘价

        # 计算 Range
        self.range_value = max(hh - lc, hc - ll)

        # 计算通道
        self.upper_band = open_price + self.k1 * self.range_value
        self.lower_band = open_price - self.k2 * self.range_value

    def is_ready(self) -> bool:
        """
        判断指标是否已准备好

        Returns:
            True 表示数据足够，可以使用指标
        """
        return (
            len(self.highs) > self.lookback_period
            and self.upper_band is not None
            and self.lower_band is not None
        )

    def get_bands(self) -> tuple[float | None, float | None]:
        """
        获取上下轨

        Returns:
            (upper_band, lower_band) 或 (None, None)
        """
        return self.upper_band, self.lower_band

    def get_range(self) -> float | None:
        """
        获取当前 Range 值

        Returns:
            Range 值或 None
        """
        return self.range_value
