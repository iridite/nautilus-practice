"""
Market Regime Filter

基于 BTC 市场状态过滤交易信号，判断是否适合做多山寨币。
"""

from collections import deque


class MarketRegimeFilter:
    """
    市场状态过滤器

    基于 BTC 的趋势和波动率判断市场状态：
    - 趋势检查：BTC > SMA(200) 表示牛市结构
    - 波动率检查：ATR% < 阈值 表示波动率未极端放大

    只有在 BTC 处于牛市且波动率可控时，才适合做多山寨币。
    """

    def __init__(
        self,
        sma_period: int = 200,
        atr_period: int = 14,
        max_atr_pct: float = 0.03,  # 3%
    ):
        """
        初始化市场状态过滤器

        Args:
            sma_period: SMA 周期（用于趋势判定）
            atr_period: ATR 周期（用于波动率计算）
            max_atr_pct: ATR 百分比阈值（超过此值表示波动率过高）
        """
        self.sma_period = sma_period
        self.atr_period = atr_period
        self.max_atr_pct = max_atr_pct

        # 数据存储
        self.closes = deque(maxlen=max(sma_period, atr_period) + 1)
        self.trs = deque(maxlen=atr_period)

        # 指标值
        self.sma: float | None = None
        self.atr: float | None = None

    def update(self, high: float, low: float, close: float) -> None:
        """
        更新市场状态数据

        Args:
            high: 最高价
            low: 最低价
            close: 收盘价
        """
        self.closes.append(close)

        # 计算 True Range
        if len(self.closes) > 1:
            tr = max(
                high - low,
                abs(high - self.closes[-2]),
                abs(low - self.closes[-2])
            )
            self.trs.append(tr)

        # 更新指标
        self._update_sma()
        self._update_atr()

    def _update_sma(self) -> None:
        """更新 SMA 指标"""
        if len(self.closes) >= self.sma_period:
            self.sma = sum(list(self.closes)[-self.sma_period:]) / self.sma_period

    def _update_atr(self) -> None:
        """更新 ATR 指标 (Wilder's Smoothing)"""
        if len(self.trs) < self.atr_period:
            return

        if self.atr is None:
            self.atr = sum(list(self.trs)[-self.atr_period:]) / self.atr_period
        else:
            alpha = 1.0 / self.atr_period
            self.atr = alpha * self.trs[-1] + (1 - alpha) * self.atr

    def is_bullish_regime(self) -> bool:
        """
        判断是否处于牛市状态

        Returns:
            True 表示 BTC 处于牛市结构（价格 > SMA）
        """
        if self.sma is None or not self.closes:
            return False

        return self.closes[-1] > self.sma

    def is_low_volatility(self) -> bool:
        """
        判断波动率是否可控

        Returns:
            True 表示波动率未极端放大（ATR% < 阈值）
        """
        if self.atr is None or not self.closes:
            return False

        current_price = self.closes[-1]
        if current_price <= 0:
            return False

        atr_pct = self.atr / current_price
        return atr_pct <= self.max_atr_pct

    def is_favorable_for_altcoins(self) -> bool:
        """
        判断市场状态是否适合做多山寨币

        Returns:
            True 表示市场状态良好（牛市 + 低波动率）
        """
        return self.is_bullish_regime() and self.is_low_volatility()

    def get_atr_pct(self) -> float | None:
        """
        获取当前 ATR 百分比

        Returns:
            ATR% 或 None（如果数据不足）
        """
        if self.atr is None or not self.closes:
            return None

        current_price = self.closes[-1]
        if current_price <= 0:
            return None

        return self.atr / current_price

    def is_ready(self) -> bool:
        """
        判断指标是否已准备好

        Returns:
            True 表示所有指标都已计算完成
        """
        return self.sma is not None and self.atr is not None
