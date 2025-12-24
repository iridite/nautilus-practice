from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.core.message import Event
from nautilus_trader.indicators import MovingAverageConvergenceDivergence
from nautilus_trader.model import InstrumentId, QuoteTick
from nautilus_trader.model import Position
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.model.enums import PriceType
from nautilus_trader.model.events import PositionClosed
from nautilus_trader.model.events import PositionOpened
from nautilus_trader.trading.strategy import Strategy
from nautilus_trader.trading.strategy import StrategyConfig

class MACDEnhancedConfig(StrategyConfig):
    instrument_id: InstrumentId
    fast_period: int = 12
    slow_period: int = 26
    trade_size: int = 1_000_000
    entry_threshold: float = 0.00005
    exit_threshold: float = 0.00002
    stop_loss_pips: int = 20  # 以 pips 为单位的止损
    take_profit_pips: int = 40  # 以 pips 为单位的止盈


class MACDEnhancedStrategy(Strategy):
    """带止损与止盈的增强 MACD 策略。"""

    def __init__(self, config: MACDEnhancedConfig):
        super().__init__(config=config)
        self.macd = MovingAverageConvergenceDivergence(
            fast_period=config.fast_period, slow_period=config.slow_period, price_type=PriceType.MID
        )

        self.trade_size = Quantity.from_int(config.trade_size)
        self.position: Position | None = None
        self.last_macd_sign = 0

    def on_start(self):
        """策略启动时订阅行情数据。"""
        self.subscribe_quote_ticks(instrument_id=self.config.instrument_id)

    def on_stop(self):
        """策略停止时清理资源。"""
        self.cancel_all_orders(self.config.instrument_id)
        self.close_all_positions(self.config.instrument_id)
        self.unsubscribe_quote_ticks(instrument_id=self.config.instrument_id)

    def on_quote_tick(self, tick: QuoteTick):
        """处理收到的 quote tick。"""
        self.macd.handle_quote_tick(tick)

        if not self.macd.initialized:
            return

        self.check_signals(tick)

    def on_event(self, event: Event):
        """处理持仓相关事件。"""
        if isinstance(event, PositionOpened):
            self.position = self.cache.position(event.position_id)
            self._log.info(f"Position opened: {self.position.side} @ {self.position.avg_px_open}")
            # 下止损与止盈单
            self.place_exit_orders()
        elif isinstance(event, PositionClosed):
            if self.position and self.position.id == event.position_id:
                pnl = self.position.realized_pnl
                self._log.info(f"Position closed with PnL: {pnl}")
                self.position = None
                # 取消剩余的止损/止盈单
                self.cancel_all_orders(self.config.instrument_id)

    def check_signals(self, tick: QuoteTick):
        """检测 MACD 信号并管理持仓。"""
        current_macd = self.macd.value
        current_sign = 1 if current_macd > 0 else -1

        # 如果已有持仓则跳过
        if self.position:
            return

        # 检测 MACD 零线交叉
        if self.last_macd_sign != 0 and self.last_macd_sign != current_sign:
            if current_sign > 0:
                self.go_long(tick)
            else:
                self.go_short(tick)

        # 基于阈值的入场信号
        elif abs(current_macd) > self.config.entry_threshold:
            if current_macd > self.config.entry_threshold:
                self.go_long(tick)
            elif current_macd < -self.config.entry_threshold:
                self.go_short(tick)

        self.last_macd_sign = current_sign

    def go_long(self, tick: QuoteTick):
        """开多仓。"""
        if self.position:
            return  # 已有持仓

        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.BUY,
            quantity=self.trade_size,
        )
        self.submit_order(order)
        self._log.info(f"Going LONG @ {tick.ask_price} - MACD: {self.macd.value:.6f}")

    def go_short(self, tick: QuoteTick):
        """开空仓。"""
        if self.position:
            return  # 已有持仓

        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.SELL,
            quantity=self.trade_size,
        )
        self.submit_order(order)
        self._log.info(f"Going SHORT @ {tick.bid_price} - MACD: {self.macd.value:.6f}")

    def place_exit_orders(self):
        """为当前持仓下止损和止盈单。"""
        if not self.position:
            return

        entry_price = float(self.position.avg_px_open)
        pip_value = 0.0001  # 适用于 FX 货币对（不同品种需调整）

        if self.position.side == PositionSide.LONG:
            # 多头：止损在开仓价下方，目标在开仓价上方
            stop_price = entry_price - (self.config.stop_loss_pips * pip_value)
            target_price = entry_price + (self.config.take_profit_pips * pip_value)

            # 止损单
            stop_loss = self.order_factory.stop_market(
                instrument_id=self.config.instrument_id,
                order_side=OrderSide.SELL,
                quantity=self.trade_size,
                trigger_price=Price.from_str(f"{stop_price:.5f}"),
            )
            self.submit_order(stop_loss)

            # 止盈限价单
            take_profit = self.order_factory.limit(
                instrument_id=self.config.instrument_id,
                order_side=OrderSide.SELL,
                quantity=self.trade_size,
                price=Price.from_str(f"{target_price:.5f}"),
            )
            self.submit_order(take_profit)

            self._log.info(f"Placed LONG exit orders - Stop: {stop_price:.5f}, Target: {target_price:.5f}")

        else:  # 空头
            # 空头：止损在开仓价上方，目标在开仓价下方
            stop_price = entry_price + (self.config.stop_loss_pips * pip_value)
            target_price = entry_price - (self.config.take_profit_pips * pip_value)

            # 止损单
            stop_loss = self.order_factory.stop_market(
                instrument_id=self.config.instrument_id,
                order_side=OrderSide.BUY,
                quantity=self.trade_size,
                trigger_price=Price.from_str(f"{stop_price:.5f}"),
            )
            self.submit_order(stop_loss)

            # 止盈限价单
            take_profit = self.order_factory.limit(
                instrument_id=self.config.instrument_id,
                order_side=OrderSide.BUY,
                quantity=self.trade_size,
                price=Price.from_str(f"{target_price:.5f}"),
            )
            self.submit_order(take_profit)

            self._log.info(f"Placed SHORT exit orders - Stop: {stop_price:.5f}, Target: {target_price:.5f}")

    def on_dispose(self):
        """策略销毁时清理资源。"""