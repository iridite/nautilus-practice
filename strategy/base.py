from decimal import Decimal
from typing import Optional

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.enums import OrderSide, OrderType, PositionSide, TimeInForce
from nautilus_trader.model.events import PositionClosed
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.orders import Order
from nautilus_trader.trading.strategy import Strategy


class BaseStrategyConfig(StrategyConfig):  # pyright: ignore[reportGeneralTypeIssues]
    """
    Base configuration for strategies, including common risk management and position sizing parameters.
    """

    instrument_id: str

    # --- Position Sizing Parameters ---
    # 1. Fixed Quantity Mode: If set (not None), this fixed quantity is used (e.g., 0.1 for 0.1 BTC).
    # This takes precedence over dynamic calculation.
    trade_size: Optional[float] = None

    # 2. Dynamic Percentage Mode: Used if trade_size is None.
    # Logic: Qty = (Equity * qty_percent * leverage) / Price
    qty_percent: Optional[Decimal] = None  # e.g., 0.1 for 10% of equity

    # Leverage (Default: 1)
    # Applied in Dynamic Percentage Mode.
    leverage: int = 1

    # --- Risk Management ---
    # Stop Loss Percentage (e.g., 0.015 for 1.5%)
    # If set, a Stop Market order is automatically managed to prevent major drawdowns.
    stop_loss_pct: Optional[float] = None

    # Toggle for automated stop loss management.
    use_auto_sl: bool = True


class BaseStrategy(Strategy):
    """
    Base Strategy class encapsulating common logic for:
    1. Instrument initialization and state management.
    2. Unified position sizing calculation (Fixed vs Dynamic).
    3. Safe order submission with validation and enhanced logging.
    4. Robust auto-managed stop loss mechanism within the bar lifecycle.
    """

    def __init__(self, config: BaseStrategyConfig):
        super().__init__(config)
        self.base_config = config
        self.instrument: Instrument = None

    def on_start(self):
        """
        Lifecycle hook: Strategy Setup.
        Subclasses should call super().on_start() to ensure instrument is loaded.
        """
        if hasattr(self.config, "instrument_id") and self.config.instrument_id:
            instrument_id = self.config.instrument_id
            if isinstance(instrument_id, str):
                instrument_id = InstrumentId.from_str(instrument_id)
            self.instrument = self.cache.instrument(instrument_id)
            if not self.instrument:
                self.log.error(
                    f"BaseStrategy: Could not find instrument {self.config.instrument_id}"
                )
            else:
                self.log.info(f"BaseStrategy: Instrument {self.instrument.id} loaded.")
                if self.instrument.multiplier and self.instrument.multiplier != 1:
                    self.log.warning(
                        f"Instrument has non-standard multiplier: {self.instrument.multiplier}"
                    )

    def on_bar(self, bar):
        """
        Base lifecycle for bar processing.
        Subclasses MUST call super().on_bar(bar) to enable automated risk management.
        """
        self._manage_auto_stop_loss()

    def _manage_auto_stop_loss(self):
        """
        Monitors open positions and ensures a stop-loss order exists if configured.
        Priority: If the strategy has already placed a stop order (e.g., ATR stop),
        this managed SL will back off to avoid conflicts.
        """
        if (
            not self.base_config.use_auto_sl
            or self.base_config.stop_loss_pct is None
            or self.base_config.stop_loss_pct <= 0
        ):
            return

        instrument = self.get_instrument()
        positions = self.cache.positions_open(instrument_id=instrument.id)

        if not positions:
            return

        # Check for any existing stop orders for this instrument
        open_orders = self.cache.orders_open(instrument_id=instrument.id)
        has_stop = any(
            order.order_type in (OrderType.STOP_MARKET, OrderType.STOP_LIMIT)
            for order in open_orders
        )

        if has_stop:
            return

        for pos in positions:
            self.log.info(
                f"BaseStrategy: Auto-managing missing SL for position {str(pos.id)[:8]}"
            )

            entry_price = Decimal(str(pos.avg_px_open))
            qty = pos.quantity
            sl_pct = Decimal(str(self.base_config.stop_loss_pct))

            if pos.side == PositionSide.LONG:
                stop_price = entry_price * (1 - sl_pct)
                sl_side = OrderSide.SELL
            else:
                stop_price = entry_price * (1 + sl_pct)
                sl_side = OrderSide.BUY

            # Round to instrument precision
            if instrument.price_precision:
                stop_price = round(stop_price, instrument.price_precision)

            try:
                trigger_price = instrument.make_price(stop_price)

                # Use reduce_only=False for better compatibility with HEDGING backtests.
                sl_order = self.order_factory.stop_market(
                    instrument_id=instrument.id,
                    order_side=sl_side,
                    quantity=qty,
                    trigger_price=trigger_price,
                    reduce_only=False,
                    time_in_force=TimeInForce.GTC,
                )

                self.submit_order_safe(
                    sl_order,
                    reason=f"Auto-Managed SL ({self.base_config.stop_loss_pct:.1%})",
                )
            except Exception as e:
                self.log.error(f"Failed to submit auto-managed SL: {e}")

    def on_position_closed(self, event: PositionClosed):
        """
        Event handler for PositionClosed.
        Ensures all remaining orders are cancelled to prevent "ghost" orders.
        """
        super().on_position_closed(event)
        if self.instrument and event.instrument_id == self.instrument.id:
            self.cancel_all_orders(event.instrument_id)
            self.log.info(
                f"BaseStrategy: Position closed for {event.instrument_id}, all orders cancelled."
            )

    def get_instrument(self) -> Instrument:
        """
        Helper to get the main instrument, initializing if necessary.
        """
        if self.instrument:
            return self.instrument
        if hasattr(self.config, "instrument_id") and self.config.instrument_id:
            instrument_id = self.config.instrument_id
            if isinstance(instrument_id, str):
                instrument_id = InstrumentId.from_str(instrument_id)
            self.instrument = self.cache.instrument(instrument_id)
        if not self.instrument:
            raise ValueError(
                "Instrument not initialized. Ensure super().on_start() was called."
            )
        return self.instrument

    def calculate_order_qty(self, price: float | Decimal) -> Quantity:
        """
        Unified logic for calculating order quantity (Fixed vs Dynamic).
        """
        price = Decimal(str(price))
        if price <= 0:
            return Quantity.from_int(0)

        instrument = self.get_instrument()

        # Mode 1: Fixed Trade Size
        if self.base_config.trade_size is not None and self.base_config.trade_size > 0:
            return instrument.make_qty(self.base_config.trade_size)

        # Mode 2: Dynamic Percentage Sizing
        if (
            self.base_config.qty_percent is not None
            and self.base_config.qty_percent > 0
        ):
            return self._calculate_dynamic_qty(instrument, price)

        return Quantity.from_int(0)

    def _calculate_dynamic_qty(
        self, instrument: Instrument, price: Decimal
    ) -> Quantity:
        try:
            accounts = self.cache.accounts()
            if not accounts:
                return Quantity.from_int(0)

            account = next(
                (a for a in accounts if a.balance(instrument.quote_currency)),
                accounts[0],
            )
            balance = account.balance(instrument.quote_currency)
            if not balance:
                return Quantity.from_int(0)

            equity = balance.total.as_decimal()
            if equity <= 0:
                return Quantity.from_int(0)

            leverage = max(1, self.base_config.leverage)
            if hasattr(instrument, "max_leverage") and instrument.max_leverage:
                leverage = min(leverage, instrument.max_leverage)

            target_notional = equity * self.base_config.qty_percent * leverage
            raw_qty = target_notional / price

            if instrument.multiplier:
                multiplier = Decimal(str(instrument.multiplier))
                if multiplier > 0:
                    raw_qty = raw_qty / multiplier

            if instrument.size_increment:
                min_size = instrument.size_increment.as_decimal()
                if raw_qty < min_size:
                    return Quantity.from_int(0)

            return instrument.make_qty(raw_qty)
        except Exception as e:
            self.log.error(f"Dynamic qty calculation error: {e}")
            return Quantity.from_int(0)

    def submit_order_safe(self, order: Order, reason: str = ""):
        """
        Submit an order with validation and standardized logging.
        """
        if order is None:
            self.log.error("Cannot submit None order.")
            return

        if order.quantity <= 0:
            self.log.warn(
                f"Order quantity invalid: {order.quantity}. Order not submitted."
            )
            return

        self.submit_order(order)
        self._log_order_submission(order, reason)

    def _log_order_submission(self, order: Order, reason: str):
        """
        Pretty-print order submission details.
        """
        side = "BUY" if order.side == OrderSide.BUY else "SELL"
        order_type = str(order.order_type)

        price_str = "Market"
        if hasattr(order, "trigger_price"):
            price_str = f"Trigger@{order.trigger_price}"
        elif hasattr(order, "price"):
            price_str = str(order.price)

        self.log.info(
            f"\n{'=' * 60}\n"
            f"🚀 [ORDER SUBMITTED] {side} ({order_type})\n"
            f"   Instrument: {order.instrument_id}\n"
            f"   Quantity:   {order.quantity}\n"
            f"   Price:      {price_str}\n"
            f"   Reason:     {reason}\n"
            f"{'=' * 60}"
        )

    def on_reset(self):
        """
        Strategy Reset.
        """
        self.instrument = None
