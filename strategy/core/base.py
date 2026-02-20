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
from config.constants import DEFAULT_ATR_PERIOD, DEFAULT_RISK_PER_TRADE


class BaseStrategyConfig(StrategyConfig):  # pyright: ignore[reportGeneralTypeIssues]
    """
    Base configuration for strategies, including common risk management and position sizing parameters.

    Provides unified interface for position sizing, risk management, and data dependencies.
    """

    oms_type: str = "NETTING"  # 持仓模式：NETTING（净持仓）或 HEDGING（对冲持仓），默认从环境配置读取

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
    atr_period: int = DEFAULT_ATR_PERIOD  # ATR计算周期
    atr_stop_multiplier: float = 2.0  # ATR止损倍数 (2.0 = 2× ATR)
    max_position_risk_pct: float = DEFAULT_RISK_PER_TRADE  # 单笔交易最大风险百分比 (2% of account equity)


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

        # HEDGING 模式持仓跟踪器
        self._positions_tracker = {}  # {position_id: {side, entry_price, extreme_price, entry_time}}
        self._pending_orders = {}  # {order_id: metadata}

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
        # 更新 HEDGING 模式的持仓跟踪器
        if self.base_config.oms_type == "HEDGING":
            self._update_positions_tracker(bar)

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

            # 清理 HEDGING 模式的持仓跟踪
            if event.position_id in self._positions_tracker:
                del self._positions_tracker[event.position_id]

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

    def _validate_price(self, price: float | Decimal) -> Decimal | None:
        """验证价格，返回Decimal或None"""
        price = Decimal(str(price))
        if price <= 0:
            return None
        return price

    def _check_deprecated_trade_size(self):
        """检查是否使用了已废弃的trade_size模式"""
        if self.base_config.trade_size is not None and self.base_config.trade_size > 0:
            self.log.error(
                "固定仓位模式(trade_size)已废弃，不再支持。"
                "请使用动态百分比模式(qty_percent)或ATR风险模式(use_atr_position_sizing=True)"
            )
            raise ValueError("trade_size mode is deprecated. Use qty_percent or ATR-based sizing.")

    def _should_use_atr_sizing(self, atr_value: Optional[Decimal]) -> bool:
        """判断是否应该使用ATR风险模式"""
        return (
            self.base_config.use_atr_position_sizing
            and atr_value is not None
            and atr_value > 0
        )

    def _should_use_percent_sizing(self) -> bool:
        """判断是否应该使用百分比模式"""
        return (
            self.base_config.qty_percent is not None
            and self.base_config.qty_percent > 0
        )

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
        validated_price = self._validate_price(price)
        if validated_price is None:
            return Quantity.from_int(0)

        instrument = self.get_instrument()

        self._check_deprecated_trade_size()

        if self._should_use_atr_sizing(atr_value):
            return self._calculate_atr_qty(instrument, validated_price, atr_value)

        if self._should_use_percent_sizing():
            return self._calculate_dynamic_qty(instrument, validated_price)

        return Quantity.from_int(0)

    def _get_account_equity(self, instrument: Instrument) -> Decimal | None:
        """获取账户权益"""
        accounts = self.cache.accounts()
        if not accounts:
            return None

        account = next(
            (a for a in accounts if a.balance(instrument.quote_currency)),
            accounts[0],
        )
        balance = account.balance(instrument.quote_currency)
        if not balance:
            return None

        equity = balance.total.as_decimal()
        if equity <= 0:
            return None

        return equity

    def _calculate_effective_leverage(self, instrument: Instrument) -> Decimal:
        """计算有效杠杆（考虑交易所限制）"""
        leverage = Decimal(max(1, self.base_config.leverage))
        if hasattr(instrument, "max_leverage") and instrument.max_leverage:
            leverage = min(leverage, Decimal(instrument.max_leverage))
        return leverage

    def _calculate_raw_quantity(self, equity: Decimal, leverage: Decimal, price: Decimal, instrument: Instrument) -> Decimal:
        """计算原始数量（考虑合约乘数）"""
        qty_percent = Decimal(str(self.base_config.qty_percent)) if isinstance(self.base_config.qty_percent, float) else self.base_config.qty_percent
        target_notional = equity * qty_percent * leverage
        raw_qty = target_notional / price

        if instrument.multiplier:
            multiplier = Decimal(str(instrument.multiplier))
            if multiplier > 0:
                raw_qty = raw_qty / multiplier

        return raw_qty

    def _validate_minimum_size(self, raw_qty: Decimal, instrument: Instrument) -> bool:
        """验证是否满足最小下单量"""
        if instrument.size_increment:
            min_size = instrument.size_increment.as_decimal()
            if raw_qty < min_size:
                return False
        return True

    def _calculate_dynamic_qty(
        self, instrument: Instrument, price: Decimal
    ) -> Quantity:
        try:
            equity = self._get_account_equity(instrument)
            if equity is None:
                return Quantity.from_int(0)

            leverage = self._calculate_effective_leverage(instrument)
            raw_qty = self._calculate_raw_quantity(equity, leverage, price, instrument)

            if not self._validate_minimum_size(raw_qty, instrument):
                return Quantity.from_int(0)

            return instrument.make_qty(raw_qty)
        except Exception as e:
            self.log.error(f"Dynamic qty calculation error: {e}")
            return Quantity.from_int(0)

    def _get_instrument_for_balance_check(self, instrument: Optional[Instrument]) -> Optional[Instrument]:
        """获取用于余额检查的标的"""
        if instrument is None:
            instrument = self.get_instrument()

        if instrument is None:
            self.log.warning("无法获取标的信息")

        return instrument

    def _get_account_for_currency(self, quote_currency) -> Optional[object]:
        """获取指定货币的账户"""
        accounts = self.cache.accounts()
        if not accounts:
            self.log.warning("无法获取账户信息")
            return None

        return next(
            (a for a in accounts if a.balance(quote_currency)), accounts[0]
        )

    def _get_available_balance(self, account, quote_currency) -> Optional[Decimal]:
        """获取可用余额"""
        balance = account.balance(quote_currency)
        if not balance:
            self.log.warning(f"无法获取{quote_currency}余额")
            return None

        return balance.free.as_decimal()

    def _check_balance_sufficient(self, available: Decimal, notional_value: Decimal) -> bool:
        """检查余额是否充足"""
        if available < notional_value:
            self.log.warning(
                f"余额不足: 需要{notional_value:.2f}, 可用{available:.2f}"
            )
            return False
        return True

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
            instrument = self._get_instrument_for_balance_check(instrument)
            if instrument is None:
                return False

            account = self._get_account_for_currency(instrument.quote_currency)
            if account is None:
                return False

            available = self._get_available_balance(account, instrument.quote_currency)
            if available is None:
                return False

            return self._check_balance_sufficient(available, notional_value)

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
        self._positions_tracker = {}
        self._pending_orders = {}

    # ========================================================================
    # HEDGING Mode Position Tracking
    # ========================================================================

    def _update_positions_tracker(self, bar):
        """更新 HEDGING 模式的持仓跟踪器（自动调用）"""
        if not self.instrument:
            return

        positions = self.cache.positions_open(instrument_id=self.instrument.id)
        for pos in positions:
            pos_id = pos.id
            if pos_id not in self._positions_tracker:
                # 恢复持仓跟踪（策略重启场景）
                side_str = 'LONG' if pos.side == PositionSide.LONG else 'SHORT'
                self._positions_tracker[pos_id] = {
                    'side': side_str,
                    'entry_price': float(pos.avg_px_open),
                    'extreme_price': float(bar.high if side_str == 'LONG' else bar.low),
                    'entry_time': pos.ts_opened
                }
            else:
                # 更新极值价格（多头跟踪最高价，空头跟踪最低价）
                tracker = self._positions_tracker[pos_id]
                if tracker['side'] == 'LONG':
                    tracker['extreme_price'] = max(tracker['extreme_price'], float(bar.high))
                else:  # SHORT
                    tracker['extreme_price'] = min(tracker['extreme_price'], float(bar.low))

    def track_order_for_position(self, order_id, side: OrderSide, bar, **metadata):
        """记录订单元数据，等待成交后关联持仓

        Args:
            order_id: 订单ID
            side: 订单方向（OrderSide.BUY 或 OrderSide.SELL）
            bar: 当前 K 线
            **metadata: 额外的元数据（如 high_conviction 等）
        """
        self._pending_orders[order_id] = {
            'side': side.name,
            'entry_price': float(bar.close),
            'extreme_price': float(bar.high if side == OrderSide.BUY else bar.low),
            'entry_time': bar.ts_event,
            **metadata
        }

    def on_order_filled(self, event):
        """订单成交回调（HEDGING 模式：自动关联订单与持仓）"""
        super().on_order_filled(event)

        # 检查是否是入场订单
        order_id = event.client_order_id
        if order_id in self._pending_orders:
            # 获取订单元数据
            metadata = self._pending_orders.pop(order_id)

            # 查找新创建的持仓
            if self.instrument:
                positions = self.cache.positions_open(instrument_id=self.instrument.id)
                for pos in positions:
                    if pos.id not in self._positions_tracker:
                        # 关联持仓与元数据
                        self._positions_tracker[pos.id] = metadata
                        self.log.info(f"持仓跟踪已建立: Position {pos.id}")
                        break

    def on_order_rejected(self, event):
        """订单拒绝回调（HEDGING 模式：清理被拒绝的订单）"""
        super().on_order_rejected(event)

        # 清理被拒绝的订单
        order_id = event.client_order_id
        if order_id in self._pending_orders:
            del self._pending_orders[order_id]

    # ========================================================================
    # ATR-Based Risk Management Methods
    # ========================================================================



    def _get_account_equity_for_atr(self, instrument: Instrument) -> Decimal | None:
        """获取账户权益（ATR计算专用）"""
        accounts = self.cache.accounts()
        if not accounts:
            self.log.warning("ATR仓位计算: 无法获取账户信息")
            return None

        account = next(
            (a for a in accounts if a.balance(instrument.quote_currency)),
            accounts[0],
        )
        balance = account.balance(instrument.quote_currency)
        if not balance:
            self.log.warning("ATR仓位计算: 无法获取余额")
            return None

        equity = balance.total.as_decimal()
        if equity <= 0:
            return None

        return equity

    def _calculate_atr_stop_distance(self, atr_value: Decimal) -> Decimal:
        """计算ATR止损距离"""
        return atr_value * Decimal(str(self.base_config.atr_stop_multiplier))

    def _calculate_max_risk_amount(self, equity: Decimal) -> Decimal:
        """计算最大风险金额"""
        return equity * Decimal(str(self.base_config.max_position_risk_pct))

    def _calculate_atr_raw_quantity(self, max_risk_amount: Decimal, stop_distance: Decimal, instrument: Instrument) -> Decimal:
        """计算ATR原始数量（含杠杆和乘数调整）"""
        # 基础数量: 风险金额 / 止损距离
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

        return raw_qty

    def _validate_atr_minimum_size(self, raw_qty: Decimal, instrument: Instrument) -> bool:
        """验证ATR计算的最小数量"""
        if instrument.size_increment:
            min_size = instrument.size_increment.as_decimal()
            if raw_qty < min_size:
                self.log.warning(
                    f"ATR仓位计算: 计算数量{raw_qty}小于最小数量{min_size}"
                )
                return False
        return True

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
            equity = self._get_account_equity_for_atr(instrument)
            if equity is None:
                return Quantity.from_int(0)

            stop_distance = self._calculate_atr_stop_distance(atr_value)
            max_risk_amount = self._calculate_max_risk_amount(equity)
            raw_qty = self._calculate_atr_raw_quantity(max_risk_amount, stop_distance, instrument)

            if not self._validate_atr_minimum_size(raw_qty, instrument):
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
