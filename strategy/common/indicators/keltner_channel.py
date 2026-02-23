"""
Keltner Channel Indicator

Keltner Channel 是一个基于 EMA 和 ATR 的波动率通道指标。
包含 EMA、ATR、Bollinger Bands 等基础指标计算。
"""

from nautilus_trader.indicators import (
    ExponentialMovingAverage,
    SimpleMovingAverage,
    AverageTrueRange,
)
from nautilus_trader.indicators.volatility import BollingerBands


class KeltnerChannel:
    """
    Keltner Channel 指标计算器

    包含：
    - EMA (Exponential Moving Average)
    - ATR (Average True Range, Wilder's Smoothing)
    - SMA (Simple Moving Average)
    - Bollinger Bands
    - Volume SMA
    """

    def __init__(
        self,
        ema_period: int = 20,
        atr_period: int = 20,
        sma_period: int = 200,
        bb_period: int = 20,
        bb_std: float = 2.0,
        volume_period: int = 20,
        keltner_base_multiplier: float = 1.5,
        keltner_trigger_multiplier: float = 2.25,
    ):
        """
        初始化 Keltner Channel 指标

        Args:
            ema_period: EMA 周期
            atr_period: ATR 周期
            sma_period: SMA 周期
            bb_period: Bollinger Bands 周期
            bb_std: Bollinger Bands 标准差倍数
            volume_period: 成交量 SMA 周期
            keltner_base_multiplier: Keltner Base 通道倍数（用于 Squeeze 判定）
            keltner_trigger_multiplier: Keltner Trigger 通道倍数（用于突破判定）
        """
        self.ema_period = ema_period
        self.atr_period = atr_period
        self.sma_period = sma_period
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.volume_period = volume_period
        self.keltner_base_multiplier = keltner_base_multiplier
        self.keltner_trigger_multiplier = keltner_trigger_multiplier

        # NautilusTrader 指标实例
        self.ema_indicator = ExponentialMovingAverage(period=ema_period)
        self.atr_indicator = AverageTrueRange(period=atr_period)
        self.sma_indicator = SimpleMovingAverage(period=sma_period)
        self.bb = BollingerBands(period=bb_period, k=bb_std)
        self.volume_sma_indicator = SimpleMovingAverage(period=volume_period)

    def update(self, high: float, low: float, close: float, volume: float) -> None:
        """
        更新指标数据

        Args:
            high: 最高价
            low: 最低价
            close: 收盘价
            volume: 成交量
        """
        # 更新所有 NautilusTrader 指标
        self.ema_indicator.update_raw(close)
        self.atr_indicator.update_raw(high, low, close)
        self.sma_indicator.update_raw(close)
        self.bb.update_raw(high, low, close)
        self.volume_sma_indicator.update_raw(volume)

    @property
    def ema(self) -> float | None:
        """获取 EMA 值"""
        return self.ema_indicator.value if self.ema_indicator.initialized else None

    @property
    def atr(self) -> float | None:
        """获取 ATR 值"""
        return self.atr_indicator.value if self.atr_indicator.initialized else None

    @property
    def sma(self) -> float | None:
        """获取 SMA 值"""
        return self.sma_indicator.value if self.sma_indicator.initialized else None

    @property
    def volume_sma(self) -> float | None:
        """获取 Volume SMA 值"""
        return self.volume_sma_indicator.value if self.volume_sma_indicator.initialized else None

    def get_keltner_base_bands(self) -> tuple[float | None, float | None]:
        """
        获取 Keltner Base 通道（用于 Squeeze 判定）

        Returns:
            (upper_band, lower_band) 或 (None, None)
        """
        if not self.ema_indicator.initialized or not self.atr_indicator.initialized:
            return None, None

        ema_value = self.ema_indicator.value
        atr_value = self.atr_indicator.value

        upper = ema_value + (self.keltner_base_multiplier * atr_value)
        lower = ema_value - (self.keltner_base_multiplier * atr_value)
        return upper, lower

    def get_keltner_trigger_bands(self) -> tuple[float | None, float | None]:
        """
        获取 Keltner Trigger 通道（用于突破判定）

        Returns:
            (upper_band, lower_band) 或 (None, None)
        """
        if not self.ema_indicator.initialized or not self.atr_indicator.initialized:
            return None, None

        ema_value = self.ema_indicator.value
        atr_value = self.atr_indicator.value

        upper = ema_value + (self.keltner_trigger_multiplier * atr_value)
        lower = ema_value - (self.keltner_trigger_multiplier * atr_value)
        return upper, lower

    def is_squeezing(self) -> bool:
        """
        判断是否处于 Squeeze 状态

        Squeeze 定义：布林带完全在 Keltner Base 通道内

        Returns:
            True 表示处于 Squeeze 状态
        """
        if not self.bb.initialized:
            return False

        bb_upper = self.bb.upper
        bb_lower = self.bb.lower

        keltner_upper, keltner_lower = self.get_keltner_base_bands()
        if keltner_upper is None or keltner_lower is None:
            return False

        return bb_upper < keltner_upper and bb_lower > keltner_lower

    def is_ready(self) -> bool:
        """
        判断指标是否已准备好（所有指标都已计算）

        Returns:
            True 表示所有指标都已计算完成
        """
        return (
            self.ema_indicator.initialized
            and self.atr_indicator.initialized
            and self.sma_indicator.initialized
            and self.bb.initialized
            and self.volume_sma_indicator.initialized
        )
