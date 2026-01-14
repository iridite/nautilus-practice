from decimal import Decimal
from typing import Optional

from nautilus_trader.indicators import AverageTrueRange, ExponentialMovingAverage
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, OrderType, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId

# from nautilus_trader.model.objects import Price
from nautilus_trader.model.orders import Order

from strategy.base import BaseStrategy, BaseStrategyConfig


class DualThrustConfig(BaseStrategyConfig):
    """
    Dual Thrust 策略配置参数
    继承自 BaseStrategyConfig，自动获得 trade_size, qty_percent, leverage 等通用参数
    """

    # instrument_id is inherited from BaseStrategyConfig

    bar_type: BarType | str = ""

    # 策略核心参数
    lookback_period: int = 4  # N: 回溯周期数
    k1: float = 0.5  # 上轨系数
    k2: float = 0.5  # 下轨系数

    # 过滤器参数
    ema_period: int = 200  # 趋势过滤器周期
    atr_period: int = 20  # 波动率计算周期
    atr_threshold: float = 1.2  # 波动率阈值倍数 (Range > ATR * Threshold)

    # 风控参数 (New)
    stop_loss_pct: float = 0.015  # 1.5% 硬止损
    breakeven_trigger_pct: float = 0.02  # 2.0% 利润触发保本移动


class DualThrust(BaseStrategy):
    """
    Dual Thrust 策略实现 for NautilusTrader
    继承 BaseStrategy 以复用下单量计算与安全下单逻辑。

    逻辑:
    1. 计算前N个周期的 HH, HC, LC, LL
    2. Range = max(HH - LC, HC - LL)
    3. BuyLine = CurrentOpen + K1 * Range
    4. SellLine = CurrentOpen - K2 * Range

    新增过滤:
    1. 趋势过滤: 价格 > EMA做多, 价格 < EMA做空
    2. 波动过滤: Range > ATR * Threshold

    新增风控:
    1. 初始硬止损 (Hard Stop Loss)
    2. 保本止损 (Breakeven Stop)
    """

    def __init__(self, config: DualThrustConfig):
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

        # 初始化指标
        self.ema = ExponentialMovingAverage(config.ema_period)
        self.atr = AverageTrueRange(config.atr_period)

        # 状态变量
        # self.instrument 由 BaseStrategy.on_start() 统一初始化
        self.history_bars: list[Bar] = []  # 用于存储计算Range的历史K线

        self.current_range: Optional[Decimal] = None
        self.buy_line: Optional[Decimal] = None
        self.sell_line: Optional[Decimal] = None

    def on_start(self):
        """
        策略启动时调用
        """
        # 1. 调用父类 on_start 初始化 instrument
        super().on_start()

        # 确保 instrument 加载成功
        if self.instrument is None:
            # 尝试通过 instrument_id 再次获取 (防止父类只用了 config 里的 str)
            self.instrument = self.cache.instrument(self.instrument_id)
            if self.instrument is None:
                self.log.error(f"Could not find instrument: {self.instrument_id}")
                self.stop()
                return

        # 2. 订阅行情数据
        self.subscribe_bars(self.bar_type)

        self.log.info(f"Dual Thrust Strategy started for {self.instrument_id}")
        self.log.info(
            f"Params: N={self.config.lookback_period}, K1={self.config.k1}, K2={self.config.k2}"
        )
        self.log.info(
            f"Filters: EMA={self.config.ema_period}, ATR={self.config.atr_period}, Threshold={self.config.atr_threshold}"
        )
        self.log.info(
            f"Risk: SL={self.config.stop_loss_pct:.1%}, BreakevenTrigger={self.config.breakeven_trigger_pct:.1%}"
        )

    def on_bar(self, bar: Bar):
        """
        处理新的 Bar 数据
        """
        # 1. 更新指标
        self.ema.handle_bar(bar)
        self.atr.handle_bar(bar)

        # 2. 维护历史数据窗口 (Rolling Window)
        self.history_bars.append(bar)

        required_len = self.config.lookback_period + 1

        # 保持窗口大小
        if len(self.history_bars) > required_len:
            self.history_bars.pop(0)

        # 3. 检查数据预热进度
        if (
            not self.ema.initialized
            or not self.atr.initialized
            or len(self.history_bars) < required_len
        ):
            if len(self.history_bars) % 10 == 0:
                self.log.info(
                    f"Warming up... EMA:{self.ema.initialized} ATR:{self.atr.initialized}"
                )
            return

        # 4. 风控管理 (移动止损/保本)
        self._manage_risk(bar)

        # 5. 计算 Dual Thrust 轨道
        self._calculate_thresholds()

        # 6. 执行交易逻辑
        self._check_signals(bar)

    def _manage_risk(self, bar: Bar):
        """
        在每个 Bar 检查持仓浮盈，触发保本逻辑
        """
        positions = self.cache.positions_open(instrument_id=self.instrument_id)
        if not positions:
            return

        current_price = bar.close

        for pos in positions:
            entry_price = pos.avg_px_open

            # 计算未实现盈亏百分比
            pnl_pct = Decimal(0)
            if pos.is_long:
                pnl_pct = (current_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - current_price) / entry_price

            # 检查是否触发保本逻辑
            if pnl_pct > self.config.breakeven_trigger_pct:
                self._move_stop_to_breakeven(pos)

    def _move_stop_to_breakeven(self, position):
        """
        将止损移动到开仓价 (保本)
        """
        # 1. 查找当前针对该持仓的未结止损单
        # 注意: 这里的逻辑简化查找: 找同标的、反方向、StopMarket类型的订单
        open_orders = self.cache.orders_open(instrument_id=self.instrument_id)
        sl_order: Optional[Order] = None

        expected_sl_side = OrderSide.SELL if position.is_long else OrderSide.BUY

        for order in open_orders:
            if (
                order.order_type == OrderType.STOP_MARKET
                and order.side == expected_sl_side
            ):
                sl_order = order
                break

        entry_price = position.avg_px_open

        # 2. 如果存在止损单
        if sl_order:
            # 检查触发价是否已经是开仓价 (允许微小误差)
            current_trigger = sl_order.trigger_price
            if abs(current_trigger - entry_price) < (entry_price * 0.001):
                # 已经是保本位了，无需操作
                return

            # 取消旧订单
            self.log.info(
                f"💰 Profit > {self.config.breakeven_trigger_pct:.1%}, Moving SL to Breakeven: {entry_price}"
            )
            self.cancel_order(sl_order)
        else:
            self.log.info(
                f"💰 Profit > {self.config.breakeven_trigger_pct:.1%}, Placing New Breakeven SL: {entry_price}"
            )

        # 3. 提交新的保本止损单
        new_sl_order = self.order_factory.stop_market(
            instrument_id=self.instrument_id,
            order_side=expected_sl_side,
            quantity=position.quantity,
            trigger_price=self.instrument.make_price(entry_price),
            reduce_only=True,
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(new_sl_order)

    def _calculate_thresholds(self):
        """
        计算上下轨核心逻辑
        """
        reference_bars = self.history_bars[-self.config.lookback_period - 1 : -1]

        if len(reference_bars) < self.config.lookback_period:
            return

        highs = [b.high for b in reference_bars]
        lows = [b.low for b in reference_bars]
        closes = [b.close for b in reference_bars]

        hh = max(highs)
        hc = max(closes)
        lc = min(closes)
        ll = min(lows)

        rng = max(hh - lc, hc - ll)
        self.current_range = rng

        current_open = self.history_bars[-1].open

        k1 = Decimal(str(self.config.k1))
        k2 = Decimal(str(self.config.k2))

        self.buy_line = current_open + (rng * k1)
        self.sell_line = current_open - (rng * k2)

    def _check_signals(self, bar: Bar):
        """
        信号检查与订单执行
        """
        if (
            self.buy_line is None
            or self.sell_line is None
            or self.current_range is None
        ):
            return

        current_price = bar.close

        # --- 0. 管理未成交挂单 ---
        # 每次 Bar 更新，Buy/Sell Line 会变动，先取消所有旧的 Limit 入场单
        for order in self.cache.orders_open(instrument_id=self.instrument_id):
            if order.order_type == OrderType.LIMIT:
                self.cancel_order(order)

        # --- 过滤器检查 ---
        atr_val = Decimal(str(self.atr.value))
        vol_threshold = atr_val * Decimal(str(self.config.atr_threshold))

        if self.current_range <= vol_threshold:
            return

        ema_val = Decimal(str(self.ema.value))
        is_uptrend = current_price > ema_val
        is_downtrend = current_price < ema_val

        # --- 仓位管理 ---
        positions = self.cache.positions_open(instrument_id=self.instrument_id)

        qty = self.calculate_order_qty(current_price)
        if qty <= 0:
            return

        # --- 逻辑 1: 做多突破 ---
        if current_price > self.buy_line and is_uptrend:
            has_short = any(p.is_short for p in positions)
            if has_short:
                self.log.info("Closing existing short positions before going long")
                # 平仓前必须取消关联的止损单，防止意外触发
                self.cancel_all_orders(self.instrument_id)
                self.close_all_positions(self.instrument_id)
                positions = [p for p in positions if not p.is_short]

            has_long = any(p.is_long for p in positions)
            if not has_long:
                # 改为 Limit 单挂在 Buy Line (Maker)，减少 Taker 手续费
                precision = (
                    self.instrument.price_precision
                    if self.instrument and self.instrument.price_precision is not None
                    else 8
                )
                buy_price_rnd = round(self.buy_line, precision)
                limit_price = self.instrument.make_price(buy_price_rnd)
                order = self.order_factory.limit(
                    instrument_id=self.instrument_id,
                    order_side=OrderSide.BUY,
                    quantity=qty,
                    price=limit_price,
                )
                self.submit_order_safe(
                    order,
                    reason=f"Breakout BUY Limit (Price {current_price} > BuyLine {self.buy_line}) & Trend (Price > EMA {ema_val:.2f}) & Vol ({self.current_range:.2f} > {vol_threshold:.2f})",
                )

        # --- 逻辑 2: 做空突破 ---
        elif current_price < self.sell_line and is_downtrend:
            has_long = any(p.is_long for p in positions)
            if has_long:
                self.log.info("Closing existing long positions before going short")
                # 平仓前必须取消关联的止损单
                self.cancel_all_orders(self.instrument_id)
                self.close_all_positions(self.instrument_id)
                positions = [p for p in positions if not p.is_long]

            has_short = any(p.is_short for p in positions)
            if not has_short:
                # 改为 Limit 单挂在 Sell Line (Maker)
                precision = (
                    self.instrument.price_precision
                    if self.instrument and self.instrument.price_precision is not None
                    else 8
                )
                sell_price_rnd = round(self.sell_line, precision)
                limit_price = self.instrument.make_price(sell_price_rnd)
                order = self.order_factory.limit(
                    instrument_id=self.instrument_id,
                    order_side=OrderSide.SELL,
                    quantity=qty,
                    price=limit_price,
                )
                self.submit_order_safe(
                    order,
                    reason=f"Breakout SELL Limit (Price {current_price} < SellLine {self.sell_line}) & Trend (Price < EMA {ema_val:.2f}) & Vol ({self.current_range:.2f} > {vol_threshold:.2f})",
                )

    def on_stop(self):
        self.cancel_all_orders(self.instrument_id)
        self.close_all_positions(self.instrument_id)
        self.log.info("Dual Thrust Strategy stopped.")

    def on_reset(self):
        """
        策略重置时调用，清除内部状态
        """
        super().on_reset()
        self.history_bars.clear()
        self.current_range = None
        self.buy_line = None
        self.sell_line = None
        self.ema.reset()
        self.atr.reset()
