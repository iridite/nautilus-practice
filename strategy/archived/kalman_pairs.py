"""
Kalman Filter Pairs Trading Strategy

核心理念:
- 使用在线卡尔曼滤波器动态估计对冲比率(hedge ratio)
- 基于残差的Z-Score进行均值回归交易
- 适用于高度相关的资产对(如SOLUSDT vs ETHUSDT)
"""

from decimal import Decimal
from typing import Optional

import numpy as np
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId

from strategy.core.base import BaseStrategy, BaseStrategyConfig


class OnlineKalmanFilter:
    """
    在线卡尔曼滤波器用于动态估计对冲比率

    状态空间模型:
    - 状态变量: θ_t = [α_t, β_t]^T (截距和斜率)
    - 观测方程: Y_t = α_t + β_t * X_t + ε_t
    - 状态转移: θ_t = θ_t-1 + ω_t (随机游走)
    """

    def __init__(self, delta: float = 1e-4, R: float = 1.0):
        """
        初始化卡尔曼滤波器

        参数:
            delta: 状态转移协方差系数(控制参数变化速度)
            R: 观测噪声方差
        """
        self.delta = delta
        self.R = R
        self.theta = np.zeros(2)
        self.P = np.eye(2) * 1.0
        self.initialized = False

    def update(self, y: float, x: float) -> tuple[float, float, float]:
        """
        更新滤波器状态

        参数:
            y: 因变量(Asset A价格)
            x: 自变量(Asset B价格)

        返回:
            (alpha, beta, z_score): 截距、斜率和Z-Score
        """
        H = np.array([1.0, x])
        P_pred = self.P + self.delta * np.eye(2)
        y_pred = np.dot(H, self.theta)
        e = y - y_pred
        Q = np.dot(H, np.dot(P_pred, H)) + self.R
        K = np.dot(P_pred, H) / Q
        self.theta = self.theta + K * e
        self.P = P_pred - np.outer(K, H) @ P_pred
        z_score = e / np.sqrt(Q) if Q > 0 else 0.0
        self.initialized = True
        return float(self.theta[0]), float(self.theta[1]), float(z_score)

    def get_beta(self) -> float:
        """获取当前对冲比率"""
        return float(self.theta[1])

    def get_alpha(self) -> float:
        """获取当前截距"""
        return float(self.theta[0])

    def reset(self):
        """重置滤波器"""
        self.theta = np.zeros(2)
        self.P = np.eye(2) * 1.0
        self.initialized = False


class KalmanPairsTradingConfig(BaseStrategyConfig):
    """卡尔曼配对交易策略配置"""

    # 简化配置字段（推荐使用）
    symbol_a: str = ""
    symbol_b: str = ""
    timeframe: str = ""
    price_type: str = "LAST"
    origination: str = "EXTERNAL"

    # 完整配置字段（向后兼容，自动从简化字段生成）
    instrument_a_id: str = ""
    instrument_b_id: str = ""
    bar_type: str = ""
    delta: float = 1e-4
    R: float = 1.0
    warmup_period: int = 50
    entry_threshold: float = 2.0
    exit_threshold: float = 0.5
    stop_loss_threshold: float = 4.0
    max_notional_per_trade: float = 10000.0
    max_positions: int = 1


class KalmanPairsTradingStrategy(BaseStrategy):
    """
    卡尔曼滤波器配对交易策略

    交易逻辑:
    - 入场做多: Z < -entry_threshold -> 买入A + 卖出B
    - 入场做空: Z > entry_threshold -> 卖出A + 买入B
    - 出场: |Z| < exit_threshold
    - 止损: |Z| > stop_loss_threshold
    """

    def __init__(self, config: KalmanPairsTradingConfig):
        super().__init__(config)

        self.instrument_a_id = InstrumentId.from_str(config.instrument_a_id)
        self.instrument_b_id = InstrumentId.from_str(config.instrument_b_id)
        self.bar_type = BarType.from_str(config.bar_type)
        self.kalman = OnlineKalmanFilter(delta=config.delta, R=config.R)

        # 数据缓存
        self.price_a: Optional[Decimal] = None
        self.price_b: Optional[Decimal] = None
        self.last_bar_a_ts: int = 0
        self.last_bar_b_ts: int = 0
        self._bar_a_updated: bool = False
        self._bar_b_updated: bool = False

        # 状态变量
        self.current_alpha: float = 0.0
        self.current_beta: float = 0.0
        self.current_z_score: float = 0.0
        self.bar_count: int = 0

        # 持仓状态
        self.position_type: Optional[str] = None
        self._pending_orders_a: set = set()
        self._pending_orders_b: set = set()

        self.DATA_SYNC_TOLERANCE_NS = 60 * 1_000_000_000

    def on_start(self):
        """订阅数据"""
        super().on_start()

        self.instrument_a = self.cache.instrument(self.instrument_a_id)
        self.instrument_b = self.cache.instrument(self.instrument_b_id)

        if not self.instrument_a or not self.instrument_b:
            self.log.error(f"无法找到交易工具: {self.instrument_a_id} 或 {self.instrument_b_id}")
            return

        # 使用配置的 bar_type 的 spec，为两个资产创建订阅
        bar_type_a = BarType(self.instrument_a_id, self.bar_type.spec)
        bar_type_b = BarType(self.instrument_b_id, self.bar_type.spec)

        self.subscribe_bars(bar_type_a)
        self.subscribe_bars(bar_type_b)

        self.log.info(
            f"策略启动: {self.instrument_a_id} vs {self.instrument_b_id}, "
            f"预热期={self.config.warmup_period}, "
            f"入场阈值=±{self.config.entry_threshold}, "
            f"出场阈值=±{self.config.exit_threshold}"
        )

    def _update_price_cache(self, bar: Bar) -> bool:
        """更新价格缓存，返回是否成功更新"""
        if bar.bar_type.instrument_id == self.instrument_a_id:
            self.price_a = Decimal(str(bar.close))
            self.last_bar_a_ts = bar.ts_event
            self._bar_a_updated = True
            return True
        elif bar.bar_type.instrument_id == self.instrument_b_id:
            self.price_b = Decimal(str(bar.close))
            self.last_bar_b_ts = bar.ts_event
            self._bar_b_updated = True
            return True
        return False

    def _should_process_bar(self) -> bool:
        """检查是否应该处理bar"""
        if not (self._bar_a_updated and self._bar_b_updated):
            return False

        if not self._check_data_sync():
            return False

        if self.price_a is None or self.price_b is None:
            return False

        return True

    def _reset_update_flags(self):
        """重置更新标记"""
        self._bar_a_updated = False
        self._bar_b_updated = False

    def _update_kalman_filter(self):
        """更新卡尔曼滤波器"""
        y = float(self.price_a)
        x = float(self.price_b)
        self.current_alpha, self.current_beta, self.current_z_score = self.kalman.update(y, x)
        self.bar_count += 1

    def _log_periodic_info(self):
        """定期记录信息"""
        if self.bar_count % 10 == 0:
            self.log.info(
                f"[Bar {self.bar_count}] "
                f"A={self.price_a:.2f}, B={self.price_b:.2f}, "
                f"Beta={self.current_beta:.4f}, Z={self.current_z_score:.2f}"
            )

    def on_bar(self, bar: Bar):
        """处理Bar事件"""
        super().on_bar(bar)

        if not self._update_price_cache(bar):
            return

        if not self._should_process_bar():
            return

        self._reset_update_flags()
        self._update_kalman_filter()
        self._log_periodic_info()

        if self.bar_count < self.config.warmup_period:
            return

        if self._has_position():
            self._manage_position()
        else:
            self._check_entry_signal()

    def _check_data_sync(self) -> bool:
        """检查数据是否同步"""
        if self.last_bar_a_ts == 0 or self.last_bar_b_ts == 0:
            return False

        time_diff = abs(self.last_bar_a_ts - self.last_bar_b_ts)
        return time_diff <= self.DATA_SYNC_TOLERANCE_NS

    def _has_position(self) -> bool:
        """检查是否有配对持仓"""
        pos_a = self.cache.positions_open(instrument_id=self.instrument_a_id)
        pos_b = self.cache.positions_open(instrument_id=self.instrument_b_id)

        # 检查是否两边都有持仓
        has_both = len(pos_a) > 0 and len(pos_b) > 0

        # 如果只有一边有持仓，记录警告
        if len(pos_a) > 0 and len(pos_b) == 0:
            self.log.warning(f"持仓不配对: 只有{self.instrument_a_id}有持仓")
        elif len(pos_a) == 0 and len(pos_b) > 0:
            self.log.warning(f"持仓不配对: 只有{self.instrument_b_id}有持仓")

        return has_both

    def _check_entry_signal(self):
        """检查入场信号"""
        z = self.current_z_score

        if z < -self.config.entry_threshold:
            self._enter_long_pair()
        elif z > self.config.entry_threshold:
            self._enter_short_pair()

    def _enter_long_pair(self):
        """入场做多配对: 买入A + 卖出B"""
        if self._has_position():
            return

        total_positions = len(self.cache.positions_open())
        if total_positions >= self.config.max_positions:
            return

        # 余额检查
        max_notional = Decimal(str(self.config.max_notional_per_trade))
        if not self.check_sufficient_balance(max_notional, self.instrument_a):
            return

        # 计算交易数量
        beta = self.current_beta

        # 根据beta符号调整对冲方向
        if beta >= 0:
            # 正beta: 买A卖B
            qty_a_raw = max_notional / self.price_a
            qty_a = self.instrument_a.make_qty(qty_a_raw)

            notional_b = max_notional * Decimal(str(abs(beta)))
            qty_b_raw = notional_b / self.price_b
            qty_b = self.instrument_b.make_qty(qty_b_raw)

            side_a = OrderSide.BUY
            side_b = OrderSide.SELL
        else:
            # 负beta: 买A买B
            qty_a_raw = max_notional / self.price_a
            qty_a = self.instrument_a.make_qty(qty_a_raw)

            notional_b = max_notional * Decimal(str(abs(beta)))
            qty_b_raw = notional_b / self.price_b
            qty_b = self.instrument_b.make_qty(qty_b_raw)

            side_a = OrderSide.BUY
            side_b = OrderSide.BUY

        if qty_a <= 0 or qty_b <= 0:
            return

        # 提交订单
        order_a = self.order_factory.market(
            instrument_id=self.instrument_a_id,
            order_side=side_a,
            quantity=qty_a,
        )

        order_b = self.order_factory.market(
            instrument_id=self.instrument_b_id,
            order_side=side_b,
            quantity=qty_b,
        )

        self.submit_order(order_a)
        self.submit_order(order_b)

        self._pending_orders_a.add(order_a.client_order_id)
        self._pending_orders_b.add(order_b.client_order_id)

        self.position_type = "long"

        self.log.info(
            f"入场做多配对: Z={self.current_z_score:.2f}, Beta={self.current_beta:.4f}, "
            f"{side_a.name} {qty_a} {self.instrument_a_id.symbol}, "
            f"{side_b.name} {qty_b} {self.instrument_b_id.symbol}"
        )

    def _enter_short_pair(self):
        """入场做空配对: 卖出A + 买入B"""
        if self._has_position():
            return

        total_positions = len(self.cache.positions_open())
        if total_positions >= self.config.max_positions:
            return

        # 余额检查
        max_notional = Decimal(str(self.config.max_notional_per_trade))
        if not self.check_sufficient_balance(max_notional, self.instrument_a):
            return

        # 计算交易数量
        beta = self.current_beta

        # 根据beta符号调整对冲方向
        if beta >= 0:
            # 正beta: 卖A买B
            qty_a_raw = max_notional / self.price_a
            qty_a = self.instrument_a.make_qty(qty_a_raw)

            notional_b = max_notional * Decimal(str(abs(beta)))
            qty_b_raw = notional_b / self.price_b
            qty_b = self.instrument_b.make_qty(qty_b_raw)

            side_a = OrderSide.SELL
            side_b = OrderSide.BUY
        else:
            # 负beta: 卖A卖B
            qty_a_raw = max_notional / self.price_a
            qty_a = self.instrument_a.make_qty(qty_a_raw)

            notional_b = max_notional * Decimal(str(abs(beta)))
            qty_b_raw = notional_b / self.price_b
            qty_b = self.instrument_b.make_qty(qty_b_raw)

            side_a = OrderSide.SELL
            side_b = OrderSide.SELL

        if qty_a <= 0 or qty_b <= 0:
            return

        # 提交订单
        order_a = self.order_factory.market(
            instrument_id=self.instrument_a_id,
            order_side=side_a,
            quantity=qty_a,
        )

        order_b = self.order_factory.market(
            instrument_id=self.instrument_b_id,
            order_side=side_b,
            quantity=qty_b,
        )

        self.submit_order(order_a)
        self.submit_order(order_b)

        self._pending_orders_a.add(order_a.client_order_id)
        self._pending_orders_b.add(order_b.client_order_id)

        self.position_type = "short"

        self.log.info(
            f"入场做空配对: Z={self.current_z_score:.2f}, Beta={self.current_beta:.4f}, "
            f"{side_a.name} {qty_a} {self.instrument_a_id.symbol}, "
            f"{side_b.name} {qty_b} {self.instrument_b_id.symbol}"
        )

    def on_order_filled(self, event):
        """订单成交回调"""
        super().on_order_filled(event)

        # 从待处理订单集合中移除
        order_id = event.client_order_id
        self._pending_orders_a.discard(order_id)
        self._pending_orders_b.discard(order_id)

    def on_order_rejected(self, event):
        """订单拒绝回调"""
        super().on_order_rejected(event)

        order_id = event.client_order_id
        self._pending_orders_a.discard(order_id)
        self._pending_orders_b.discard(order_id)

        self.log.error(f"订单被拒绝: {order_id}, 原因: {event.reason}")

        # 如果配对订单中有一个被拒绝，平掉另一边
        if not self._has_position():
            self._close_all_positions()

    def _manage_position(self):
        """管理持仓"""
        z = self.current_z_score
        abs_z = abs(z)

        if abs_z > self.config.stop_loss_threshold:
            self.log.warning(f"触发止损: Z={z:.2f} > {self.config.stop_loss_threshold}, 相关性破裂")
            self._close_all_positions()
            return

        if abs_z < self.config.exit_threshold:
            self.log.info(f"触发出场: Z={z:.2f} < {self.config.exit_threshold}, 均值回归完成")
            self._close_all_positions()
            return

    def _close_all_positions(self):
        """平仓所有持仓"""
        positions_a = self.cache.positions_open(instrument_id=self.instrument_a_id)
        for pos in positions_a:
            side = OrderSide.SELL if pos.is_long else OrderSide.BUY
            order = self.order_factory.market(
                instrument_id=self.instrument_a_id,
                order_side=side,
                quantity=pos.quantity,
            )
            self.submit_order(order)

        positions_b = self.cache.positions_open(instrument_id=self.instrument_b_id)
        for pos in positions_b:
            side = OrderSide.SELL if pos.is_long else OrderSide.BUY
            order = self.order_factory.market(
                instrument_id=self.instrument_b_id,
                order_side=side,
                quantity=pos.quantity,
            )
            self.submit_order(order)

        self.position_type = None
        self.log.info("已平仓所有持仓")

    def on_stop(self):
        """策略停止"""
        self.log.info(
            f"策略停止: 总Bar数={self.bar_count}, "
            f"最终Beta={self.current_beta:.4f}, Z={self.current_z_score:.2f}"
        )
        self._close_all_positions()

    def on_reset(self):
        """重置策略"""
        super().on_reset()
        self.kalman.reset()
        self.price_a = None
        self.price_b = None
        self.last_bar_a_ts = 0
        self.last_bar_b_ts = 0
        self._bar_a_updated = False
        self._bar_b_updated = False
        self.current_alpha = 0.0
        self.current_beta = 0.0
        self.current_z_score = 0.0
        self.bar_count = 0
        self.position_type = None
        self._pending_orders_a.clear()
        self._pending_orders_b.clear()
