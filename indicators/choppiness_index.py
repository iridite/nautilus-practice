"""
Choppiness Index (CHOP) 指标实现

CHOP 用于衡量市场的震荡程度:
- CHOP > 61.8: 市场震荡，横盘整理
- CHOP < 38.2: 市场趋势明显
"""

import numpy as np
from nautilus_trader.model.data import Bar


class ChoppinessIndex:
    """
    Choppiness Index (CHOP) 指标

    公式: CHOP = 100 * LOG10(SUM(ATR, period) / (MAX(high, period) - MIN(low, period))) / LOG10(period)

    Parameters
    ----------
    period : int
        计算周期（默认 14）
    """

    def __init__(self, period: int = 14):
        self.period = period
        self._highs = []
        self._lows = []
        self._closes = []
        self._trs = []
        self.value = 0.0

    @property
    def name(self) -> str:
        return f"ChoppinessIndex({self.period})"

    @property
    def has_inputs(self) -> bool:
        return len(self._highs) > 0

    @property
    def initialized(self) -> bool:
        return len(self._highs) >= self.period

    def _calculate_tr(self, high: float, low: float, prev_close: float) -> float:
        """计算 True Range"""
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        return max(tr1, tr2, tr3)

    def handle_bar(self, bar: Bar) -> None:
        """处理新的 Bar 数据"""
        self.update_raw(float(bar.high), float(bar.low), float(bar.close))

    def update_raw(self, high: float, low: float, close: float) -> None:
        """更新指标值"""
        self._highs.append(high)
        self._lows.append(low)
        self._closes.append(close)

        # 计算 TR
        if len(self._closes) > 1:
            tr = self._calculate_tr(high, low, self._closes[-2])
            self._trs.append(tr)

        # 保持窗口大小
        if len(self._highs) > self.period:
            self._highs.pop(0)
            self._lows.pop(0)
            self._closes.pop(0)
        if len(self._trs) > self.period:
            self._trs.pop(0)

        # 计算 CHOP
        if self.initialized and len(self._trs) >= self.period:
            atr_sum = sum(self._trs[-self.period :])
            high_max = max(self._highs[-self.period :])
            low_min = min(self._lows[-self.period :])

            if high_max > low_min:
                self.value = 100 * np.log10(atr_sum / (high_max - low_min)) / np.log10(self.period)
            else:
                self.value = 0.0

    def reset(self) -> None:
        """重置指标"""
        self._highs.clear()
        self._lows.clear()
        self._closes.clear()
        self._trs.clear()
        self.value = 0.0
