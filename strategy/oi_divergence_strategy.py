"""
OI Divergence Strategy - Risk-Enhanced Production Version
OI 背离策略 - 风控增强生产版

Version 3.0 - Risk Team Enhancements:
    ✅ ATR-based Dynamic Stop Loss
    ✅ ATR-based Dynamic Position Sizing
    ✅ Slippage Monitoring in on_order_filled
    ✅ Enhanced Risk Management

Architecture:
    - Research: Signal logic and mathematical models
    - Data: Data loading and validation
    - Risk: Advanced risk management (this version)
    - QuantDev: Strategy core logic

Author: Risk Team + QuantDev Team
Date: 2025-01-21
Version: 3.0
"""

from collections import deque
from decimal import Decimal
from enum import Enum
from typing import Deque, Optional

from nautilus_trader.indicators import AverageTrueRange, SimpleMovingAverage
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import InstrumentId

from strategy.base import BaseStrategy, BaseStrategyConfig
from utils.custom_data import FundingRateData, OpenInterestData
from utils.data_validator import FundingRateValidator, OIValidator
from utils.signal_stale_guard import SignalStaleGuard
from utils.slippage_monitor import SlippageMonitor

# ============================================================================
# Constants
# ============================================================================

# 日志格式常量
LOG_SEPARATOR_SHORT = "=" * 60
LOG_SEPARATOR_LONG = "=" * 70
LOG_WARNING_MARKER = "⚠️ " * 30

# 数据验证阈值
DEFAULT_OI_SPIKE_THRESHOLD = 0.5  # 50% OI 变化视为异常
DEFAULT_FUNDING_SPIKE_THRESHOLD = 2.0  # 200% 年化费率变化视为异常
MAX_FUNDING_RATE_ABS = 500.0  # ±500% 年化费率视为异常

# ============================================================================
# Risk-Enhanced Configuration
# ============================================================================


class OIDivergenceStrategyConfig(BaseStrategyConfig):
    """
    OI Divergence 策略配置 - 风控增强版

    新增 Risk Team 参数：
    - ATR 止损相关
    - 动态仓位管理相关
    - 滑点控制相关
    """

    # === 数据设定 (Data Settings) ===
    bar_type: str = ""  # 主执行周期
    trend_bar_type: str = ""  # 趋势判断周期（可选）

    # === 区间计算参数 (Range Calculation) ===
    lookback_bars: int = 48  # 阻力/支撑回溯周期

    # === OI 背离检测参数 (OI Divergence Detection) ===
    oi_lookback: int = 12  # OI 移动平均周期
    oi_decline_threshold: float = 0.05  # OI 下降阈值（5%）

    # === 资金费率过滤参数 (Funding Rate Filter) ===
    funding_rate_threshold_annual: float = 30.0  # 年化资金费率阈值
    use_funding_filter: bool = True

    # === 入场逻辑参数 (Entry Logic) ===
    breakout_reentry_pct: float = 0.002  # 回撤进入阈值（0.2%）

    # === 出场逻辑参数 (Exit Logic) ===
    tp_use_vwap: bool = True  # 止盈目标：VWAP
    vwap_period: int = 48



    # === 时间止损 ===
    time_stop_bars: int = 24  # 时间止损：24 根 K 线

    # === 状态控制 ===
    max_positions: int = 1

    # === 信号强度权重 ===
    signal_weight_breakout: float = 0.3
    signal_weight_oi: float = 0.4
    signal_weight_funding: float = 0.3



    # === 🔥 Risk-Enhanced: 信号钝化保护 ===
    enable_divergence_stale_check: bool = True  # 启用背离钝化检测
    divergence_stale_bars: int = 12  # 背离持续超过 N 根 K 线视为钝化
    stale_action: str = "tighten_stop"  # 钝化处理：tighten_stop/close/reduce
    stale_stop_multiplier: float = 1.0  # 钝化后止损收紧倍数（1.0× ATR）

    # === 调试与日志 ===
    enable_signal_logging: bool = True
    enable_quality_check: bool = True




# ============================================================================
# Strategy State Machine (Unchanged)
# ============================================================================


class StrategyState(Enum):
    """策略状态机"""

    IDLE = "IDLE"
    BREAKOUT_DETECTED = "BREAKOUT_DETECTED"
    WAITING_REENTRY = "WAITING_REENTRY"
    POSITION_OPEN = "POSITION_OPEN"


class BreakoutType(Enum):
    """突破类型"""

    NONE = "NONE"
    UP = "UP"
    DOWN = "DOWN"


# ============================================================================
# Risk-Enhanced Main Strategy Implementation
# ============================================================================


class OIDivergenceStrategy(BaseStrategy):
    """
    OI Divergence 策略 - 风控增强版

    🔥 Risk Team Enhancements:
    1. ATR 动态止损：根据市场波动率调整止损距离
    2. ATR 动态仓位：根据波动率调整仓位大小
    3. 滑点监控：on_order_filled 中检测异常滑点
    4. 增强风控日志：详细记录风控决策过程
    """

    def __init__(self, config: OIDivergenceStrategyConfig):
        super().__init__(config)
        # config is already set by parent class, no need to reassign

        # === 解析 Instrument 和 BarType ===
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

        # === 🔥 Risk-Enhanced: ATR 指标 ===
        self.atr = AverageTrueRange(config.atr_period) if config.use_atr_stop else None

        # === 原有指标 ===
        self.vwap_sma = SimpleMovingAverage(config.vwap_period)

        # === 数据缓存 ===
        self.bars_main: Deque[Bar] = deque(maxlen=config.lookback_bars + 10)
        self.bars_trend: Optional[Deque[Bar]] = deque(maxlen=50) if self.trend_bar_type else None
        self.oi_history: Deque[dict] = deque(maxlen=config.oi_lookback + 10)
        self.funding_history: Deque[dict] = deque(maxlen=10)

        # === 🔥 Performance: OI baseline 缓存 ===
        self._oi_baseline_cache: Optional[Decimal] = None
        self._oi_sum: Decimal = Decimal("0")
        self._oi_count: int = 0

        # === 🔥 Risk: 通用工具模块 ===
        self.oi_validator = OIValidator(
            spike_threshold=DEFAULT_OI_SPIKE_THRESHOLD, enable_logging=True
        )
        self.funding_validator = FundingRateValidator(
            max_abs_value=MAX_FUNDING_RATE_ABS,
            spike_threshold=DEFAULT_FUNDING_SPIKE_THRESHOLD * 100,
            enable_logging=True,
        )
        self.slippage_monitor = SlippageMonitor(
            max_slippage_pct=config.max_slippage_pct,
            enable_alert=config.enable_slippage_alert,
            enable_logging=config.enable_signal_logging,
        )
        self.signal_stale_guard = SignalStaleGuard(
            stale_bars=config.divergence_stale_bars,
            stale_action=config.stale_action,
            stale_stop_multiplier=config.stale_stop_multiplier,
        )

        # === 关键价位 ===
        self.resistance: Optional[Decimal] = None
        self.support: Optional[Decimal] = None
        self.midpoint: Optional[Decimal] = None

        # === 当前市场状态 ===
        self.current_oi: Optional[Decimal] = None
        self.current_funding_rate_annual: Optional[Decimal] = None

        # === 策略状态 ===
        self._strategy_state: StrategyState = StrategyState.IDLE
        self.breakout_type: BreakoutType = BreakoutType.NONE
        self.breakout_price: Optional[Decimal] = None
        self.breakout_bar: Optional[Bar] = None

        # === 持仓管理 ===
        self.entry_bar_count: int = 0
        self.entry_price: Optional[Decimal] = None

        # === 🔥 Risk-Enhanced: 止损订单追踪 ===
        self._stop_loss_submitted_order_ids: set = set()

        # === 日志控制 ===
        self._last_warmup_log_bars: int = 0
        self._signal_counter: int = 0

    # ========================================================================
    # Lifecycle Methods
    # ========================================================================

    def on_start(self):
        """策略启动"""
        super().on_start()

        if self.instrument is None:
            self.instrument = self.cache.instrument(self.instrument_id)
            if self.instrument is None:
                self.log.error(f"❌ Could not find instrument: {self.instrument_id}")
                self.stop()
                return

        # 订阅数据
        self.subscribe_bars(self.bar_type)
        self.log.info(f"📊 Subscribed to main bar type: {self.bar_type}")

        if self.trend_bar_type:
            self.subscribe_bars(self.trend_bar_type)
            self.log.info(f"📊 Subscribed to trend bar type: {self.trend_bar_type}")

        # 订阅自定义数据（OI 和 Funding Rate）
        # 使用 DataType 包装自定义数据类
        from nautilus_trader.model.data import DataType

        oi_data_type = DataType(OpenInterestData)
        funding_data_type = DataType(FundingRateData)

        self.subscribe_data(oi_data_type, instrument_id=self.instrument_id)
        self.subscribe_data(funding_data_type, instrument_id=self.instrument_id)
        self.log.info("📡 Subscribed to custom data: OpenInterestData, FundingRateData")

        # 🔥 风控增强日志
        self.log.info(
            f"\n{LOG_SEPARATOR_LONG}\n"
            f"🚀 OI Divergence Strategy Started (RISK-ENHANCED v3.0)\n"
            f"{LOG_SEPARATOR_LONG}\n"
            f"Instrument: {self.instrument_id}\n"
            f"Bar Type: {self.bar_type}\n"
            f"\n--- 🔥 Risk Enhancements ---\n"
            f"ATR Stop Loss: {'✅ ENABLED' if self.config.use_atr_stop else '❌ DISABLED'}\n"
            f"  - ATR Period: {self.config.atr_period}\n"
            f"  - ATR Multiplier: {self.config.atr_stop_multiplier}x\n"
            f"ATR Position Sizing: {'✅ ENABLED' if self.config.use_atr_position_sizing else '❌ DISABLED'}\n"
            f"  - Volatility Target: {self.config.atr_volatility_target:.2%}\n"
            f"  - Max Position Risk: {self.config.max_position_risk_pct:.1%}\n"
            f"Slippage Control: {'✅ ENABLED' if self.config.enable_slippage_alert else '❌ DISABLED'}\n"
            f"  - Max Slippage: {self.config.max_slippage_pct:.2%}\n"
            f"\n--- Research Parameters (Unchanged) ---\n"
            f"Lookback Bars: {self.config.lookback_bars}\n"
            f"OI Decline Threshold: {self.config.oi_decline_threshold:.1%}\n"
            f"Funding Threshold: {self.config.funding_rate_threshold_annual:.1f}%\n"
            f"{LOG_SEPARATOR_LONG}"
        )

    def on_data(self, data):
        """处理自定义数据"""
        if isinstance(data, OpenInterestData):
            self._handle_oi_data(data)
        elif isinstance(data, FundingRateData):
            self._handle_funding_data(data)

    def on_bar(self, bar: Bar):
        """处理新的 Bar 数据"""
        super().on_bar(bar)

        # 只处理主周期 Bar
        if bar.bar_type != self.bar_type:
            if self.trend_bar_type and bar.bar_type == self.trend_bar_type:
                if self.bars_trend is not None:
                    self.bars_trend.append(bar)
            return

        # 更新缓存
        self.bars_main.append(bar)

        # 更新指标
        self.vwap_sma.handle_bar(bar)
        if self.atr:
            self.atr.handle_bar(bar)

        # 热身检查
        if not self._is_ready():
            self._log_warmup_status()
            return

        # 更新关键价位
        self._update_key_levels()

        # 获取持仓
        positions = self.cache.positions_open(instrument_id=self.instrument_id)

        if positions:
            # 🔥 Risk: 检查 ATR 止损
            if self.config.use_atr_stop:
                self._check_atr_stop_loss(bar, positions)

            # 检查出场信号
            self._check_exit_signals(bar, positions)
        else:
            # 检查入场信号
            self._check_entry_signals(bar)

    # ========================================================================
    # 🔥 Risk-Enhanced: Order Filled Event Handler (Slippage Monitoring)
    # ========================================================================

    def on_order_filled(self, event: OrderFilled):
        """
        订单成交事件处理

        🔥 Risk Enhancement: 滑点监控
        - 检测实际成交价与预期价格的偏离
        - 如果滑点超过阈值，记录警告并可能触发防御措施

        🔥 Risk Enhancement: 真实止损订单提交
        - 使用实际成交价提交止损单，而非信号触发价
        - 确保止损订单在入场成交后立即挂出
        - 防止部分成交时重复提交止损单
        """
        super().on_order_filled(event)

        # 只监控入场订单（市价单）
        if event.order_side in (OrderSide.BUY, OrderSide.SELL):
            # 🔥 Risk: 使用工具模块监控滑点
            self.slippage_monitor.check_slippage(event, self.log)

            # 更新入场价格（使用真实成交价）
            if event.order_side == OrderSide.BUY:
                self.entry_price = Decimal(str(event.last_px))
                self.log.info(f"✅ LONG Entry Filled @ {event.last_px}")
            elif event.order_side == OrderSide.SELL:
                self.entry_price = Decimal(str(event.last_px))
                self.log.info(f"✅ SHORT Entry Filled @ {event.last_px}")

            # 🔥 Risk: 使用真实成交价提交止损订单
            if event.client_order_id not in self._stop_loss_submitted_order_ids:
                self._submit_stop_loss_order(event.order_side, event.last_qty)
                self._stop_loss_submitted_order_ids.add(event.client_order_id)
                self.log.info(f"🔥 Stop Loss order submitted for {event.client_order_id}")



    # ========================================================================
    # 🔥 Risk-Enhanced: ATR Dynamic Stop Loss
    # ========================================================================

    def _get_atr_stop_price(
        self, entry_price: Decimal, order_side: OrderSide
    ) -> Optional[Decimal]:
        """
        计算 ATR 止损价格

        Parameters
        ----------
        entry_price : Decimal
            入场价格
        order_side : OrderSide
            订单方向

        Returns
        -------
        Optional[Decimal]
            止损触发价格，如果 ATR 未初始化则返回 None
        """
        if not self.atr or not self.atr.initialized or self.atr.value is None:
            return None

        atr_value = Decimal(str(self.atr.value))
        stop_distance = atr_value * Decimal(str(self.config.atr_stop_multiplier))

        if order_side == OrderSide.SELL:
            # 做空：止损在入场价上方（买入平仓）
            return entry_price + stop_distance
        else:
            # 做多：止损在入场价下方（卖出平仓）
            return entry_price - stop_distance

    def _submit_stop_loss_order(self, order_side: OrderSide, quantity):
        """
        提交止损订单（真实订单保证执行）

        根据配置选择：
        1. ATR 动态止损（优先）
        2. 固定百分比止损（后备）

        Parameters
        ----------
        order_side : OrderSide
            入场订单方向（用于判断持仓方向）
        quantity : Quantity
            订单数量
        """
        if self.entry_price is None:
            return

        # 获取止损价格
        atr_stop_price = self._get_atr_stop_price(self.entry_price, order_side)

        if self.config.use_atr_stop and atr_stop_price is not None:
            # ATR 动态止损
            trigger_price = self.instrument.make_price(atr_stop_price)
            opposite_side = (
                OrderSide.BUY if order_side == OrderSide.SELL else OrderSide.SELL
            )

            sl_order = self.order_factory.stop_market(
                instrument_id=self.instrument_id,
                order_side=opposite_side,
                quantity=quantity,
                trigger_price=trigger_price,
                time_in_force=TimeInForce.FOK,  # ✅ 立即成交或取消
                reduce_only=True,  # ✅ 防止加仓，只减少持仓
            )

            self.submit_order_safe(
                sl_order,
                reason=f"ATR Dynamic Stop Loss ({self.config.atr_stop_multiplier}× ATR) @ {atr_stop_price:.2f}",
            )

            if self.config.enable_signal_logging and self.atr:
                self.log.info(
                    f"🔥 ATR Stop Loss Order Submitted: {opposite_side.name} @ {atr_stop_price:.2f} "
                    f"(ATR: {self.atr.value:.2f}, Multiplier: {self.config.atr_stop_multiplier}x)"
                )

        elif self.config.stop_loss_pct is not None:
            # 固定百分比止损（后备方案）
            if order_side == OrderSide.SELL:
                sl_price = self.entry_price * (
                    Decimal("1") + Decimal(str(self.config.stop_loss_pct))
                )
            else:
                sl_price = self.entry_price * (
                    Decimal("1") - Decimal(str(self.config.stop_loss_pct))
                )

            trigger_price = self.instrument.make_price(sl_price)
            opposite_side = (
                OrderSide.BUY if order_side == OrderSide.SELL else OrderSide.SELL
            )

            sl_order = self.order_factory.stop_market(
                instrument_id=self.instrument_id,
                order_side=opposite_side,
                quantity=quantity,
                trigger_price=trigger_price,
                time_in_force=TimeInForce.GTC,
                reduce_only=True,  # ✅ 防止加仓，只减少持仓
            )

            self.submit_order_safe(
                sl_order,
                reason=f"Fixed Stop Loss ({self.config.stop_loss_pct:.2%}) @ {trigger_price}",
            )

    def _check_atr_stop_loss(self, bar: Bar, positions):
        """
        检查 ATR 动态止损（最后防线）

        注意：正常情况下止损订单应该在开仓时已提交。
        此方法作为最后防线，用于处理：
        1. 止损订单未被正确提交的情况
        2. 价格跳空穿过止损订单的情况

        Parameters
        ----------
        bar : Bar
            当前 Bar
        positions : list
            持仓列表
        """
        if not self.atr or not self.atr.initialized:
            return

        current_price = Decimal(str(bar.close))
        atr_value = Decimal(str(self.atr.value))
        stop_distance = atr_value * Decimal(str(self.config.atr_stop_multiplier))

        for pos in positions:
            if self.entry_price is None:
                continue

            # 计算 ATR 止损价位
            if pos.is_long:
                # 做多：止损在入场价下方
                atr_stop_price = self.entry_price - stop_distance
                is_hit = current_price <= atr_stop_price
            else:
                # 做空：止损在入场价上方
                atr_stop_price = self.entry_price + stop_distance
                is_hit = current_price >= atr_stop_price

            if is_hit:
                pnl_pct = float((current_price - self.entry_price) / self.entry_price)
                if pos.is_short:
                    pnl_pct = -pnl_pct

                self.log.warning(
                    f"\n{LOG_SEPARATOR_SHORT}\n"
                    f"🛑 ATR STOP LOSS TRIGGERED (Last Resort)\n"
                    f"{LOG_SEPARATOR_SHORT}\n"
                    f"Position: {pos.side.name}\n"
                    f"Entry Price: {self.entry_price:.2f}\n"
                    f"Current Price: {current_price:.2f}\n"
                    f"ATR Value: {atr_value:.2f}\n"
                    f"Stop Distance: {stop_distance:.2f} ({self.config.atr_stop_multiplier}× ATR)\n"
                    f"ATR Stop Price: {atr_stop_price:.2f}\n"
                    f"P&L: {pnl_pct:.2%}\n"
                    f"⚠️  WARNING: Price gap detected or stop order failed!\n"
                    f"{LOG_SEPARATOR_SHORT}"
                )

                self.close_position(pos)
                self.cancel_all_orders(self.instrument_id)
                self.entry_bar_count = 0
                self.entry_price = None
                self._strategy_state = StrategyState.IDLE
                return

    # ========================================================================
    # 🔥 Risk-Enhanced: ATR Dynamic Position Sizing
    # ========================================================================



    def _calculate_atr_adjusted_qty(
        self, current_price: Decimal, order_side: OrderSide
    ) -> float:
        """
        基于 ATR 的动态仓位计算

        Parameters
        ----------
        current_price : Decimal
            当前价格
        order_side : OrderSide
            订单方向

        Returns
        -------
        float
            调整后的下单数量
        """
        if (
            not self.config.use_atr_position_sizing
            or not self.atr
            or not self.atr.initialized
        ):
            return float(self.calculate_order_qty(current_price))

        equity = self._get_account_equity()
        if equity is None:
            return float(self.calculate_order_qty(current_price))

        atr_value = Decimal(str(self.atr.value))
        stop_distance = atr_value * Decimal(str(self.config.atr_stop_multiplier))

        if stop_distance == 0:
            self.log.warning("⚠️  ATR stop distance is zero, using default qty")
            return float(self.calculate_order_qty(current_price))

        target_qty = self._calculate_position_size_from_risk(equity, atr_value)

        if self.config.enable_signal_logging:
            max_risk = equity * Decimal(str(self.config.max_position_risk_pct))
            self.log.info(
                f"\n--- 🔥 ATR Position Sizing ---\n"
                f"Equity: {equity:.2f}\n"
                f"Max Risk: {max_risk:.2f} ({self.config.max_position_risk_pct:.1%})\n"
                f"ATR Value: {atr_value:.4f}\n"
                f"Stop Distance: {stop_distance:.4f} ({self.config.atr_stop_multiplier}× ATR)\n"
                f"Target Qty: {target_qty:.8f}\n"
                f"----------------------------"
            )

        return float(target_qty)

    # ========================================================================
    # Custom Data Handlers (Unchanged)
    # ========================================================================

    def _handle_oi_data(self, data: OpenInterestData):
        """处理 Open Interest 数据"""
        if data.instrument_id != self.instrument_id:
            return

        # 🔥 Risk: 使用工具模块验证 OI 数据
        is_valid, error_msg = self.oi_validator.validate(data.open_interest, self.log)
        if not is_valid:
            return

        # 数据通过验证，更新状态
        self.current_oi = data.open_interest
        self.oi_history.append(
            {
                "ts": data.ts_event,
                "oi": data.open_interest,
                "data": data,
            }
        )

        # 🔥 Performance: 增量更新 OI baseline 缓存
        if len(self.oi_history) >= self.config.oi_lookback:
            # 添加新值
            self._oi_sum += data.open_interest
            self._oi_count += 1

            # 如果超过窗口大小，移除最旧的值
            if self._oi_count > self.config.oi_lookback:
                oldest_idx = len(self.oi_history) - self.config.oi_lookback - 1
                if oldest_idx >= 0:
                    oldest_oi = list(self.oi_history)[oldest_idx]["oi"]
                    self._oi_sum -= oldest_oi
                    self._oi_count -= 1

            # 更新缓存
            self._oi_baseline_cache = self._oi_sum / Decimal(str(self._oi_count))

        if self.config.enable_signal_logging and len(self.oi_history) % 24 == 0:
            oi_baseline = self._calculate_oi_baseline()
            oi_divergence = self._calculate_oi_divergence() if oi_baseline > 0 else None
            self.log.debug(
                f"📊 OI Update | Current: {self.current_oi:.0f}, "
                f"Baseline: {oi_baseline:.0f}, "
                f"Divergence: {oi_divergence:.2%}"
                if oi_divergence
                else "N/A"
            )

    def _handle_funding_data(self, data: FundingRateData):
        """处理 Funding Rate 数据"""
        if data.instrument_id != self.instrument_id:
            return

        # 🔥 Risk: 使用工具模块验证 Funding Rate 数据
        is_valid, error_msg = self.funding_validator.validate(
            data.funding_rate_annual, self.log
        )
        if not is_valid:
            return

        # 数据通过验证，更新状态
        self.current_funding_rate_annual = data.funding_rate_annual
        self.funding_history.append(
            {
                "ts": data.ts_event,
                "rate": data.funding_rate,
                "annual": data.funding_rate_annual,
                "data": data,
            }
        )

        if self.config.enable_signal_logging:
            sentiment = self._classify_funding_sentiment(data.funding_rate_annual)
            self.log.debug(
                f"💰 Funding Update | Rate: {data.funding_rate:.4f}, "
                f"Annual: {data.funding_rate_annual:.2f}%, "
                f"Sentiment: {sentiment}"
            )

    # ========================================================================
    # Research Alpha Implementation - Entry Signals (Unchanged)
    # ========================================================================

    def _check_entry_signals(self, bar: Bar):
        """检查入场信号"""
        if self.resistance is None or self.support is None:
            return

        current_price = Decimal(str(bar.close))
        current_high = Decimal(str(bar.high))
        current_low = Decimal(str(bar.low))

        # 检测做空信号
        short_signal, short_details = self._detect_short_signal(
            bar, current_price, current_high
        )

        if short_signal:
            self._execute_short_entry(bar, current_price, short_details)
            return

        # 检测做多信号
        long_signal, long_details = self._detect_long_signal(
            bar, current_price, current_low
        )

        if long_signal:
            self._execute_long_entry(bar, current_price, long_details)
            return

    def _detect_short_signal(
        self, bar: Bar, current_price: Decimal, current_high: Decimal
    ) -> tuple[bool, dict]:
        """检测做空信号"""
        details = {
            "type": "SHORT",
            "cond1_breakout": False,
            "cond2_oi_divergence": False,
            "cond3_funding": False,
            "cond4_reentry": False,
            "signal_strength": 0.0,
        }

        # Condition 1: 突破阻力位
        if self.resistance is None or current_high <= self.resistance:
            return False, details

        details["cond1_breakout"] = True
        details["breakout_price"] = float(current_high)
        details["resistance"] = float(self.resistance)

        # Condition 2: OI 背离
        oi_divergence = self._calculate_oi_divergence()
        if oi_divergence is None or oi_divergence >= -self.config.oi_decline_threshold:
            if self.config.enable_signal_logging:
                self.log.debug(
                    f"⚠️  SHORT signal blocked by OI: divergence={oi_divergence:.2%}"
                )
            return False, details

        details["cond2_oi_divergence"] = True
        details["oi_divergence"] = float(oi_divergence)

        # Condition 3: 资金费率过滤
        if self.config.use_funding_filter:
            if (
                self.current_funding_rate_annual is None
                or self.current_funding_rate_annual
                <= self.config.funding_rate_threshold_annual
            ):
                if self.config.enable_signal_logging:
                    self.log.debug(
                        f"⚠️  SHORT signal blocked by Funding Rate: "
                        f"{self.current_funding_rate_annual:.2f}%"
                    )
                return False, details

        details["cond3_funding"] = True
        details["funding_rate_annual"] = (
            float(self.current_funding_rate_annual)
            if self.current_funding_rate_annual
            else None
        )

        # Condition 4: 回撤进入
        reentry_threshold = self.resistance * (
            Decimal("1") - Decimal(str(self.config.breakout_reentry_pct))
        )

        if current_price >= reentry_threshold:
            return False, details

        details["cond4_reentry"] = True
        details["reentry_threshold"] = float(reentry_threshold)

        # 计算信号强度
        signal_strength = self._calculate_signal_strength_short(
            current_high, oi_divergence
        )
        details["signal_strength"] = signal_strength

        return True, details

    def _detect_long_signal(
        self, bar: Bar, current_price: Decimal, current_low: Decimal
    ) -> tuple[bool, dict]:
        """检测做多信号"""
        details = {
            "type": "LONG",
            "cond1_breakout": False,
            "cond2_oi_divergence": False,
            "cond3_funding": False,
            "cond4_reentry": False,
            "signal_strength": 0.0,
        }

        # Condition 1: 突破支撑位
        if self.support is None or current_low >= self.support:
            return False, details

        details["cond1_breakout"] = True
        details["breakout_price"] = float(current_low)
        details["support"] = float(self.support)

        # Condition 2: OI 背离
        oi_divergence = self._calculate_oi_divergence()
        if oi_divergence is None or oi_divergence >= -self.config.oi_decline_threshold:
            if self.config.enable_signal_logging:
                self.log.debug(
                    f"⚠️  LONG signal blocked by OI: divergence={oi_divergence:.2%}"
                )
            return False, details

        details["cond2_oi_divergence"] = True
        details["oi_divergence"] = float(oi_divergence)

        # Condition 3: 资金费率过滤
        if self.config.use_funding_filter:
            if (
                self.current_funding_rate_annual is None
                or self.current_funding_rate_annual
                >= -self.config.funding_rate_threshold_annual
            ):
                if self.config.enable_signal_logging:
                    self.log.debug(
                        f"⚠️  LONG signal blocked by Funding Rate: "
                        f"{self.current_funding_rate_annual:.2f}%"
                    )
                return False, details

        details["cond3_funding"] = True
        details["funding_rate_annual"] = (
            float(self.current_funding_rate_annual)
            if self.current_funding_rate_annual
            else None
        )

        # Condition 4: 反弹进入
        reentry_threshold = self.support * (
            Decimal("1") + Decimal(str(self.config.breakout_reentry_pct))
        )

        if current_price <= reentry_threshold:
            return False, details

        details["cond4_reentry"] = True
        details["reentry_threshold"] = float(reentry_threshold)

        # 计算信号强度
        signal_strength = self._calculate_signal_strength_long(
            current_low, oi_divergence
        )
        details["signal_strength"] = signal_strength

        return True, details

    # ========================================================================
    # Research Alpha Implementation - Exit Signals (Enhanced)
    # ========================================================================

    def _check_exit_signals(self, bar: Bar, positions):
        """检查出场信号"""
        self.entry_bar_count += 1
        current_price = Decimal(str(bar.close))

        for pos in positions:
            # 🔥 Risk: 使用工具模块检查信号钝化保护
            if self.config.enable_divergence_stale_check:
                oi_divergence = self._calculate_oi_divergence()
                if oi_divergence is not None:
                    is_divergence_active = abs(float(oi_divergence)) >= self.config.oi_decline_threshold
                    is_stale, bars_count = self.signal_stale_guard.update(
                        self.entry_bar_count, is_divergence_active
                    )
                    if is_stale and self.entry_price is not None:
                        atr_value = Decimal(str(self.atr.value)) if self.atr and self.atr.initialized else None
                        closed = self.signal_stale_guard.handle_stale_protection(
                            self, pos, self.entry_price, atr_value, self.log
                        )
                        if closed:
                            self.entry_bar_count = 0
                            self.entry_price = None
                            self._strategy_state = StrategyState.IDLE
                            return

            # 止盈
            if self._check_take_profit(pos, current_price):
                tp_target = self._get_tp_target(pos)
                self.log.info(
                    f"\n{LOG_SEPARATOR_SHORT}\n"
                    f"✅ TAKE PROFIT TRIGGERED\n"
                    f"{LOG_SEPARATOR_SHORT}\n"
                    f"Position: {pos.side.name}\n"
                    f"Current Price: {current_price:.2f}\n"
                    f"TP Target: {tp_target:.2f}\n"
                    f"Holding Time: {self.entry_bar_count} bars\n"
                    f"{LOG_SEPARATOR_SHORT}"
                )
                self.close_position(pos)
                self.cancel_all_orders(self.instrument_id)
                self.entry_bar_count = 0
                self.entry_price = None
                self._strategy_state = StrategyState.IDLE
                return

            # 时间止损
            if self.entry_bar_count >= self.config.time_stop_bars:
                self.log.info(
                    f"\n{LOG_SEPARATOR_SHORT}\n"
                    f"⏰ TIME STOP TRIGGERED\n"
                    f"{LOG_SEPARATOR_SHORT}\n"
                    f"Position: {pos.side.name}\n"
                    f"Holding Time: {self.entry_bar_count} bars\n"
                    f"Current Price: {current_price:.2f}\n"
                    f"{LOG_SEPARATOR_SHORT}"
                )
                self.close_position(pos)
                self.cancel_all_orders(self.instrument_id)
                self.entry_bar_count = 0
                self.entry_price = None
                self._strategy_state = StrategyState.IDLE
                return



    # ========================================================================
    # 🔥 Risk-Enhanced: Order Execution with ATR Position Sizing
    # ========================================================================

    def _execute_entry(
        self, order_side: OrderSide, current_price: Decimal, signal_details: dict
    ):
        """执行入场（带 ATR 仓位调整和真实止损订单）"""
        positions = self.cache.positions_open(instrument_id=self.instrument_id)
        if len(positions) >= self.config.max_positions:
            side_name = "SHORT" if order_side == OrderSide.SELL else "LONG"
            self.log.warning(
                f"⚠️  Max positions reached ({self.config.max_positions}), skipping {side_name} entry"
            )
            return

        # 🔥 Risk: 使用 ATR 动态仓位计算
        if self.config.use_atr_position_sizing and self.atr and self.atr.initialized:
            raw_qty = self._calculate_atr_adjusted_qty(current_price, order_side)
            qty = self.instrument.make_qty(raw_qty)
        else:
            qty = self.calculate_order_qty(current_price)

        if qty <= 0:
            self.log.error(f"❌ Invalid order quantity: {qty}, skipping entry")
            return

        # 创建市价单
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=order_side,
            quantity=qty,
        )

        # 🔥 Risk: 使用工具模块记录预期成交价
        self.slippage_monitor.set_expected_price(str(order.client_order_id), current_price)

        # 构建 reason
        if order_side == OrderSide.SELL:
            level_key = "resistance"
            level_value = signal_details.get("resistance", 0)
            comparison = "<"
            side_name = "SHORT"
            emoji = "🔻"
        else:
            level_key = "support"
            level_value = signal_details.get("support", 0)
            comparison = ">"
            side_name = "LONG"
            emoji = "🔺"

        reason = (
            f"OI Divergence {side_name} | "
            f"Signal Strength: {signal_details['signal_strength']:.2f} | "
            f"Price: {current_price:.2f} {comparison} {level_key.capitalize()}: {level_value:.2f} | "
            f"OI Divergence: {signal_details['oi_divergence']:.2%}"
        )

        self.submit_order_safe(order, reason=reason)

        # 更新状态
        self.entry_bar_count = 0
        self._strategy_state = StrategyState.POSITION_OPEN
        self._signal_counter += 1

        # 日志
        if self.config.enable_signal_logging:
            self.log.info(
                f"\n{LOG_SEPARATOR_LONG}\n"
                f"{emoji} {side_name} ENTRY EXECUTED (Signal #{self._signal_counter})\n"
                f"{LOG_SEPARATOR_LONG}\n"
                f"Entry Price: {current_price:.2f}\n"
                f"Quantity: {qty}\n"
                f"Stop Loss: {'ATR-based (dynamic)' if self.config.use_atr_stop else 'Fixed ' + str(self.config.stop_loss_pct)}\n"
                f"\n--- Signal Details ---\n"
                f"Breakout Price: {signal_details['breakout_price']:.2f}\n"
                f"{level_key.capitalize()}: {level_value:.2f}\n"
                f"OI Divergence: {signal_details['oi_divergence']:.2%}\n"
                f"Signal Strength: {signal_details['signal_strength']:.2f}\n"
                f"{LOG_SEPARATOR_LONG}"
            )

    def _execute_short_entry(
        self, bar: Bar, current_price: Decimal, signal_details: dict
    ):
        """执行做空入场（带 ATR 仓位调整和真实止损订单）"""
        self._execute_entry(OrderSide.SELL, current_price, signal_details)

    def _execute_long_entry(
        self, bar: Bar, current_price: Decimal, signal_details: dict
    ):
        """执行做多入场（带 ATR 仓位调整和真实止损订单）"""
        self._execute_entry(OrderSide.BUY, current_price, signal_details)

    # ========================================================================
    # Research Alpha Calculations (Unchanged)
    # ========================================================================

    def _calculate_oi_divergence(self) -> Optional[Decimal]:
        """计算 OI 背离指标"""
        if len(self.oi_history) < self.config.oi_lookback:
            return None

        if self.current_oi is None:
            return None

        oi_baseline = self._calculate_oi_baseline()

        if oi_baseline == 0:
            return None

        oi_divergence = (self.current_oi - oi_baseline) / oi_baseline

        return oi_divergence

    def _calculate_oi_baseline(self) -> Decimal:
        """计算 OI 基准值（使用缓存优化）"""
        if len(self.oi_history) < self.config.oi_lookback:
            return Decimal("0")

        # 🔥 Performance: 使用缓存值
        if self._oi_baseline_cache is not None:
            return self._oi_baseline_cache

        # 后备方案：重新计算（仅在缓存未初始化时）
        recent_oi = [
            item["oi"] for item in list(self.oi_history)[-self.config.oi_lookback :]
        ]

        if not recent_oi:
            return Decimal("0")

        return sum(recent_oi) / Decimal(str(len(recent_oi)))

    def _calculate_signal_strength_short(
        self, current_high: Decimal, oi_divergence: Decimal
    ) -> float:
        """计算做空信号强度"""
        if self.resistance is None or self.resistance == 0:
            breakout_score = 0.0
        else:
            breakout_score = float((current_high - self.resistance) / self.resistance)
        oi_score = -float(oi_divergence) / self.config.oi_decline_threshold

        if self.current_funding_rate_annual:
            import math

            funding_score = math.tanh(float(self.current_funding_rate_annual) / 50.0)
        else:
            funding_score = 0.0

        signal_strength = (
            self.config.signal_weight_breakout * breakout_score
            + self.config.signal_weight_oi * oi_score
            + self.config.signal_weight_funding * funding_score
        )

        return max(0.0, signal_strength)

    def _calculate_signal_strength_long(
        self, current_low: Decimal, oi_divergence: Decimal
    ) -> float:
        """计算做多信号强度"""
        if self.support is None or self.support == 0:
            breakout_score = 0.0
        else:
            breakout_score = float((self.support - current_low) / self.support)
        oi_score = -float(oi_divergence) / self.config.oi_decline_threshold

        if self.current_funding_rate_annual:
            import math

            funding_score = -math.tanh(float(self.current_funding_rate_annual) / 50.0)
        else:
            funding_score = 0.0

        signal_strength = (
            self.config.signal_weight_breakout * breakout_score
            + self.config.signal_weight_oi * oi_score
            + self.config.signal_weight_funding * funding_score
        )

        return max(0.0, signal_strength)

    def _update_key_levels(self):
        """更新关键价位"""
        if len(self.bars_main) < self.config.lookback_bars:
            return

        recent_bars = list(self.bars_main)[-self.config.lookback_bars :]

        highs = [Decimal(str(b.high)) for b in recent_bars]
        lows = [Decimal(str(b.low)) for b in recent_bars]

        self.resistance = max(highs)
        self.support = min(lows)
        self.midpoint = (self.resistance + self.support) / Decimal("2")

    def _check_take_profit(self, pos, current_price: Decimal) -> bool:
        """检查止盈"""
        tp_target = self._get_tp_target(pos)  # 传入持仓以正确计算止盈目标
        if tp_target is None:
            return False

        if pos.is_long and current_price >= tp_target:
            return True

        if pos.is_short and current_price <= tp_target:
            return True

        return False

    def _get_tp_target(self, pos) -> Optional[Decimal]:
        """
        获取止盈目标

        使用 ATR 动态止盈，根据持仓方向计算止盈距离
        - LONG: tp_price = entry_price + (ATR × tp_multiplier)
        - SHORT: tp_price = entry_price - (ATR × tp_multiplier)

        Parameters
        ----------
        pos : Position
            持仓对象，用于判断方向

        Returns
        -------
        Optional[Decimal]
            止盈目标价格
        """
        # 优先使用 ATR 动态止盈
        if self.entry_price is not None and self.atr and self.atr.initialized:
            atr_value = Decimal(str(self.atr.value))
            tp_multiplier = getattr(self.config, "atr_tp_multiplier", 3.0)
            tp_distance = atr_value * Decimal(str(tp_multiplier))

            if pos.is_long:
                return self.entry_price + tp_distance
            else:
                return self.entry_price - tp_distance

        # 后备方案：使用 VWAP 或 midpoint
        if self.config.tp_use_vwap and self.vwap_sma.initialized:
            return Decimal(str(self.vwap_sma.value))

        if self.midpoint is not None:
            return self.midpoint

        return None

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def _is_ready(self) -> bool:
        """检查策略是否准备就绪"""
        atr_ready = True
        if self.config.use_atr_stop and self.atr:
            atr_ready = self.atr.initialized

        return (
            len(self.bars_main) >= self.config.lookback_bars
            and self.vwap_sma.initialized
            and len(self.oi_history) >= self.config.oi_lookback
            and self.current_oi is not None
            and atr_ready
        )

    def _log_warmup_status(self):
        """记录热身状态"""
        total_bars = len(self.cache.bars(self.bar_type))
        if total_bars // 100 > self._last_warmup_log_bars:
            self._last_warmup_log_bars = total_bars // 100

            atr_status = "N/A"
            if self.config.use_atr_stop and self.atr:
                atr_status = "✅" if self.atr.initialized else "⏳"

            self.log.info(
                f"🔄 Indicators warming up... (Bars: {total_bars}) | "
                f"VWAP: {'✅' if self.vwap_sma.initialized else '⏳'} | "
                f"ATR: {atr_status} | "
                f"Range: {'✅' if self.resistance is not None else '⏳'} | "
                f"OI: {'✅' if len(self.oi_history) >= self.config.oi_lookback else '⏳'}"
            )

    def _classify_funding_sentiment(self, funding_rate_annual: Decimal) -> str:
        """分类资金费率情绪"""
        if funding_rate_annual > 50:
            return "Extreme Long Crowding"
        elif funding_rate_annual > 30:
            return "Long Crowding"
        elif funding_rate_annual > -30:
            return "Neutral"
        elif funding_rate_annual > -50:
            return "Short Crowding"
        else:
            return "Extreme Short Crowding"

    # ========================================================================
    # Lifecycle Cleanup
    # ========================================================================

    def on_stop(self):
        """策略停止"""
        self.cancel_all_orders(self.instrument_id)
        self.close_all_positions(self.instrument_id)
        self.log.info(
            f"\n{LOG_SEPARATOR_SHORT}\n"
            f"🛑 OI Divergence Strategy Stopped (v3.0 Risk-Enhanced)\n"
            f"Total Signals Generated: {self._signal_counter}\n"
            f"{LOG_SEPARATOR_SHORT}"
        )

    def on_reset(self):
        """策略重置"""
        super().on_reset()

        # 清除缓存
        self.bars_main.clear()
        if self.bars_trend:
            self.bars_trend.clear()
        self.oi_history.clear()
        self.funding_history.clear()

        # 🔥 Performance: 重置 OI baseline 缓存
        self._oi_baseline_cache = None
        self._oi_sum = Decimal("0")
        self._oi_count = 0

        # 🔥 Risk: 重置工具模块状态
        self.oi_validator.reset()
        self.funding_validator.reset()
        self.slippage_monitor.reset()
        self.signal_stale_guard.reset()

        # 重置价位
        self.resistance = None
        self.support = None
        self.midpoint = None

        # 重置市场状态
        self.current_oi = None
        self.current_funding_rate_annual = None

        # 重置策略状态
        self._strategy_state = StrategyState.IDLE
        self.breakout_type = BreakoutType.NONE
        self.breakout_price = None
        self.breakout_bar = None
        self.entry_bar_count = 0
        self.entry_price = None

        # 🔥 Risk: 重置滑点监控
        self.expected_entry_price = None
        self.actual_slippage_pct = None
        self._stop_loss_submitted_order_ids.clear()
        self._slippage_calculated_orders.clear()

        # 重置指标
        self.vwap_sma.reset()
        if self.atr:
            self.atr.reset()

        # 重置日志
        self._last_warmup_log_bars = 0
        self._signal_counter = 0
