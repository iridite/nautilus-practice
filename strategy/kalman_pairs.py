"""
Kalman Filter Pairs Trading Strategy

核心理念:
- 使用在线卡尔曼滤波器动态估计对冲比率(hedge ratio)
- 基于残差的Z-Score进行均值回归交易
- 适用于高度相关的资产对(如SOLUSDT vs ETHUSDT)
"""

from collections import deque
from decimal import Decimal
from typing import Dict, Optional

import numpy as np
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId

from strategy.base import BaseStrategy, BaseStrategyConfig


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

        # 状态向量 [α, β]
        self.theta = np.zeros(2)

        # 状态协方差矩阵
        self.P = np.eye(2) * 1.0

        # 是否已初始化
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
        # 观测向量 [1, x]
        H = np.array([1.0, x])

        # 预测步骤
        # P_pred = P + delta * I
        P_pred = self.P + self.delta * np.eye(2)

        # 预测误差
        y_pred = np.dot(H, self.theta)
        e = y - y_pred

        # 预测误差方差
        Q = np.dot(H, np.dot(P_pred, H)) + self.R

        # 卡尔曼增益
        K = np.dot(P_pred, H) / Q

        # 更新状态
        self.theta = self.theta + K * e

        # 更新协方差
        self.P = P_pred - np.outer(K, H) @ P_pred

        # 计算Z-Score
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

    # 交易对配置
    instrument_a_id: str = ""  # 目标资产(Y)
    instrument_b_id: str = ""  # 对冲资产(X)
    bar_type: str = ""

    # 卡尔曼滤波器参数
    delta: float = 1e-4  # 状态转移协方差
    R: float = 1.0  # 观测噪声方差
    warmup_period: int = 50  # 预热期(bar数量)

    # 交易信号参数
    entry_threshold: float = 2.0  # 入场Z-Score阈值
    exit_threshold: float = 0.5  # 出场Z-Score阈值
    stop_loss_threshold: float = 4.0  # 止损Z-Score阈值(相关性破裂)

    # 风险管理
    max_notional_per_trade: float = 10000.0  # 每笔交易最大名义价值
    max_positions: int = 1  # 最大持仓数


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

        # 交易对标识
        self.instrument_a_id = InstrumentId.from_str(config.instrument_a_id)
        self.instrument_b_id = InstrumentId.from_str(config.instrument_b_id)
        self.bar_type = BarType.from_str(config.bar_type)

        # 卡尔曼滤波器
        self.kalman = OnlineKalmanFilter(delta=config.delta, R=config.R)

        # 数据缓存
        self.price_a: Optional[Decimal] = None
        self.price_b: Optional[Decimal] = None
        self.last_bar_a_ts: int = 0
        self.last_bar_b_ts: int = 0

        # 状态变量
        self.current_alpha: float = 0.0
        self.current_beta: float = 0.0
        self.current_z_score: float = 0.0
        self.bar_count: int = 0

        # 持仓状态
        self.position_type: Optional[str] = None  # "long" or "short"

        # 数据同步容差(1分钟)
        self.DATA_SYNC_TOLERANCE_NS = 60 * 1_000_000_000

    def on_start(self):
        """订阅数据"""
        super().on_start()

        # 获取交易工具
        self.instrument_a = self.cache.instrument(self.instrument_a_id)
        self.instrument_b = self.cache.instrument(self.instrument_b_id)

        if not self.instrument_a or not self.instrument_b:
            self.log.error(f"无法找到交易工具: {self.instrument_a_id} 或 {self.instrument_b_id}")
            return

        # 订阅Bar数据
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

    def on_bar(self, bar: Bar):
        """处理Bar事件"""
        super().on_bar(bar)

        # 更新价格缓存
        if bar.bar_type.instrument_id == self.instrument_a_id:
            self.price_a = Decimal(str(bar.close))
            self.last_bar_a_ts = bar.ts_event
        elif bar.bar_type.instrument_id == self.instrument_b_id:
            self.price_b = Decimal(str(bar.close))
            self.last_bar_b_ts = bar.ts_event
        else:
            return

        # 检查数据同步
        if not self._check_data_sync():
            return

        # 确保有价格数据
        if self.price_a is None or self.price_b is None:
            return

        # 更新卡尔曼滤波器
        y = float(self.price_a)
        x = float(self.price_b)

        self.current_alpha, self.current_beta, self.current_z_score = self.kalman.update(y, x)
        self.bar_count += 1

        # 记录状态
        if self.bar_count % 10 == 0:
            self.log.info(
                f"[Bar {self.bar_count}] "
                f"A={self.price_a:.2f}, B={self.price_b:.2f}, "
                f"Beta={self.current_beta:.4f}, Z={self.current_z_score:.2f}"
            )

        # 预热期内不交易
        if self.bar_count < self.config.warmup_period:
            return

        # 执行交易逻辑
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
        """检查是否有持仓"""
        pos_a = self.cache.positions_open(instrument_id=self.instrument_a_id)
        pos_b = self.cache.positions_open(instrument_id=self.instrument_b_id)
        return len(pos_a) > 0 or len(pos_b) > 0

    def _check_entry_signal(self):
        """检查入场信号"""
        z = self.current_z_score

        # 做多配对: Z < -entry_threshold (A被低估)
        if z < -self.config.entry_threshold:
            self._enter_long_pair()

        # 做空配对: Z > entry_threshold (A被高估)
        elif z > self.config.entry_threshold:
            self._enter_short_pair()

    def _enter_long_pair(self):
        """入场做多配对: 买入A + 卖出B"""
        if self._has_position():
            return

        # 检查持仓限制
        total_positions = len(self.cache.positions_open())
        if total_positions >= self.config.max_positions:
            return

        # 计算交易数量
        beta = abs(self.current_beta)
        max_notional = Decimal(str(self.config.max_notional_per_trade))

        # Asset A数量
        qty_a_raw = max_notional / self.price_a
        qty_a = self.instrument_a.make_qty(qty_a_raw)

        # Asset B数量(根据beta调整)
        notional_b = self.price_a * qty_a_raw * Decimal(str(beta))
        qty_b_raw = notional_b / self.price_b
        qty_b = self.instrument_b.make_qty(qty_b_raw)

        if qty_a <= 0 or qty_b <= 0:
            return

        # 提交订单
        order_a = self.order_factory.market(
            instrument_id=self.instrument_a_id,
            order_side=OrderSide.BUY,
            quantity=qty_a,
        )

        order_b = self.order_factory.market(
            instrument_id=self.instrument_b_id,
            order_side=OrderSide.SELL,
            quantity=qty_b,
        )

        self.submit_order(order_a)
        self.submit_order(order_b)

        self.position_type = "long"

        self.log.info(
            f"入场做多配对: Z={self.current_z_score:.2f}, Beta={self.current_beta:.4f}, "
            f"买入{qty_a} {self.instrument_a_id.symbol}, "
            f"卖出{qty_b} {self.instrument_b_id.symbol}"
        )

    def _enter_short_pair(self):
        """入场做空配对: 卖出A + 买入B"""
        if self._has_position():
            return

        # 检查持仓限制
        total_positions = len(self.cache.positions_open())
        if total_positions >= self.config.max_positions:
            return

        # 计算交易数量
        beta = abs(self.current_beta)
        max_notional = Decimal(str(self.config.max_notional_per_trade))

        # Asset A数量
        qty_a_raw = max_notional / self.price_a
        qty_a = self.instrument_a.make_qty(qty_a_raw)

        # Asset B数量(根据beta调整)
        notional_b = self.price_a * qty_a_raw * Decimal(str(beta))
        qty_b_raw = notional_b / self.price_b
        qty_b = self.instrument_b.make_qty(qty_b_raw)

        if qty_a <= 0 or qty_b <= 0:
            return

        # 提交订单
        order_a = self.order_factory.market(
            instrument_id=self.instrument_a_id,
            order_side=OrderSide.SELL,
            quantity=qty_a,
        )

        order_b = self.order_factory.market(
            instrument_id=self.instrument_b_id,
            order_side=OrderSide.BUY,
            quantity=qty_b,
        )

        self.submit_order(order_a)
        self.submit_order(order_b)

        self.position_type = "short"

        self.log.info(
            f"入场做空配对: Z={self.current_z_score:.2f}, Beta={self.current_beta:.4f}, "
            f"卖出{qty_a} {self.instrument_a_id.symbol}, "
            f"买入{qty_b} {self.instrument_b_id.symbol}"
        )

    def _manage_position(self):
        """管理持仓"""
        z = self.current_z_score
        abs_z = abs(z)

        # 止损: 相关性破裂
        if abs_z > self.config.stop_loss_threshold:
            self.log.warning(
                f"触发止损: Z={z:.2f} > {self.config.stop_loss_threshold}, 相关性破裂"
            )
            self._close_all_positions()
            return

        # 出场: 均值回归完成
        if abs_z < self.config.exit_threshold:
            self.log.info(
                f"触发出场: Z={z:.2f} < {self.config.exit_threshold}, 均值回归完成"
            )
            self._close_all_positions()
            return

    def _close_all_positions(self):
        """平仓所有持仓"""
        # 平仓Asset A
        positions_a = self.cache.positions_open(instrument_id=self.instrument_a_id)
        for pos in positions_a:
            side = OrderSide.SELL if pos.is_long else OrderSide.BUY
            order = self.order_factory.market(
                instrument_id=self.instrument_a_id,
                order_side=side,
                quantity=pos.quantity,
            )
            self.submit_order(order)

        # 平仓Asset B
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
        self.current_alpha = 0.0
        self.current_beta = 0.0
        self.current_z_score = 0.0
        self.bar_count = 0
        self.position_type = None
