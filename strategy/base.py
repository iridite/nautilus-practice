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


class DataDependency:
    """
    数据依赖声明类

    用于声明策略所需的数据类型和参数
    """

    def __init__(
        self,
        data_type: str,
        required: bool = True,
        period: Optional[str] = None,
        exchange: Optional[str] = None,
        symbols: Optional[List[str]] = None,
        auto_fetch: bool = True
    ):
        """
        初始化数据依赖

        Parameters
        ----------
        data_type : str
            数据类型（"ohlcv", "oi", "funding"）
        required : bool, optional
            是否为必需数据，默认 True
        period : str, optional
            数据周期（如 "1h", "4h"），默认 None
        exchange : str, optional
            交易所名称，默认 None（使用策略默认交易所）
        symbols : List[str], optional
            特定符号列表，默认 None（使用策略默认符号）
        auto_fetch : bool, optional
            是否自动获取缺失数据，默认 True
        """
        self.data_type = data_type
        self.required = required
        self.period = period
        self.exchange = exchange
        self.symbols = symbols
        self.auto_fetch = auto_fetch

    def __repr__(self) -> str:
        return (
            f"DataDependency("
            f"type={self.data_type}, "
            f"required={self.required}, "
            f"period={self.period}, "
            f"exchange={self.exchange}, "
            f"auto_fetch={self.auto_fetch})"
        )


class BaseStrategyConfig(StrategyConfig):  # pyright: ignore[reportGeneralTypeIssues]
    """
    Base configuration for strategies, including common risk management and position sizing parameters.

    Provides unified interface for position sizing, risk management, and data dependencies.
    """

    oms_type: str = "NETTING"

    instrument_id: str = ""

    data_dependencies: list = []

    # --- Position Sizing Parameters ---
    # 1. Fixed Quantity Mode: DEPRECATED - 已废弃，不再支持
    # 使用此参数将抛出错误，请改用 qty_percent 或 use_atr_position_sizing
    trade_size: Optional[float] = None

    # 2. Dynamic Percentage Mode: 动态百分比模式
    # Logic: Qty = (Equity * qty_percent * leverage) / Price
    qty_percent: Optional[Decimal] = None  # e.g., 0.1 for 10% of equity

    # 3. ATR Risk Mode: ATR风险模式（优先级高于动态百分比）
    # 启用后需要在 calculate_order_qty 中传入 atr_value 参数
    # Logic: Qty = (Equity * max_position_risk_pct) / (ATR * atr_stop_multiplier)
    use_atr_position_sizing: bool = False  # 启用ATR仓位计算

    # Leverage (Default: 1)
    # Applied in Dynamic Percentage Mode and ATR Mode.
    leverage: int = 1

    # --- Risk Management ---
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

    # --- Data Dependencies ---
    # 数据依赖声明列表，用于自动检查和获取所需数据
    data_dependencies: List[DataDependency] = []

    # 是否启用自动数据检查和获取
    enable_auto_data_fetch: bool = True

    # 数据获取的默认交易所（如果依赖中未指定）
    default_data_exchange: Optional[str] = None

    # 数据获取的默认周期（如果依赖中未指定）
    default_data_period: str = "1h"

    def add_data_dependency(
        self,
        data_type: str,
        required: bool = True,
        period: Optional[str] = None,
        exchange: Optional[str] = None,
        symbols: Optional[List[str]] = None,
        auto_fetch: bool = True
    ) -> None:
        """
        添加数据依赖

        Parameters
        ----------
        data_type : str
            数据类型（"ohlcv", "oi", "funding"）
        required : bool, optional
            是否为必需数据，默认 True
        period : str, optional
            数据周期，默认使用 default_data_period
        exchange : str, optional
            交易所名称，默认使用 default_data_exchange
        symbols : List[str], optional
            特定符号列表，默认 None
        auto_fetch : bool, optional
            是否自动获取缺失数据，默认 True
        """
        dependency = DataDependency(
            data_type=data_type,
            required=required,
            period=period or self.default_data_period,
            exchange=exchange or self.default_data_exchange,
            symbols=symbols,
            auto_fetch=auto_fetch
        )
        self.data_dependencies.append(dependency)

    def get_required_dependencies(self) -> List[DataDependency]:
        """获取所有必需的数据依赖"""
        return [dep for dep in self.data_dependencies if dep.required]

    def get_optional_dependencies(self) -> List[DataDependency]:
        """获取所有可选的数据依赖"""
        return [dep for dep in self.data_dependencies if not dep.required]

    def has_oi_dependency(self) -> bool:
        """检查是否有 OI 数据依赖"""
        return any(dep.data_type == "oi" for dep in self.data_dependencies)

    def has_funding_dependency(self) -> bool:
        """检查是否有 Funding Rate 数据依赖"""
        return any(dep.data_type == "funding" for dep in self.data_dependencies)

    def get_dependency_by_type(self, data_type: str) -> List[DataDependency]:
        """根据数据类型获取依赖"""
        return [dep for dep in self.data_dependencies if dep.data_type == data_type]


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

        # 检查数据依赖
        self._check_data_dependencies()

    def _check_data_dependencies(self):
        """
        检查策略的数据依赖是否满足

        这个方法会在策略启动时调用，检查所有必需的数据依赖。
        如果有缺失的必需数据，会记录错误日志。
        """
        if not hasattr(self.base_config, 'data_dependencies') or not self.base_config.data_dependencies:
            return

        required_deps = self.base_config.get_required_dependencies()
        if not required_deps:
            return

        self.log.info(f"BaseStrategy: Checking {len(required_deps)} required data dependencies...")

        missing_deps = []
        for dep in required_deps:
            if not self._is_dependency_satisfied(dep):
                missing_deps.append(dep)

        if missing_deps:
            self.log.error(
                f"BaseStrategy: Missing required data dependencies: "
                f"{[dep.data_type for dep in missing_deps]}"
            )
            for dep in missing_deps:
                self.log.error(f"  - {dep}")
        else:
            self.log.info("BaseStrategy: All required data dependencies satisfied.")

    def _is_dependency_satisfied(self, dependency: DataDependency) -> bool:
        """
        检查单个数据依赖是否满足

        Parameters
        ----------
        dependency : DataDependency
            要检查的数据依赖

        Returns
        -------
        bool
            依赖是否满足
        """
        # 这里可以添加实际的数据文件检查逻辑
        # 目前返回 True 作为占位符，实际实现会在 main.py 中进行
        return True

    def get_data_requirements(self) -> dict:
        """
        获取策略的数据需求摘要

        Returns
        -------
        dict
            包含数据需求信息的字典
        """
        if not hasattr(self.base_config, 'data_dependencies'):
            return {}

        requirements = {
            "total_dependencies": len(self.base_config.data_dependencies),
            "required_dependencies": len(self.base_config.get_required_dependencies()),
            "optional_dependencies": len(self.base_config.get_optional_dependencies()),
            "has_oi_dependency": self.base_config.has_oi_dependency(),
            "has_funding_dependency": self.base_config.has_funding_dependency(),
            "auto_fetch_enabled": getattr(self.base_config, 'enable_auto_data_fetch', True),
            "dependencies": [
                {
                    "type": dep.data_type,
                    "required": dep.required,
                    "period": dep.period,
                    "exchange": dep.exchange,
                    "auto_fetch": dep.auto_fetch
                }
                for dep in self.base_config.data_dependencies
            ]
        }

        return requirements

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
            leverage = max(1, self.base_config.leverage)
            if hasattr(instrument, "max_leverage") and instrument.max_leverage:
                leverage = min(leverage, instrument.max_leverage)
            raw_qty = raw_qty * Decimal(str(leverage))

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
