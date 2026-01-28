"""
信号钝化保护工具模块

提供通用的信号钝化检测和保护功能，可被多个策略复用。
适用于趋势跟踪、背离交易等需要防止信号长时间持续不反转的场景。
"""

from decimal import Decimal
from typing import Optional

from nautilus_trader.model.enums import OrderSide, TimeInForce


class SignalStaleGuard:
    """
    信号钝化保护器

    功能：
    - 追踪信号持续时间
    - 检测信号钝化（长时间持续不反转）
    - 提供保护措施（平仓或收紧止损）
    - 自动重置追踪状态
    """

    def __init__(
        self,
        stale_bars: int = 12,
        stale_action: str = "tighten_stop",
        stale_stop_multiplier: float = 1.0,
    ):
        """
        初始化信号钝化保护器

        Parameters
        ----------
        stale_bars : int
            信号钝化阈值（K 线数量）
        stale_action : str
            钝化处理方式：'close'（平仓）或 'tighten_stop'（收紧止损）
        stale_stop_multiplier : float
            收紧止损倍数（用于 ATR 止损）
        """
        self.stale_bars = stale_bars
        self.stale_action = stale_action
        self.stale_stop_multiplier = stale_stop_multiplier

        self._first_detected_bar: Optional[int] = None
        self._bars_count: int = 0
        self._protection_triggered: bool = False

    def update(
        self, current_bar_count: int, signal_active: bool
    ) -> tuple[bool, int]:
        """
        更新钝化状态

        Parameters
        ----------
        current_bar_count : int
            当前 K 线计数
        signal_active : bool
            信号是否仍然活跃

        Returns
        -------
        tuple[bool, int]
            (是否触发保护, 持续时间)
        """
        if signal_active:
            if self._first_detected_bar is None:
                self._first_detected_bar = current_bar_count

            self._bars_count = current_bar_count - self._first_detected_bar

            if self._bars_count >= self.stale_bars and not self._protection_triggered:
                self._protection_triggered = True
                return True, self._bars_count
        else:
            self.reset()

        return False, self._bars_count

    def handle_stale_protection(
        self,
        strategy,
        pos,
        entry_price: Decimal,
        atr_value: Optional[Decimal] = None,
        logger=None,
    ) -> bool:
        """
        处理钝化保护措施

        Parameters
        ----------
        strategy : Strategy
            策略对象
        pos : Position
            持仓对象
        entry_price : Decimal
            入场价格
        atr_value : Optional[Decimal]
            ATR 值（用于收紧止损）
        logger : Logger, optional
            日志记录器

        Returns
        -------
        bool
            是否执行了平仓操作
        """
        if self.stale_action == "close":
            if logger:
                logger.warning(
                    f"🚨 SIGNAL STALE - CLOSING POSITION | "
                    f"Duration: {self._bars_count} bars, "
                    f"Threshold: {self.stale_bars} bars"
                )
            strategy.close_position(pos)
            strategy.cancel_all_orders(pos.instrument_id)
            return True

        elif self.stale_action == "tighten_stop" and atr_value is not None:
            tightened_distance = atr_value * Decimal(str(self.stale_stop_multiplier))

            if pos.is_long:
                new_stop = entry_price - tightened_distance
            else:
                new_stop = entry_price + tightened_distance

            if logger:
                logger.warning(
                    f"🚨 SIGNAL STALE - TIGHTENING STOP | "
                    f"Duration: {self._bars_count} bars, "
                    f"New Stop: {new_stop:.2f} ({self.stale_stop_multiplier}× ATR)"
                )

            # 取消现有止损单，提交新的收紧止损单
            strategy.cancel_all_orders(pos.instrument_id)

            opposite_side = OrderSide.BUY if pos.is_short else OrderSide.SELL
            trigger_price = strategy.instrument.make_price(new_stop)

            sl_order = strategy.order_factory.stop_market(
                instrument_id=pos.instrument_id,
                order_side=opposite_side,
                quantity=pos.quantity,
                trigger_price=trigger_price,
                time_in_force=TimeInForce.GTC,
                reduce_only=True,
            )

            strategy.submit_order_safe(
                sl_order,
                reason=f"Tightened Stop Loss (Signal Stale) @ {new_stop:.2f}",
            )

        return False

    def get_bars_count(self) -> int:
        """获取信号持续的 K 线数量"""
        return self._bars_count

    def is_protection_triggered(self) -> bool:
        """检查保护是否已触发"""
        return self._protection_triggered

    def reset(self):
        """重置追踪状态"""
        self._first_detected_bar = None
        self._bars_count = 0
        self._protection_triggered = False
