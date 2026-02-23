"""
Keltner Channel Indicator

Keltner Channel 是一个基于 EMA 和 ATR 的波动率通道指标。
包含 EMA、ATR、Bollinger Bands 等基础指标计算。
"""

from collections import deque
import numpy as np
from config.constants import (
    EMA_ALPHA_NUMERATOR,
    EMA_ALPHA_DENOMINATOR_OFFSET,
    ATR_ALPHA_NUMERATOR,
)


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

        # 数据存储
        max_period = max(ema_period, bb_period, sma_period)
        self.closes = deque(maxlen=max_period + 1)
        self.volumes = deque(maxlen=volume_period + 1)
        self.trs = deque(maxlen=atr_period)

        # 指标值
        self.ema: float | None = None
        self.atr: float | None = None
        self.sma: float | None = None
        self.bb_upper: float | None = None
        self.bb_lower: float | None = None
        self.volume_sma: float | None = None

    def update(self, high: float, low: float, close: float, volume: float) -> None:
        """
        更新指标数据

        Args:
            high: 最高价
            low: 最低价
            close: 收盘价
            volume: 成交量
        """
        self.closes.append(close)
        self.volumes.append(volume)

        # 计算 True Range
        if len(self.closes) > 1:
            tr = max(high - low, abs(high - self.closes[-2]), abs(low - self.closes[-2]))
            self.trs.append(tr)

        # 更新所有指标
        self._update_ema()
        self._update_atr()
        self._update_sma()
        self._update_bollinger_bands()
        self._update_volume_sma()

    def _update_ema(self) -> None:
        """更新 EMA 指标"""
        if len(self.closes) < self.ema_period:
            return

        if self.ema is None:
            self.ema = sum(list(self.closes)[-self.ema_period :]) / self.ema_period
        else:
            alpha = EMA_ALPHA_NUMERATOR / (self.ema_period + EMA_ALPHA_DENOMINATOR_OFFSET)
            self.ema = alpha * self.closes[-1] + (1 - alpha) * self.ema

    def _update_atr(self) -> None:
        """更新 ATR 指标 (Wilder's Smoothing / RMA)"""
        if len(self.trs) < self.atr_period:
            return

        if self.atr is None:
            self.atr = sum(list(self.trs)[-self.atr_period :]) / self.atr_period
        else:
            alpha = ATR_ALPHA_NUMERATOR / self.atr_period
            self.atr = alpha * self.trs[-1] + (1 - alpha) * self.atr

    def _update_sma(self) -> None:
        """更新 SMA 指标"""
        if len(self.closes) >= self.sma_period:
            self.sma = sum(list(self.closes)[-self.sma_period :]) / self.sma_period

    def _update_bollinger_bands(self) -> None:
        """更新 Bollinger Bands 指标"""
        if len(self.closes) >= self.bb_period:
            bb_closes = np.array(list(self.closes)[-self.bb_period :])
            bb_mean = bb_closes.mean()
            bb_std = bb_closes.std()
            self.bb_upper = bb_mean + self.bb_std * bb_std
            self.bb_lower = bb_mean - self.bb_std * bb_std

    def _update_volume_sma(self) -> None:
        """更新 Volume SMA 指标"""
        if len(self.volumes) >= self.volume_period:
            self.volume_sma = sum(list(self.volumes)[-self.volume_period :]) / self.volume_period

    def get_keltner_base_bands(self) -> tuple[float | None, float | None]:
        """
        获取 Keltner Base 通道（用于 Squeeze 判定）

        Returns:
            (upper_band, lower_band) 或 (None, None)
        """
        if self.ema is None or self.atr is None:
            return None, None

        upper = self.ema + (self.keltner_base_multiplier * self.atr)
        lower = self.ema - (self.keltner_base_multiplier * self.atr)
        return upper, lower

    def get_keltner_trigger_bands(self) -> tuple[float | None, float | None]:
        """
        获取 Keltner Trigger 通道（用于突破判定）

        Returns:
            (upper_band, lower_band) 或 (None, None)
        """
        if self.ema is None or self.atr is None:
            return None, None

        upper = self.ema + (self.keltner_trigger_multiplier * self.atr)
        lower = self.ema - (self.keltner_trigger_multiplier * self.atr)
        return upper, lower

    def is_squeezing(self) -> bool:
        """
        判断是否处于 Squeeze 状态

        Squeeze 定义：布林带完全在 Keltner Base 通道内

        Returns:
            True 表示处于 Squeeze 状态
        """
        if self.bb_upper is None or self.bb_lower is None:
            return False

        keltner_upper, keltner_lower = self.get_keltner_base_bands()
        if keltner_upper is None or keltner_lower is None:
            return False

        return self.bb_upper < keltner_upper and self.bb_lower > keltner_lower

    def is_ready(self) -> bool:
        """
        判断指标是否已准备好（所有指标都已计算）

        Returns:
            True 表示所有指标都已计算完成
        """
        return (
            self.ema is not None
            and self.atr is not None
            and self.sma is not None
            and self.bb_upper is not None
            and self.bb_lower is not None
            and self.volume_sma is not None
        )
