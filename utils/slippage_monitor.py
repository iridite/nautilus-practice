"""
滑点监控工具模块

提供通用的滑点监控功能，可被多个策略复用。
"""

from decimal import Decimal
from typing import Optional

from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.events import OrderFilled


class SlippageMonitor:
    """
    滑点监控器

    功能：
    - 追踪预期成交价与实际成交价的偏差
    - 自动判断滑点方向（有利/不利）
    - 避免部分成交时重复计算
    - 提供滑点告警功能
    """

    def __init__(
        self,
        max_slippage_pct: float = 0.005,
        enable_alert: bool = True,
        enable_logging: bool = True,
    ):
        """
        初始化滑点监控器

        Parameters
        ----------
        max_slippage_pct : float
            最大允许滑点百分比（默认 0.5%）
        enable_alert : bool
            是否启用滑点告警
        enable_logging : bool
            是否启用日志记录
        """
        self.max_slippage_pct = max_slippage_pct
        self.enable_alert = enable_alert
        self.enable_logging = enable_logging

        self._expected_prices: dict[str, Decimal] = {}
        self._calculated_orders: set[str] = set()
        self._last_slippage: Optional[float] = None

    def set_expected_price(self, order_id: str, price: Decimal):
        """
        设置预期成交价

        Parameters
        ----------
        order_id : str
            订单 ID
        price : Decimal
            预期成交价格
        """
        self._expected_prices[str(order_id)] = price

    def check_slippage(
        self, event: OrderFilled, logger=None
    ) -> Optional[tuple[float, bool]]:
        """
        检查滑点并返回滑点信息

        Parameters
        ----------
        event : OrderFilled
            订单成交事件
        logger : Logger, optional
            日志记录器

        Returns
        -------
        Optional[tuple[float, bool]]
            (滑点百分比, 是否不利滑点)，如果无法计算则返回 None
        """
        order_id = str(event.client_order_id)

        # 避免重复计算
        if order_id in self._calculated_orders:
            return None

        # 获取预期价格
        expected_price = self._expected_prices.get(order_id)
        if expected_price is None:
            return None

        # 计算滑点
        actual_price = Decimal(str(event.last_px))
        slippage_decimal = (actual_price - expected_price) / expected_price
        slippage_pct = float(slippage_decimal)

        # 判断滑点方向
        if event.order_side == OrderSide.BUY:
            is_adverse = slippage_pct > 0  # 买贵了
        else:
            is_adverse = slippage_pct < 0  # 卖便宜了

        # 存储结果
        self._last_slippage = abs(slippage_pct)
        self._calculated_orders.add(order_id)

        # 日志记录
        if logger:
            if self.enable_alert and self._last_slippage > self.max_slippage_pct:
                logger.warning(
                    f"🚨 EXCESSIVE SLIPPAGE: {self._last_slippage:.3%} "
                    f"({'ADVERSE' if is_adverse else 'FAVORABLE'}) | "
                    f"Expected: {expected_price:.2f}, Actual: {actual_price:.2f}, "
                    f"Threshold: {self.max_slippage_pct:.3%}"
                )
            elif self.enable_logging:
                logger.info(
                    f"✅ Slippage: {self._last_slippage:.3%} "
                    f"(Expected: {expected_price:.2f}, Actual: {actual_price:.2f})"
                )

        return self._last_slippage, is_adverse

    def get_last_slippage(self) -> Optional[float]:
        """获取最后一次滑点百分比"""
        return self._last_slippage

    def reset(self):
        """重置监控器状态"""
        self._expected_prices.clear()
        self._calculated_orders.clear()
        self._last_slippage = None
