from collections import deque
from decimal import Decimal
from typing import Optional

from nautilus_trader.indicators import AverageTrueRange, ExponentialMovingAverage
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId

from strategy.base import BaseStrategy, BaseStrategyConfig


class DualThrustConfig(BaseStrategyConfig):
    """
    Dual Thrust 策略配置参数
    继承自 BaseStrategyConfig，自动获得 trade_size, qty_percent, leverage 等通用参数
    """

    bar_type: str = ""

    # 策略核心参数
    lookback_period: int = 4  # N: 回溯周期数 (4H)
    k1: float = 0.5  # 上轨系数
    k2: float = 0.5  # 下轨系数

    # MTF 参数
    trend_bar_type: str = ""  # 4H 周期
    trend_ema_period: int = 200

    # 过滤器参数
    atr_period: int = 20  # 波动率计算周期 (1H)

    # 风控参数
    stop_loss_atr_mult: float = 1.5  # 1.5倍 ATR 止损


class DualThrust(BaseStrategy):
    """
    Dual Thrust 策略实现 for NautilusTrader
    继承 BaseStrategy 以复用下单量计算与安全下单逻辑。

    逻辑说明:
    1. 趋势过滤: 1H 价格必须在 4H EMA 同侧。
    2. 突破逻辑: 1H 价格突破基于前 N 个 4H Bar 计算出的轨道。
    3. 离场逻辑: 反向信号反手离场。
    4. 风险管理: 入场时挂设基于 ATR 的硬止损单。
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
        self.ema_4h = ExponentialMovingAverage(config.trend_ema_period)
        self.atr = AverageTrueRange(config.atr_period)

        # 状态变量
        self.bars_4h: deque = deque(maxlen=config.lookback_period + 1)  # 存储4H K线
        self.trend_bar_type = (
            BarType.from_str(config.trend_bar_type) if config.trend_bar_type else None
        )

        self.current_range: Optional[Decimal] = None
        self.buy_line: Optional[Decimal] = None
        self.sell_line: Optional[Decimal] = None

        # 辅助变量：用于控制日志频率
        self._last_warmup_log_bars = 0

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

        # 订阅行情数据
        self.subscribe_bars(self.bar_type)
        if self.trend_bar_type:
            self.subscribe_bars(self.trend_bar_type)

        self.log.info(f"Dual Thrust Strategy started for {self.instrument_id}")
        self.log.info(
            f"Params: N={self.config.lookback_period} (4H), K1={self.config.k1}, K2={self.config.k2}"
        )
        self.log.info(
            f"MTF: Trend Bar={self.trend_bar_type}, EMA={self.config.trend_ema_period}"
        )
        self.log.info(f"Risk: SL={self.config.stop_loss_atr_mult}xATR")

    def on_bar(self, bar: Bar):
        """
        处理新的 Bar 数据
        """
        super().on_bar(bar)

        # --- A. 处理 4H 数据 (趋势与轨道计算层) ---
        if self.trend_bar_type and bar.bar_type == self.trend_bar_type:
            self.ema_4h.handle_bar(bar)
            self.bars_4h.append(bar)
            self._calculate_range()
            return

        # --- B. 处理 1H 数据 (交易执行层) ---
        if bar.bar_type == self.bar_type:
            self.atr.handle_bar(bar)

            # 检查系统热身状态
            if (
                not self.ema_4h.initialized
                or not self.atr.initialized
                or self.current_range is None
            ):
                total_main_bars = len(self.cache.bars(self.bar_type))
                if total_main_bars // 500 > self._last_warmup_log_bars:
                    self._last_warmup_log_bars = total_main_bars // 500
                    self.log.info(
                        f"Indicators Warming up... (Main Bars: {total_main_bars}) | "
                        f"EMA_4H: {'OK' if self.ema_4h.initialized else 'Wait'} | "
                        f"ATR_1H: {'OK' if self.atr.initialized else 'Wait'} | "
                        f"Range: {'OK' if self.current_range is not None else 'Wait'}"
                    )
                return

            # 计算当前执行层的轨道
            self._calculate_thresholds(bar)

            # 执行突破检查与下单逻辑
            self._check_signals(bar)

    def _calculate_range(self):
        """
        基于 4H 历史数据计算 Range
        Range = max(HH - LC, HC - LL)
        """
        if len(self.bars_4h) < self.config.lookback_period:
            return

        # 使用最近 lookback_period 个 4H Bar 作为参考
        reference_bars = list(self.bars_4h)[-self.config.lookback_period :]

        # 使用 Decimal 转换，确保计算精度并避免与 Price 对象直接运算的问题
        highs = [Decimal(str(b.high)) for b in reference_bars]
        lows = [Decimal(str(b.low)) for b in reference_bars]
        closes = [Decimal(str(b.close)) for b in reference_bars]

        hh = max(highs)
        hc = max(closes)
        lc = min(closes)
        ll = min(lows)

        self.current_range = max(hh - lc, hc - ll)

    def _calculate_thresholds(self, bar: Bar):
        """
        将计算出的 Range 应用到当前执行周期(1H)的开盘价上
        """
        if self.current_range is None:
            return

        current_open = Decimal(str(bar.open))
        k1 = Decimal(str(self.config.k1))
        k2 = Decimal(str(self.config.k2))

        self.buy_line = current_open + (self.current_range * k1)
        self.sell_line = current_open - (self.current_range * k2)

    def _check_signals(self, bar: Bar):
        """
        信号检查与订单执行
        """
        current_price = Decimal(str(bar.close))

        # --- 1. 趋势过滤器检查 (MTF) ---
        # 1H 价格必须在 4H EMA 同侧方可进场
        ema_val = Decimal(str(self.ema_4h.value))
        is_uptrend = current_price > ema_val
        is_downtrend = current_price < ema_val

        # --- 2. 仓位与风险准备 ---
        positions = self.cache.positions_open(instrument_id=self.instrument_id)
        qty = self.calculate_order_qty(current_price)

        # 止损距离计算 (ATR)
        atr_val = Decimal(str(self.atr.value))
        sl_dist = atr_val * Decimal(str(self.config.stop_loss_atr_mult))

        # --- 3. 逻辑 A: 做多突破 ---
        if self.buy_line and current_price > self.buy_line and is_uptrend:
            # 检查是否存在反向持仓，若是则平仓离场（反手逻辑）
            for p in positions:
                if p.is_short:
                    self.log.info(
                        f"Reverse Signal Detected: Price {current_price:.2f} > BuyLine {self.buy_line:.2f}. "
                        "Closing existing Short positions."
                    )
                    self.close_all_positions(self.instrument_id)
                    self.cancel_all_orders(self.instrument_id)
                    positions = []
                    break

            # 若无多头仓位且计算出有效数量，则进场
            has_long = any(p.is_long for p in positions)
            if not has_long and qty > 0:
                order = self.order_factory.market(
                    instrument_id=self.instrument_id,
                    order_side=OrderSide.BUY,
                    quantity=qty,
                )
                self.submit_order_safe(
                    order,
                    reason=f"DualThrust BUY Breakout (Price {current_price:.2f} > BuyLine {self.buy_line:.2f}) & 4H EMA Up",
                )

                # 设置基于 ATR 的硬止损单 (StopMarket)
                sl_price = current_price - sl_dist
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
                    sl_order,
                    reason=f"DualThrust ATR Stop Loss (SELL) @ {trigger_price}",
                )

        # --- 4. 逻辑 B: 做空突破 ---
        elif self.sell_line and current_price < self.sell_line and is_downtrend:
            # 检查是否存在多头持仓，若是则平仓离场
            for p in positions:
                if p.is_long:
                    self.log.info(
                        f"Reverse Signal Detected: Price {current_price:.2f} < SellLine {self.sell_line:.2f}. "
                        "Closing existing Long positions."
                    )
                    self.close_all_positions(self.instrument_id)
                    self.cancel_all_orders(self.instrument_id)
                    positions = []
                    break

            # 若无空头仓位且计算出有效数量，则进场
            has_short = any(p.is_short for p in positions)
            if not has_short and qty > 0:
                order = self.order_factory.market(
                    instrument_id=self.instrument_id,
                    order_side=OrderSide.SELL,
                    quantity=qty,
                )
                self.submit_order_safe(
                    order,
                    reason=f"DualThrust SELL Breakout (Price {current_price:.2f} < SellLine {self.sell_line:.2f}) & 4H EMA Down",
                )

                # 设置基于 ATR 的硬止损单
                sl_price = current_price + sl_dist
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
                    sl_order,
                    reason=f"DualThrust ATR Stop Loss (BUY) @ {trigger_price}",
                )

    def on_stop(self):
        """
        策略停止时清理所有订单与仓位
        """
        self.cancel_all_orders(self.instrument_id)
        self.close_all_positions(self.instrument_id)
        self.log.info("Dual Thrust Strategy stopped.")

    def on_reset(self):
        """
        策略重置时清除内部状态
        """
        super().on_reset()
        self.bars_4h.clear()
        self.current_range = None
        self.buy_line = None
        self.sell_line = None
        self.ema_4h.reset()
        self.atr.reset()
        self._last_warmup_log_bars = 0
