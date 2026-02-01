from decimal import Decimal
from typing import List, Optional

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

    Provides unified interface for position sizing, risk management, and data dependencies.
    """

    oms_type: str = "NETTING"

    # 简化配置字段（推荐使用）
    symbol: str = ""  # 简化标的名称，如 "ETHUSDT"（永续）或 "ETH"（现货）
    timeframe: str = ""  # 时间框架，如 "1d", "1h", "15m"
    price_type: str = "LAST"  # 价格类型：LAST, MID, BID, ASK
    origination: str = "EXTERNAL"  # 数据来源：EXTERNAL, INTERNAL

    # 完整配置字段（向后兼容，自动从简化字段生成）
    instrument_id: str = ""  # 完整标的ID，如 "ETHUSDT-PERP.BINANCE"
    bar_type: str = ""  # 完整bar类型，如 "ETHUSDT-PERP.BINANCE-1-DAY-LAST-EXTERNAL"

    # 数据依赖列表：策略所需的数据类型，例如 ["ohlcv", "oi", "funding"]
    data_types: List[str] = []

    # 时间框架依赖列表：策略所需的时间框架，例如 ["main"] 或 ["main", "trend"]
    # 如果为空列表，默认加载 ["main"]
    timeframes: List[str] = []

    # --- Position Sizing Parameters ---
    # 1. Fixed Quantity Mode: DEPRECATED - 已废弃，不再支持
    # 使用此参数将抛出错误，请改用 qty_percent 或 use_atr_position_sizing
    trade_size: Optional[float] = None

    # 2. Dynamic Percentage Mode: 动态百分比模式
    # Logic: Qty = (Equity * qty_percent * leverage) / Price
    qty_percent: Optional[Decimal | float] = None  # e.g., 0.1 for 10% of equity

    # 3. ATR Risk Mode: ATR风险模式（优先级高于动态百分比）
    # 启用后需要在 calculate_order_qty 中传入 atr_value 参数
    # Logic: Qty = (Equity * max_position_risk_pct) / (ATR * atr_stop_multiplier)
    use_atr_position_sizing: bool = False  # 启用ATR仓位计算

    # Leverage (Default: 1)
    # Applied in Dynamic Percentage Mode and ATR Mode.
    leverage: int = 1

    # --- Risk Management ---
    # Maximum number of concurrent positions allowed
    max_positions: int = 1

    # Stop Loss Percentage (e.g., 0.015 for 1.5%)
    # If set, a Stop Market order is automatically managed to prevent major drawdowns.
    stop_loss_pct: Optional[float] = None  # pct for percent

    # Toggle for automated stop loss management.
    use_auto_sl: bool = True

    # --- ATR-Based Risk Management ---
    # ATR参数（用于模式3：ATR风险仓位计算）
    atr_period: int = 14  # ATR计算周期
    atr_stop_multiplier: float = 2.0  # ATR止损倍数 (2.0 = 2× ATR)
    max_position_risk_pct: float = 0.02  # 单笔交易最大风险百分比 (2% of account equity)


class BaseStrategy(Strategy):
    """
    Base Strategy class encapsulating common logic for:
    1. Instrument initialization and state management.
    2. Unified position sizing calculation (Fixed vs Dynamic).
    3. Safe order submission with validation and enhanced logging.
    4. Robust auto-managed stop loss mechanism within the bar lifecycle.
    5. Data dependency validation and management.
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
        # self.config: strategy-specific config; self.base_config: BaseStrategyConfig fields
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
        """自动止损：为持仓补充缺失的止损单"""
        if not self.base_config.use_auto_sl or not self.base_config.stop_loss_pct:
            return

        instrument = self.get_instrument()
        positions = self.cache.positions_open(instrument_id=instrument.id)
        if not positions:
            return

        # 如果已有止损单，跳过
        if any(o.order_type in (OrderType.STOP_MARKET, OrderType.STOP_LIMIT)
               for o in self.cache.orders_open(instrument_id=instrument.id)):
            return

        sl_pct = Decimal(str(self.base_config.stop_loss_pct))

        for pos in positions:
            entry_price = Decimal(str(pos.avg_px_open))

            if pos.side == PositionSide.LONG:
                stop_price = entry_price * (1 - sl_pct)
                sl_side = OrderSide.SELL
            else:
                stop_price = entry_price * (1 + sl_pct)
                sl_side = OrderSide.BUY

            if instrument.price_precision:
                stop_price = round(stop_price, instrument.price_precision)

            sl_order = self.order_factory.stop_market(
                instrument_id=instrument.id,
                order_side=sl_side,
                quantity=pos.quantity,
                trigger_price=instrument.make_price(stop_price),
                reduce_only=False,
                time_in_force=TimeInForce.GTC,
            )

            self.submit_order_safe(sl_order, f"Auto SL {self.base_config.stop_loss_pct:.1%}")

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

    def calculate_order_qty(self, price: float | Decimal, atr_value: Optional[Decimal] = None) -> Quantity:
        """
        计算下单数量（仓位大小）

        根据配置的模式计算每次下单的数量：
        - 模式1（固定数量）: 已废弃，不再支持
        - 模式2（动态百分比）: 使用 qty_percent 参数，根据账户权益动态计算
          公式: 数量 = (账户权益 × 百分比 × 杠杆) / 价格
          例如: 权益10000U，10%，2x杠杆，BTC价格50000 → 下单 0.04 BTC
        - 模式3（ATR风险）: 使用 use_atr_position_sizing=True，基于ATR和风险百分比计算
          公式: 数量 = (账户权益 × 风险百分比) / (ATR × 止损倍数)
          例如: 权益10000U，风险2%，ATR=100，止损2倍 → 风险200U，止损距离200，下单1个合约

        Parameters
        ----------
        price : float | Decimal
            当前市场价格
        atr_value : Optional[Decimal]
            ATR值，用于模式3的风险仓位计算

        Returns
        -------
        Quantity
            计算得到的下单数量（仓位大小）
        """
        price = Decimal(str(price))
        if price <= 0:
            return Quantity.from_int(0)

        instrument = self.get_instrument()

        # Mode 1: Fixed Trade Size (DEPRECATED)
        if self.base_config.trade_size is not None and self.base_config.trade_size > 0:
            self.log.error(
                "固定仓位模式(trade_size)已废弃，不再支持。"
                "请使用动态百分比模式(qty_percent)或ATR风险模式(use_atr_position_sizing=True)"
            )
            raise ValueError("trade_size mode is deprecated. Use qty_percent or ATR-based sizing.")

        # Mode 3: ATR-Based Risk Sizing (Priority)
        if self.base_config.use_atr_position_sizing and atr_value is not None and atr_value > 0:
            return self._calculate_atr_qty(instrument, price, atr_value)

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

            leverage = Decimal(max(1, self.base_config.leverage))
            if hasattr(instrument, "max_leverage") and instrument.max_leverage:
                leverage = min(leverage, Decimal(instrument.max_leverage))

            qty_percent = Decimal(str(self.base_config.qty_percent)) if isinstance(self.base_config.qty_percent, float) else self.base_config.qty_percent
            target_notional = equity * qty_percent * leverage
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

    def check_sufficient_balance(
        self, notional_value: Decimal, instrument: Optional[Instrument] = None
    ) -> bool:
        """
        检查账户余额是否足够支持交易

        Parameters
        ----------
        notional_value : Decimal
            交易名义价值
        instrument : Optional[Instrument]
            交易工具，默认使用self.instrument

        Returns
        -------
        bool
            True if sufficient balance, False otherwise
        """
        if notional_value <= 0:
            return True

        try:
            if instrument is None:
                instrument = self.get_instrument()

            if instrument is None:
                self.log.warning("无法获取标的信息")
                return False

            accounts = self.cache.accounts()
            if not accounts:
                self.log.warning("无法获取账户信息")
                return False

            quote_currency = instrument.quote_currency
            account = next(
                (a for a in accounts if a.balance(quote_currency)), accounts[0]
            )

            balance = account.balance(quote_currency)
            if not balance:
                self.log.warning(f"无法获取{quote_currency}余额")
                return False

            available = balance.free.as_decimal()

            if available < notional_value:
                self.log.warning(
                    f"余额不足: 需要{notional_value:.2f}, 可用{available:.2f}"
                )
                return False

            return True

        except Exception as e:
            self.log.error(f"余额检查失败: {e}")
            return False

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

        # Log order submission
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

    # ========================================================================
    # ATR-Based Risk Management Methods
    # ========================================================================



    def _calculate_atr_qty(
        self, instrument: Instrument, price: Decimal, atr_value: Decimal
    ) -> Quantity:
        """
        基于ATR的风险仓位计算（模式3）

        行业标准公式:
        1. 止损距离 = ATR × 止损倍数
        2. 风险金额 = 账户权益 × 风险百分比
        3. 合约数量 = 风险金额 / 止损距离
        4. 实际数量 = 合约数量 / 价格（现货）或 合约数量（期货）

        Parameters
        ----------
        instrument : Instrument
            交易工具
        price : Decimal
            当前价格
        atr_value : Decimal
            ATR值

        Returns
        -------
        Quantity
            计算得到的下单数量
        """
        try:
            # 获取账户权益
            accounts = self.cache.accounts()
            if not accounts:
                self.log.warning("ATR仓位计算: 无法获取账户信息")
                return Quantity.from_int(0)

            account = next(
                (a for a in accounts if a.balance(instrument.quote_currency)),
                accounts[0],
            )
            balance = account.balance(instrument.quote_currency)
            if not balance:
                self.log.warning("ATR仓位计算: 无法获取余额")
                return Quantity.from_int(0)

            equity = balance.total.as_decimal()
            if equity <= 0:
                return Quantity.from_int(0)

            # 计算止损距离（价格单位）
            stop_distance = atr_value * Decimal(str(self.base_config.atr_stop_multiplier))

            # 计算最大风险金额
            max_risk_amount = equity * Decimal(str(self.base_config.max_position_risk_pct))

            # 计算基础数量: 风险金额 / 止损距离
            # 这给出了在止损距离下，损失等于风险金额的仓位大小
            raw_qty = max_risk_amount / stop_distance

            # 应用杠杆
            leverage = Decimal(max(1, self.base_config.leverage))
            if hasattr(instrument, "max_leverage") and instrument.max_leverage:
                leverage = min(leverage, Decimal(instrument.max_leverage))
            raw_qty = raw_qty * leverage

            # 处理合约乘数
            if instrument.multiplier:
                multiplier = Decimal(str(instrument.multiplier))
                if multiplier > 0:
                    raw_qty = raw_qty / multiplier

            # 检查最小数量
            if instrument.size_increment:
                min_size = instrument.size_increment.as_decimal()
                if raw_qty < min_size:
                    self.log.warning(
                        f"ATR仓位计算: 计算数量{raw_qty}小于最小数量{min_size}"
                    )
                    return Quantity.from_int(0)

            qty = instrument.make_qty(raw_qty)

            self.log.info(
                f"ATR仓位计算: 权益={equity:.2f}, ATR={atr_value:.2f}, "
                f"止损距离={stop_distance:.2f}, 风险金额={max_risk_amount:.2f}, "
                f"数量={qty}"
            )

            return qty

        except Exception as e:
            self.log.error(f"ATR仓位计算错误: {e}")
            return Quantity.from_int(0)
