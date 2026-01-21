"""
OI Divergence (持仓量背离) 策略

策略逻辑：
捕捉"杠杆驱动的假突破"，即价格突破关键位置但持仓量（Open Interest）
反向下降带来的均值回归机会。

核心 Alpha：
1. 确定区间：计算过去 N 个 Bar 的最高价（Resistance）和最低价（Support）
2. 触发条件（以做空为例）：
   - 价格突破 Resistance
   - OI 背离：持仓量相比突破前下降
   - 情绪过滤：资金费率处于高位（多头拥挤）
3. 入场：价格重新跌回 Resistance 以下时做空
4. 出场：
   - 止盈：回归到 VWAP 或中轨
   - 止损：突破近期高点的一定百分比
   - 时间止损：持仓超过 M 个 Bar 后强制平仓

Author: NautilusTrader Quant Team
Date: 2025-01-XX
"""

from collections import deque
from decimal import Decimal
from typing import Optional

from nautilus_trader.indicators import SimpleMovingAverage
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId

from strategy.base import BaseStrategy, BaseStrategyConfig
from utils.custom_data import FundingRateData, OpenInterestData


class OIDivergenceConfig(BaseStrategyConfig):
    """
    OI Divergence 策略配置参数

    继承自 BaseStrategyConfig，自动获得 trade_size, qty_percent, leverage 等通用参数
    """

    # === 数据设定 ===
    bar_type: str = ""  # 主执行周期（如 "1H"）
    trend_bar_type: str = ""  # 趋势判断周期（如 "4H"）

    # === 区间计算参数 ===
    lookback_bars: int = 48  # 计算 Resistance/Support 的回溯周期（默认 48 小时）

    # === OI 背离检测参数 ===
    oi_lookback: int = 12  # OI 移动平均周期（用于比较突破前后 OI 变化）
    oi_decline_threshold: float = 0.05  # OI 下降阈值（5% 表示 OI 需下降超过 5%）

    # === 资金费率过滤参数 ===
    funding_rate_threshold_annual: float = 30.0  # 年化资金费率阈值（30% 表示极度拥挤）
    use_funding_filter: bool = True  # 是否启用资金费率过滤

    # === 入场逻辑参数 ===
    breakout_reentry_pct: float = (
        0.002  # 回撤进入阈值（0.2% 表示价格需回撤到 Resistance 下方 0.2%）
    )

    # === 出场逻辑参数 ===
    tp_use_vwap: bool = True  # 止盈目标：是否使用 VWAP（否则使用中轨）
    vwap_period: int = 48  # VWAP 计算周期
    stop_loss_pct: Optional[float] = 0.01  # 硬止损百分比（1%）
    time_stop_bars: int = 24  # 时间止损：持仓超过 N 个 Bar 强制平仓

    # === 状态控制 ===
    max_positions: int = 1  # 最大持仓数量（防止过度交易）


class OIDivergence(BaseStrategy):
    """
    OI Divergence 策略实现

    继承 BaseStrategy 以复用下单量计算与安全下单逻辑。

    状态机：
    1. IDLE：等待突破信号
    2. BREAKOUT_DETECTED：检测到价格突破 + OI 背离
    3. WAITING_REENTRY：等待价格回撤到关键位
    4. POSITION_OPEN：持有仓位，监控出场条件
    """

    def __init__(self, config: OIDivergenceConfig):
        super().__init__(config)

        # 解析配置
        if isinstance(config.instrument_id, InstrumentId):
            self.instrument_id = config.instrument_id
        else:
            self.instrument_id = InstrumentId.from_str(config.instrument_id)

        if isinstance(config.bar_type, BarType):
            self.bar_type = config.bar_type
        else:
            self.bar_type = BarType.from_str(config.bar_type)

        if config.trend_bar_type:
            self.trend_bar_type = (
                config.trend_bar_type
                if isinstance(config.trend_bar_type, BarType)
                else BarType.from_str(config.trend_bar_type)
            )
        else:
            self.trend_bar_type = None

        # === 指标初始化 ===
        self.vwap_sma = SimpleMovingAverage(config.vwap_period)  # 用 SMA 近似 VWAP

        # === 数据缓存 ===
        self.bars_main: deque = deque(maxlen=config.lookback_bars + 1)
        self.oi_history: deque = deque(maxlen=config.oi_lookback + 10)
        self.funding_history: deque = deque(maxlen=10)

        # === 关键价位 ===
        self.resistance: Optional[Decimal] = None
        self.support: Optional[Decimal] = None
        self.midpoint: Optional[Decimal] = None

        # === OI 状态 ===
        self.oi_baseline: Optional[Decimal] = None  # 突破前 OI 基准值
        self.current_oi: Optional[Decimal] = None
        self.current_funding_rate_annual: Optional[Decimal] = None

        # === 策略状态 ===
        self.breakout_type: Optional[str] = None  # "LONG" or "SHORT"
        self.breakout_price: Optional[Decimal] = None
        self.entry_bar_count: int = 0  # 持仓 Bar 计数（用于时间止损）

        # === 日志控制 ===
        self._last_warmup_log_bars = 0

    def on_start(self):
        """策略启动时调用"""
        super().on_start()

        # 确保 instrument 加载成功
        if self.instrument is None:
            self.instrument = self.cache.instrument(self.instrument_id)
            if self.instrument is None:
                self.log.error(f"Could not find instrument: {self.instrument_id}")
                self.stop()
                return

        # 订阅行情数据
        self.subscribe_bars(self.bar_type)
        if self.trend_bar_type:
            self.subscribe_bars(self.trend_bar_type)

        # 订阅自定义数据（OI 和 Funding Rate）
        # 注意：需要在数据引擎中注册这些数据类型
        self.subscribe_data(OpenInterestData, client_id=None)
        self.subscribe_data(FundingRateData, client_id=None)

        self.log.info(f"OI Divergence Strategy started for {self.instrument_id}")
        self.log.info(
            f"Params: Lookback={self.config.lookback_bars}, "
            f"OI_Decline={self.config.oi_decline_threshold:.1%}, "
            f"Funding_Threshold={self.config.funding_rate_threshold_annual:.1f}%"
        )
        self.log.info(
            f"Exit: VWAP={self.config.tp_use_vwap}, "
            f"SL={self.config.stop_loss_pct:.1%}, "
            f"Time_Stop={self.config.time_stop_bars} bars"
        )

    def on_data(self, data):
        """处理自定义数据（OI 和 Funding Rate）"""
        if isinstance(data, OpenInterestData):
            self._handle_oi_data(data)
        elif isinstance(data, FundingRateData):
            self._handle_funding_data(data)

    def _handle_oi_data(self, data: OpenInterestData):
        """处理 Open Interest 数据"""
        if data.instrument_id != self.instrument_id:
            return

        self.current_oi = data.open_interest
        self.oi_history.append(
            {"ts": data.ts_event, "oi": data.open_interest, "data": data}
        )

    def _handle_funding_data(self, data: FundingRateData):
        """处理 Funding Rate 数据"""
        if data.instrument_id != self.instrument_id:
            return

        self.current_funding_rate_annual = data.funding_rate_annual
        self.funding_history.append(
            {
                "ts": data.ts_event,
                "rate": data.funding_rate,
                "annual": data.funding_rate_annual,
                "data": data,
            }
        )

    def on_bar(self, bar: Bar):
        """处理新的 Bar 数据"""
        super().on_bar(bar)

        # 只处理主周期数据
        if bar.bar_type != self.bar_type:
            return

        # 更新 Bar 缓存
        self.bars_main.append(bar)
        self.vwap_sma.handle_bar(bar)

        # 检查系统热身状态
        if not self._is_ready():
            total_bars = len(self.cache.bars(self.bar_type))
            if total_bars // 100 > self._last_warmup_log_bars:
                self._last_warmup_log_bars = total_bars // 100
                self.log.info(
                    f"Indicators warming up... (Bars: {total_bars}) | "
                    f"VWAP: {'OK' if self.vwap_sma.initialized else 'Wait'} | "
                    f"Range: {'OK' if self.resistance is not None else 'Wait'} | "
                    f"OI: {'OK' if len(self.oi_history) >= self.config.oi_lookback else 'Wait'}"
                )
            return

        # 更新关键价位
        self._update_key_levels()

        # 检查持仓状态
        positions = self.cache.positions_open(instrument_id=self.instrument_id)

        if positions:
            # 已持仓：监控出场条件
            self._check_exit_signals(bar, positions)
        else:
            # 无持仓：监控入场信号
            self._check_entry_signals(bar)

    def _is_ready(self) -> bool:
        """检查策略是否准备就绪"""
        return (
            len(self.bars_main) >= self.config.lookback_bars
            and self.vwap_sma.initialized
            and len(self.oi_history) >= self.config.oi_lookback
            and self.current_oi is not None
        )

    def _update_key_levels(self):
        """更新关键价位（Resistance, Support, Midpoint）"""
        if len(self.bars_main) < self.config.lookback_bars:
            return

        # 使用最近 lookback_bars 个 Bar 计算
        recent_bars = list(self.bars_main)[-self.config.lookback_bars :]

        highs = [Decimal(str(b.high)) for b in recent_bars]
        lows = [Decimal(str(b.low)) for b in recent_bars]

        self.resistance = max(highs)
        self.support = min(lows)
        self.midpoint = (self.resistance + self.support) / Decimal("2")

    def _check_entry_signals(self, bar: Bar):
        """检查入场信号"""
        if self.resistance is None or self.support is None:
            return

        current_price = Decimal(str(bar.close))
        current_high = Decimal(str(bar.high))
        current_low = Decimal(str(bar.low))

        # === 信号 A: 做空（价格突破 Resistance + OI 背离） ===
        if self._detect_short_signal(current_price, current_high):
            self._execute_short_entry(bar, current_price)

        # === 信号 B: 做多（价格突破 Support + OI 背离） ===
        elif self._detect_long_signal(current_price, current_low):
            self._execute_long_entry(bar, current_price)

    def _detect_short_signal(
        self, current_price: Decimal, current_high: Decimal
    ) -> bool:
        """
        检测做空信号

        条件：
        1. 价格突破 Resistance
        2. OI 背离（下降）
        3. 资金费率高位（多头拥挤）
        4. 价格回撤到 Resistance 下方
        """
        # 条件 1: 价格曾经突破 Resistance
        if self.resistance is None or current_high < self.resistance:
            return False

        # 条件 2: OI 背离检测
        if not self._is_oi_declining():
            return False

        # 条件 3: 资金费率过滤（多头拥挤）
        if self.config.use_funding_filter:
            if not self._is_funding_rate_high():
                return False

        # 条件 4: 价格回撤到 Resistance 下方（回撤进入）
        if self.resistance is None:
            return False
        reentry_threshold = self.resistance * (
            Decimal("1") - Decimal(str(self.config.breakout_reentry_pct))
        )
        if current_price >= reentry_threshold:
            return False

        return True

    def _detect_long_signal(self, current_price: Decimal, current_low: Decimal) -> bool:
        """
        检测做多信号

        条件：
        1. 价格突破 Support
        2. OI 背离（下降）
        3. 资金费率低位（空头拥挤）
        4. 价格反弹到 Support 上方
        """
        # 条件 1: 价格曾经突破 Support
        if self.support is None or current_low > self.support:
            return False

        # 条件 2: OI 背离检测
        if not self._is_oi_declining():
            return False

        # 条件 3: 资金费率过滤（空头拥挤）
        if self.config.use_funding_filter:
            if not self._is_funding_rate_low():
                return False

        # 条件 4: 价格反弹到 Support 上方（回撤进入）
        if self.support is None:
            return False
        reentry_threshold = self.support * (
            Decimal("1") + Decimal(str(self.config.breakout_reentry_pct))
        )
        if current_price <= reentry_threshold:
            return False

        return True

    def _is_oi_declining(self) -> bool:
        """
        判断 OI 是否下降

        逻辑：当前 OI 相比过去 N 个 Bar 的平均值下降超过阈值
        """
        if len(self.oi_history) < self.config.oi_lookback:
            return False

        # 计算过去 N 个 Bar 的 OI 平均值
        recent_oi = [
            item["oi"] for item in list(self.oi_history)[-self.config.oi_lookback :]
        ]
        oi_baseline = sum(recent_oi) / Decimal(str(len(recent_oi)))

        if oi_baseline == 0:
            return False

        # 计算下降比例
        if self.current_oi is None:
            return False
        oi_change_pct = (self.current_oi - oi_baseline) / oi_baseline

        # 判断是否下降超过阈值
        return oi_change_pct < -Decimal(str(self.config.oi_decline_threshold))

    def _is_funding_rate_high(self) -> bool:
        """判断资金费率是否处于高位（多头拥挤）"""
        if self.current_funding_rate_annual is None:
            return False

        return self.current_funding_rate_annual > Decimal(
            str(self.config.funding_rate_threshold_annual)
        )

    def _is_funding_rate_low(self) -> bool:
        """判断资金费率是否处于低位（空头拥挤）"""
        if self.current_funding_rate_annual is None:
            return False

        return self.current_funding_rate_annual < -Decimal(
            str(self.config.funding_rate_threshold_annual)
        )

    def _execute_short_entry(self, bar: Bar, current_price: Decimal):
        """执行做空入场"""
        # 检查最大持仓限制
        positions = self.cache.positions_open(instrument_id=self.instrument_id)
        if len(positions) >= self.config.max_positions:
            return

        # 计算下单量
        qty = self.calculate_order_qty(current_price)
        if qty <= 0:
            return

        # 提交做空市价单
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.SELL,
            quantity=qty,
        )

        baseline = self._get_oi_baseline()
        oi_change = (
            ((self.current_oi - baseline) / baseline * Decimal("100"))
            if baseline > 0 and self.current_oi is not None
            else Decimal("0")
        )

        self.submit_order_safe(
            order,
            reason=f"OI Divergence SHORT | "
            f"Price {current_price:.2f} < Resistance {self.resistance:.2f} | "
            f"OI Change: {oi_change:.1f}% | "
            f"Funding Annual: {self.current_funding_rate_annual:.1f}%",
        )

        # 设置硬止损单
        sl_price = current_price * (
            Decimal("1") + Decimal(str(self.config.stop_loss_pct))
        )
        trigger_price = self.instrument.make_price(sl_price)

        sl_order = self.order_factory.stop_market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=qty,
            trigger_price=trigger_price,
            time_in_force=TimeInForce.GTC,
            reduce_only=False,
        )
        self.submit_order_safe(
            sl_order, reason=f"OI Divergence SL (BUY) @ {trigger_price}"
        )

        # 重置持仓计数器
        self.entry_bar_count = 0

    def _execute_long_entry(self, bar: Bar, current_price: Decimal):
        """执行做多入场"""
        # 检查最大持仓限制
        positions = self.cache.positions_open(instrument_id=self.instrument_id)
        if len(positions) >= self.config.max_positions:
            return

        # 计算下单量
        qty = self.calculate_order_qty(current_price)
        if qty <= 0:
            return

        # 提交做多市价单
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=qty,
        )

        baseline = self._get_oi_baseline()
        oi_change = (
            ((self.current_oi - baseline) / baseline * Decimal("100"))
            if baseline > 0 and self.current_oi is not None
            else Decimal("0")
        )

        self.submit_order_safe(
            order,
            reason=f"OI Divergence LONG | "
            f"Price {current_price:.2f} > Support {self.support:.2f} | "
            f"OI Change: {oi_change:.1f}% | "
            f"Funding Annual: {self.current_funding_rate_annual:.1f}%",
        )

        # 设置硬止损单
        sl_price = current_price * (
            Decimal("1") - Decimal(str(self.config.stop_loss_pct))
        )
        trigger_price = self.instrument.make_price(sl_price)

        sl_order = self.order_factory.stop_market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.SELL,
            quantity=qty,
            trigger_price=trigger_price,
            time_in_force=TimeInForce.GTC,
            reduce_only=False,
        )
        self.submit_order_safe(
            sl_order, reason=f"OI Divergence SL (SELL) @ {trigger_price}"
        )

        # 重置持仓计数器
        self.entry_bar_count = 0

    def _check_exit_signals(self, bar: Bar, positions):
        """检查出场信号"""
        self.entry_bar_count += 1

        current_price = Decimal(str(bar.close))

        for pos in positions:
            # === 出场条件 1: 止盈（回归 VWAP 或中轨） ===
            if self._check_take_profit(pos, current_price):
                self.log.info(
                    f"Take Profit triggered for {pos.side.name} position | "
                    f"Price: {current_price:.2f}, Target: {self._get_tp_target():.2f}"
                )
                self.close_position(pos)
                self.cancel_all_orders(self.instrument_id)
                self.entry_bar_count = 0
                return

            # === 出场条件 2: 时间止损 ===
            if self.entry_bar_count >= self.config.time_stop_bars:
                self.log.info(
                    f"Time Stop triggered for {pos.side.name} position | "
                    f"Held for {self.entry_bar_count} bars"
                )
                self.close_position(pos)
                self.cancel_all_orders(self.instrument_id)
                self.entry_bar_count = 0
                return

    def _check_take_profit(self, pos, current_price: Decimal) -> bool:
        """检查是否触发止盈"""
        tp_target = self._get_tp_target()
        if tp_target is None:
            return False

        # 做多：价格上涨到目标位
        if pos.is_long and current_price >= tp_target:
            return True

        # 做空：价格下跌到目标位
        if pos.is_short and current_price <= tp_target:
            return True

        return False

    def _get_tp_target(self) -> Optional[Decimal]:
        """获取止盈目标价位"""
        if self.config.tp_use_vwap:
            # 使用 VWAP（用 SMA 近似）
            if self.vwap_sma.initialized:
                return Decimal(str(self.vwap_sma.value))
        else:
            # 使用中轨
            if self.midpoint is not None:
                return self.midpoint

        return None

    def _get_oi_baseline(self) -> Decimal:
        """获取 OI 基准值（用于计算 OI 变化百分比）"""
        if len(self.oi_history) < self.config.oi_lookback:
            return Decimal("0")

        recent_oi = [
            item["oi"] for item in list(self.oi_history)[-self.config.oi_lookback :]
        ]
        return sum(recent_oi) / Decimal(str(len(recent_oi)))

    def on_stop(self):
        """策略停止时清理所有订单与仓位"""
        self.cancel_all_orders(self.instrument_id)
        self.close_all_positions(self.instrument_id)
        self.log.info("OI Divergence Strategy stopped.")

    def on_reset(self):
        """策略重置时清除内部状态"""
        super().on_reset()
        self.bars_main.clear()
        self.oi_history.clear()
        self.funding_history.clear()

        self.resistance = None
        self.support = None
        self.midpoint = None
        self.oi_baseline = None
        self.current_oi = None
        self.current_funding_rate_annual = None

        self.breakout_type = None
        self.breakout_price = None
        self.entry_bar_count = 0

        self.vwap_sma.reset()
        self._last_warmup_log_bars = 0
