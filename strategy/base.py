from decimal import Decimal
from typing import Optional

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.orders import MarketOrder, Order
from nautilus_trader.trading.strategy import Strategy


class BaseStrategyConfig(StrategyConfig):
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


class BaseStrategy(Strategy):
    """
    Base Strategy class encapsulating common logic for:
    1. Instrument initialization
    2. Unified position sizing calculation (Fixed vs Dynamic)
    3. Safe order submission with validation and enhanced logging
    """

    def __init__(self, config: BaseStrategyConfig):
        super().__init__(config)
        self.base_config = config  # Typed alias for easier access
        self.instrument: Optional[Instrument] = None

    def on_start(self):
        """
        Lifecycle hook: Strategy Setup.
        Subclasses should call super().on_start() to ensure instrument is loaded.
        """
        # Attempt to load instrument if ID is provided in config
        if hasattr(self.config, "instrument_id") and self.config.instrument_id:
            self.instrument = self.cache.instrument(self.config.instrument_id)
            if not self.instrument:
                self.log.error(
                    f"BaseStrategy: Could not find instrument {self.config.instrument_id}"
                )
            else:
                self.log.info(f"BaseStrategy: Instrument {self.instrument.id} loaded.")

                # warning on non-one order multiplier
                if self.instrument.multiplier and self.instrument.multiplier != 1:
                    self.log.warning(
                        f"Current instrument have non-one order multiplier, it is {self.instrument.multiplier}"
                    )

    def on_reset(self):
        """
        Lifecycle hook: Strategy Reset.
        Clears internal state to prevent issues during multiple backtest runs.
        """
        self.instrument = None

    def get_instrument(self) -> Instrument:
        """
        Helper to get the main instrument, initializing it if necessary.
        """
        if self.instrument:
            return self.instrument

        if hasattr(self.config, "instrument_id") and self.config.instrument_id:
            self.instrument = self.cache.instrument(self.config.instrument_id)

        if not self.instrument:
            raise ValueError(
                "Instrument not initialized. "
                "Ensure 'instrument_id' is in config and valid, or call super().on_start()."
            )
        return self.instrument

    def recommend_leverage(self) -> Optional[int]:
        """
        Override this method to provide dynamic leverage recommendations.
        Priority: recommend_leverage() > config.leverage > 1
        """
        return None

    def calculate_order_qty(self, price: float | Decimal) -> Quantity:
        """
        Unified logic for calculating order quantity.

        Logic:
        1. If config.trade_size is set -> Use Fixed Quantity.
        2. If config.qty_percent is set -> Use Dynamic Calculation:
           Qty = (Equity * qty_percent * effective_leverage) / Price
        3. Else -> Log Error & Return 0.

        Includes checks for:
        - Account Balance/Equity
        - Instrument Max Leverage
        - Zero/Negative Price
        """
        price = Decimal(str(price))
        if price <= 0:
            self.log.error(f"Invalid price for calculation: {price}")
            return Quantity.from_int(0)

        instrument = self.get_instrument()

        # --- Mode 1: Fixed Trade Size ---
        if self.base_config.trade_size is not None and self.base_config.trade_size > 0:
            # Direct fixed quantity
            try:
                qty = instrument.make_qty(self.base_config.trade_size)
                return qty
            except Exception as e:
                self.log.error(
                    f"Error creating fixed qty from {self.base_config.trade_size}: {e}"
                )
                return Quantity.from_int(0)

        # --- Mode 2: Dynamic Position Sizing ---
        if (
            self.base_config.qty_percent is not None
            and self.base_config.qty_percent > 0
        ):
            return self._calculate_dynamic_qty(instrument, price)

        # --- No valid configuration ---
        self.log.error(
            "Position sizing configuration missing: Set 'trade_size' or 'qty_percent'."
        )
        return Quantity.from_int(0)

    def _calculate_dynamic_qty(
        self, instrument: Instrument, price: Decimal
    ) -> Quantity:
        """
        Internal method for dynamic quantity calculation based on equity.
        """
        try:
            # 1. Retrieve Account/Balance
            # Note: Assuming single account or first available account for simplicity.
            # In multi-account setups, logic to select the correct account ID is needed.
            accounts = self.cache.accounts()
            if not accounts:
                self.log.error("No accounts found in cache.")
                return Quantity.from_int(0)

            # Prefer account matching the quote currency if possible, else take first
            account = None
            for acc in accounts:
                if acc.balance(instrument.quote_currency) is not None:
                    account = acc
                    break
            if not account:
                account = accounts[0]

            balance = account.balance(instrument.quote_currency)
            if not balance:
                self.log.error(
                    f"No balance found for quote currency: {instrument.quote_currency}"
                )
                return Quantity.from_int(0)

            # Use .as_decimal() to extract Decimal from Money object for arithmetic
            equity = balance.total.as_decimal()

            if equity <= 0:
                self.log.warn(f"Insufficient equity: {equity}. Cannot open position.")
                return Quantity.from_int(0)

            # 2. Determine Leverage
            rec_leverage = self.recommend_leverage()
            leverage = (
                rec_leverage if rec_leverage is not None else self.base_config.leverage
            )
            # Ensure leverage is at least 1
            leverage = max(1, leverage)

            # 3. Cap Leverage by Instrument Limits
            if hasattr(instrument, "max_leverage") and instrument.max_leverage:
                if leverage > instrument.max_leverage:
                    # self.log.debug(f"Capping leverage {leverage} -> {instrument.max_leverage}")
                    leverage = instrument.max_leverage

            # 4. Calculate Notional and Quantity
            target_notional = equity * self.base_config.qty_percent * leverage
            raw_qty = target_notional / price

            # Account for instrument multiplier (e.g. OKX SWAP contract size = 0.1 or 0.01 etc.)
            # If multiplier is 0.1, it means 1 contract = 0.1 units of underlying.
            # So we need 10x more contracts to match the target notional.
            if instrument.multiplier:
                multiplier = Decimal(str(instrument.multiplier))
                if multiplier > 0 and multiplier != 1:
                    raw_qty = raw_qty / multiplier

            # Check against minimum size increment to avoid "rounded to zero" errors
            if instrument.size_increment:
                try:
                    min_size = instrument.size_increment.as_decimal()
                    if min_size > 0 and raw_qty < min_size:
                        self.log.warn(
                            f"Calculated qty {raw_qty:.8f} is below instrument min size {min_size}. "
                            "Skipping trade."
                        )
                        return Quantity.from_int(0)
                except AttributeError:
                    pass  # Fallback: let make_qty handle validation if as_decimal fails

            return instrument.make_qty(raw_qty)

        except ValueError as e:
            if "rounded to zero" in str(e):
                self.log.warn(f"Qty too small (rounded to zero): {e}")
                return Quantity.from_int(0)
            self.log.error(f"ValueError in dynamic qty calculation: {e}")
            return Quantity.from_int(0)
        except Exception as e:
            self.log.error(f"Error in dynamic qty calculation: {e}")
            return Quantity.from_int(0)

    def submit_order_safe(self, order: Order, reason: str = ""):
        """
        Submit an order with pre-checks and standardized formatting logging.
        """
        if order is None:
            self.log.error("Cannot submit None order.")
            return

        if order.quantity <= 0:
            self.log.warn(
                f"Order quantity invalid: {order.quantity}. Order not submitted."
            )
            return

        # Submit
        self.submit_order(order)

        # Log
        self._log_order_submission(order, reason)

    def _log_order_submission(self, order: Order, reason: str):
        """
        Pretty-print order submission details.
        """
        side = "BUY" if order.side == OrderSide.BUY else "SELL"
        order_type = "MARKET" if isinstance(order, MarketOrder) else "LIMIT"
        price_str = f"{order.price}" if hasattr(order, "price") else "Market"

        self.log.info(
            f"\n{'=' * 60}\n"
            f"🚀 [ORDER SUBMITTED] {side} ({order_type})\n"
            f"   Instrument: {order.instrument_id}\n"
            f"   Quantity:   {order.quantity}\n"
            f"   Price:      {price_str}\n"
            f"   Reason:     {reason}\n"
            f"{'=' * 60}"
        )
