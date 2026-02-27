"""
Entry and Exit Signal Generators

生成入场和出场信号的模块。
"""

from collections import deque
from decimal import Decimal


class EntrySignalGenerator:
    """
    入场信号生成器

    检查所有入场条件：
    - Keltner 通道突破
    - 成交量放大
    - 价格位置（> SMA）
    - 上影线比例
    """

    def __init__(
        self,
        volume_multiplier: float = 1.5,
        max_upper_wick_ratio: float = 0.3,
        min_body_ratio: float = 0.4,
    ):
        """
        初始化入场信号生成器

        Args:
            volume_multiplier: 成交量放大倍数
            max_upper_wick_ratio: 最大上影线比例
            min_body_ratio: 最小实体比例（实体/全长）
        """
        self.volume_multiplier = volume_multiplier
        self.max_upper_wick_ratio = max_upper_wick_ratio
        self.min_body_ratio = min_body_ratio

    def check_keltner_breakout(
        self,
        close: float,
        keltner_trigger_upper: float | None,
    ) -> bool:
        """
        检查 Keltner 通道突破

        Args:
            close: 收盘价
            keltner_trigger_upper: Keltner Trigger 上轨

        Returns:
            True 表示突破上轨
        """
        if keltner_trigger_upper is None:
            return False

        return close > keltner_trigger_upper

    def check_volume_surge(
        self,
        volume: float,
        volume_sma: float | None,
    ) -> bool:
        """
        检查成交量放大

        Args:
            volume: 当前成交量
            volume_sma: 成交量均值

        Returns:
            True 表示成交量放大
        """
        if volume_sma is None:
            return False

        return volume > volume_sma * self.volume_multiplier

    def check_price_above_sma(
        self,
        close: float,
        sma: float | None,
    ) -> bool:
        """
        检查价格是否在 SMA 之上

        Args:
            close: 收盘价
            sma: SMA 值

        Returns:
            True 表示价格在 SMA 之上
        """
        if sma is None:
            return False

        return close > sma

    def check_wick_ratio(
        self,
        high: float,
        low: float,
        close: float,
    ) -> bool:
        """
        检查上影线比例

        Args:
            high: 最高价
            low: 最低价
            close: 收盘价

        Returns:
            True 表示上影线比例合理
        """
        body_size = high - low
        if body_size <= 0:
            return True

        upper_wick = high - close
        upper_wick_ratio = upper_wick / body_size

        return upper_wick_ratio <= self.max_upper_wick_ratio

    def check_body_quality(
        self,
        open_price: float,
        high: float,
        low: float,
        close: float,
    ) -> bool:
        """
        检查 K线实体质量

        实体质量 = 实体大小 / K线全长
        - 实体大小 = |close - open|
        - K线全长 = high - low
        - 要求实体占比 >= min_body_ratio (默认 40%)

        高质量 K线特征：
        - 实体饱满，影线短
        - 表示趋势明确，买卖力量强劲
        - 避免十字星、陀螺等犹豫形态

        Args:
            open_price: 开盘价
            high: 最高价
            low: 最低价
            close: 收盘价

        Returns:
            True 表示实体质量合格
        """
        full_range = high - low
        if full_range <= 0:
            return False

        body_size = abs(close - open_price)
        body_ratio = body_size / full_range

        return body_ratio >= self.min_body_ratio


class ExitSignalGenerator:
    """
    出场信号生成器

    检查所有出场条件：
    - 时间止损
    - Chandelier Exit 跟踪止损
    - 抛物线止盈
    - RSI 超买止盈
    - 保本止损
    """

    def __init__(
        self,
        enable_time_stop: bool = True,
        time_stop_bars: int = 3,
        time_stop_momentum_threshold: float = 0.01,
        stop_loss_atr_multiplier: float = 2.0,
        deviation_threshold: float = 0.4,
        enable_rsi_stop_loss: bool = False,
        breakeven_multiplier: float = 1.5,
    ):
        """
        初始化出场信号生成器

        Args:
            enable_time_stop: 是否启用时间止损
            time_stop_bars: 时间止损 K 线数
            time_stop_momentum_threshold: 动能确认阈值
            stop_loss_atr_multiplier: 止损 ATR 倍数
            deviation_threshold: 抛物线止盈乖离阈值
            enable_rsi_stop_loss: 是否启用 RSI 超买止损
            breakeven_multiplier: 保本触发 ATR 倍率
        """
        self.enable_time_stop = enable_time_stop
        self.time_stop_bars = time_stop_bars
        self.time_stop_momentum_threshold = time_stop_momentum_threshold
        self.stop_loss_atr_multiplier = stop_loss_atr_multiplier
        self.deviation_threshold = deviation_threshold
        self.enable_rsi_stop_loss = enable_rsi_stop_loss
        self.breakeven_multiplier = breakeven_multiplier

        # 状态变量
        self.breakeven_active = False
        self.rsi_watcher = False

    def check_time_stop(
        self,
        entry_bar_count: int,
        highest_high: float | None,
        entry_price: Decimal | None,
    ) -> bool:
        """
        检查时间止损

        Args:
            entry_bar_count: 开仓后经过的 K 线数
            highest_high: 持仓期间最高价
            entry_price: 开仓价格

        Returns:
            True 表示触发时间止损
        """
        if not self.enable_time_stop or entry_bar_count < self.time_stop_bars:
            return False

        if highest_high is None or entry_price is None:
            return False

        momentum_threshold = 1 + self.time_stop_momentum_threshold
        return highest_high < float(entry_price) * momentum_threshold

    def check_chandelier_exit(
        self,
        close: float,
        highest_high: float | None,
        atr: float | None,
    ) -> bool:
        """
        检查 Chandelier Exit 跟踪止损

        Args:
            close: 收盘价
            highest_high: 持仓期间最高价
            atr: ATR 值

        Returns:
            True 表示触发跟踪止损
        """
        if highest_high is None or atr is None:
            return False

        trailing_stop = highest_high - (self.stop_loss_atr_multiplier * atr)
        return close < trailing_stop

    def check_parabolic_profit(
        self,
        close: float,
        ema: float | None,
    ) -> bool:
        """
        检查抛物线止盈

        Args:
            close: 收盘价
            ema: EMA 值

        Returns:
            True 表示触发抛物线止盈
        """
        if ema is None:
            return False

        deviation_pct = (close - ema) / ema
        return deviation_pct >= self.deviation_threshold

    def check_rsi_overbought(
        self,
        rsi: float | None,
    ) -> bool:
        """
        检查 RSI 超买止盈

        Args:
            rsi: RSI 值

        Returns:
            True 表示触发 RSI 超买止盈
        """
        if rsi is None or not self.enable_rsi_stop_loss:
            return False

        # RSI 超过 85 时开始监控
        if rsi > 85 and not self.rsi_watcher:
            self.rsi_watcher = True
            return False

        # RSI 回落到 85 以下时平仓
        if self.rsi_watcher and rsi <= 85:
            self.rsi_watcher = False
            return True

        return False

    def update_breakeven_status(
        self,
        close: float,
        entry_price: Decimal | None,
        atr: float | None,
    ) -> None:
        """
        更新保本模式状态

        Args:
            close: 收盘价
            entry_price: 开仓价格
            atr: ATR 值
        """
        if atr is None or entry_price is None or self.breakeven_active:
            return

        breakeven_trigger_price = float(entry_price) + (self.breakeven_multiplier * atr)
        if close > breakeven_trigger_price:
            self.breakeven_active = True

    def check_breakeven_stop(
        self,
        close: float,
        entry_price: Decimal | None,
    ) -> bool:
        """
        检查保本止损

        Args:
            close: 收盘价
            entry_price: 开仓价格

        Returns:
            True 表示触发保本止损
        """
        if not self.breakeven_active or entry_price is None:
            return False

        breakeven_stop_price = float(entry_price) * 1.002
        return close < breakeven_stop_price

    def reset(self) -> None:
        """重置状态变量"""
        self.breakeven_active = False
        self.rsi_watcher = False


class SqueezeDetector:
    """
    Squeeze 状态检测器

    检测布林带是否收窄进 Keltner 通道（Squeeze 状态）。
    """

    def __init__(self, memory_days: int = 5):
        """
        初始化 Squeeze 检测器

        Args:
            memory_days: Squeeze 历史记忆天数
        """
        self.memory_days = memory_days
        self.squeeze_history = deque(maxlen=memory_days)

    def check_squeeze(
        self,
        bb_upper: float | None,
        bb_lower: float | None,
        keltner_upper: float | None,
        keltner_lower: float | None,
    ) -> bool:
        """
        检查是否处于 Squeeze 状态

        Args:
            bb_upper: 布林带上轨
            bb_lower: 布林带下轨
            keltner_upper: Keltner Base 上轨
            keltner_lower: Keltner Base 下轨

        Returns:
            True 表示处于 Squeeze 状态
        """
        if bb_upper is None or bb_lower is None:
            return False
        if keltner_upper is None or keltner_lower is None:
            return False

        is_squeezing = bb_upper < keltner_upper and bb_lower > keltner_lower
        self.squeeze_history.append(is_squeezing)
        return is_squeezing

    def has_recent_squeeze(self) -> bool:
        """
        判断近期是否有 Squeeze

        Returns:
            True 表示近期有 Squeeze
        """
        return any(self.squeeze_history)

    def is_high_conviction(self, current_squeeze: bool) -> bool:
        """
        判断是否为高确信度设置

        Args:
            current_squeeze: 当前是否处于 Squeeze

        Returns:
            True 表示高确信度（当前 Squeeze 或近期有 Squeeze）
        """
        return current_squeeze or self.has_recent_squeeze()
