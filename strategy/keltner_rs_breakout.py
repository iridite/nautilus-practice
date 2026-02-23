"""
Strategy: Keltner RS Breakout (KRB) - Refactored Version
Type: Medium-Frequency Trend Following

Core Logic:
  1. Entry: Close > EMA(20) + 2.25*ATR(20)
  2. Filter A (Market Regime): BTC > SMA(200) and BTC_ATR% < 3%
  3. Filter B (Macro): Close > SMA(200)
  4. Filter C (Alpha): Relative Strength (Symbol vs BTC) > 0
  5. Filter D (Momentum): Volume > 1.5 * SMA(Vol, 20)
  6. Sizing: Volatility Targeting (Base Risk 1.0%, Squeeze Risk 1.5%)
  7. Exit: Chandelier Exit (Highest - 2x ATR) + Time Stop (3 bars)

Two-Layer Filtering Mechanism:
  Layer 1 - Universe Selection:
    - Dynamically filters active coins based on trading volume
    - Updates periodically (Monthly/Weekly/Bi-weekly)
    - Ensures liquidity and data quality

  Layer 2 - Relative Strength (RS) Filtering:
    - Operates within the active Universe pool
    - Calculates weighted RS: 0.4 * RS(5d) + 0.6 * RS(20d)
    - Only trades coins with RS > 0 (outperforming BTC)
    - Ensures buying strong momentum coins in active pool

Note: This strategy implements the "Breathing Trend" philosophy using Static Keltner Channels
and dual-layer filtering (Universe → RS) to ensure trading reasonable targets.
"""

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from nautilus_trader.indicators import RelativeStrengthIndex
from nautilus_trader.model.data import Bar, BarType, CustomData, DataType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId

from strategy.core.base import BaseStrategy, BaseStrategyConfig
from strategy.common.indicators import (
    KeltnerChannel,
    RelativeStrengthCalculator,
    MarketRegimeFilter,
)
from strategy.common.signals import EntrySignalGenerator, ExitSignalGenerator, SqueezeDetector
from strategy.common.universe import DynamicUniverseManager
from utils import get_project_root
from utils.custom_data import FundingRateData
from config.constants import (
    DEFAULT_EMA_PERIOD,
    DEFAULT_SMA_PERIOD,
    DEFAULT_ATR_PERIOD_LONG,
    DEFAULT_BB_PERIOD,
    DEFAULT_BB_STD,
    DEFAULT_RSI_PERIOD,
    DEFAULT_KELTNER_BASE_MULTIPLIER,
    DEFAULT_KELTNER_TRIGGER_MULTIPLIER,
    DEFAULT_VOLUME_MULTIPLIER,
    RS_SHORT_PERIOD,
    RS_LONG_PERIOD,
    RS_SHORT_WEIGHT,
    RS_LONG_WEIGHT,
    RS_THRESHOLD,
    BASE_RISK_PCT,
    HIGH_CONVICTION_RISK_PCT,
    STOP_LOSS_ATR_MULTIPLIER,
    BREAKEVEN_MULTIPLIER,
    MIN_STOP_DISTANCE_PCT,
    TIME_STOP_BARS,
    MOMENTUM_THRESHOLD,
    DEVIATION_THRESHOLD,
    MAX_UPPER_WICK_RATIO,
    BTC_REGIME_SMA_PERIOD,
    BTC_REGIME_ATR_PERIOD,
    VOLATILITY_THRESHOLD,
    FUNDING_RATE_WARNING_ANNUAL,
    FUNDING_RATE_DANGER_ANNUAL,
    EUPHORIA_REDUCE_POSITION_PCT,
    SQUEEZE_MEMORY_DAYS,
    MAX_HISTORY_SIZE,
    TARGET_PRECISION_DECIMALS,
)

TARGET_PRECISION = Decimal("0." + "0" * TARGET_PRECISION_DECIMALS)


class KeltnerRSBreakoutConfig(BaseStrategyConfig):
    """Keltner RS Breakout 策略配置"""

    # 简化配置字段（推荐使用）
    symbol: str = ""
    timeframe: str = ""
    price_type: str = "LAST"
    origination: str = "EXTERNAL"
    btc_symbol: str = "BTCUSDT"

    # 完整配置字段（向后兼容，自动从简化字段生成）
    instrument_id: str = ""
    bar_type: str = ""
    btc_instrument_id: str = ""

    # 指标参数
    ema_period: int = DEFAULT_EMA_PERIOD
    atr_period: int = DEFAULT_ATR_PERIOD_LONG
    sma_period: int = DEFAULT_SMA_PERIOD
    rsi_period: int = DEFAULT_RSI_PERIOD
    bb_period: int = DEFAULT_BB_PERIOD
    bb_std: float = DEFAULT_BB_STD
    volume_period: int = DEFAULT_ATR_PERIOD_LONG

    # 通道参数
    keltner_base_multiplier: float = DEFAULT_KELTNER_BASE_MULTIPLIER
    keltner_trigger_multiplier: float = DEFAULT_KELTNER_TRIGGER_MULTIPLIER

    # 风控参数
    base_risk_pct: float = BASE_RISK_PCT
    high_conviction_risk_pct: float = HIGH_CONVICTION_RISK_PCT
    stop_loss_atr_multiplier: float = STOP_LOSS_ATR_MULTIPLIER
    enable_time_stop: bool = True
    time_stop_bars: int = TIME_STOP_BARS
    time_stop_momentum_threshold: float = MOMENTUM_THRESHOLD
    breakeven_multiplier: float = BREAKEVEN_MULTIPLIER
    deviation_threshold: float = DEVIATION_THRESHOLD
    enable_rsi_stop_loss: bool = False
    max_upper_wick_ratio: float = MAX_UPPER_WICK_RATIO

    # 过滤器参数
    volume_multiplier: float = DEFAULT_VOLUME_MULTIPLIER
    rs_short_lookback_days: int = RS_SHORT_PERIOD
    rs_long_lookback_days: int = RS_LONG_PERIOD
    rs_short_weight: float = RS_SHORT_WEIGHT
    rs_long_weight: float = RS_LONG_WEIGHT
    squeeze_memory_days: int = SQUEEZE_MEMORY_DAYS

    # BTC 市场状态过滤器参数
    enable_btc_regime_filter: bool = True
    btc_regime_sma_period: int = BTC_REGIME_SMA_PERIOD
    btc_regime_atr_period: int = BTC_REGIME_ATR_PERIOD
    btc_max_atr_pct: float = VOLATILITY_THRESHOLD

    # 市场狂热度过滤器参数
    enable_euphoria_filter: bool = True
    funding_rate_warning_annual: float = FUNDING_RATE_WARNING_ANNUAL
    funding_rate_danger_annual: float = FUNDING_RATE_DANGER_ANNUAL
    euphoria_reduce_position_pct: float = EUPHORIA_REDUCE_POSITION_PCT

    # Universe 参数
    universe_top_n: int | None = None
    universe_freq: str = "ME"

    # 其他参数
    min_stop_distance_pct: float = MIN_STOP_DISTANCE_PCT
    max_history_size: int = MAX_HISTORY_SIZE


class KeltnerRSBreakoutStrategy(BaseStrategy):
    """
    Keltner RS Breakout 策略 - 重构版本

    使用模块化组件：
    - KeltnerChannel: Keltner 通道指标
    - RelativeStrengthCalculator: 相对强度计算
    - MarketRegimeFilter: BTC 市场状态过滤
    - EntrySignalGenerator: 入场信号生成
    - ExitSignalGenerator: 出场信号生成
    - SqueezeDetector: Squeeze 状态检测
    - DynamicUniverseManager: 动态标的池管理
    """

    def __init__(self, config: KeltnerRSBreakoutConfig):
        super().__init__(config)

        # BTC 标的 ID
        self.btc_instrument_id = InstrumentId.from_str(config.btc_instrument_id)

        # 模块化组件
        self.keltner = KeltnerChannel(
            ema_period=config.ema_period,
            atr_period=config.atr_period,
            sma_period=config.sma_period,
            bb_period=config.bb_period,
            bb_std=config.bb_std,
            volume_period=config.volume_period,
            keltner_base_multiplier=config.keltner_base_multiplier,
            keltner_trigger_multiplier=config.keltner_trigger_multiplier,
        )

        self.rs_calculator = RelativeStrengthCalculator(
            short_lookback_days=config.rs_short_lookback_days,
            long_lookback_days=config.rs_long_lookback_days,
            short_weight=config.rs_short_weight,
            long_weight=config.rs_long_weight,
            max_history_size=config.max_history_size,
        )

        self.btc_regime_filter = MarketRegimeFilter(
            sma_period=config.btc_regime_sma_period,
            atr_period=config.btc_regime_atr_period,
            max_atr_pct=config.btc_max_atr_pct,
        )

        self.entry_signals = EntrySignalGenerator(
            volume_multiplier=config.volume_multiplier,
            max_upper_wick_ratio=config.max_upper_wick_ratio,
        )

        self.exit_signals = ExitSignalGenerator(
            enable_time_stop=config.enable_time_stop,
            time_stop_bars=config.time_stop_bars,
            time_stop_momentum_threshold=config.time_stop_momentum_threshold,
            stop_loss_atr_multiplier=config.stop_loss_atr_multiplier,
            deviation_threshold=config.deviation_threshold,
            enable_rsi_stop_loss=config.enable_rsi_stop_loss,
            breakeven_multiplier=config.breakeven_multiplier,
        )

        self.squeeze_detector = SqueezeDetector(
            memory_days=config.squeeze_memory_days,
        )

        # Universe 管理器
        self.universe_manager: DynamicUniverseManager | None = None
        if config.universe_top_n is not None:
            universe_file = (
                get_project_root()
                / "data"
                / "universe"
                / f"universe_{config.universe_top_n}_{config.universe_freq}.json"
            )
            if universe_file.exists():
                self.universe_manager = DynamicUniverseManager(
                    universe_file=universe_file,
                    freq=config.universe_freq,
                )
                self.log.info(f"成功加载 Universe 管理器: {universe_file}")
            else:
                self.log.warning(f"Universe 文件不存在: {universe_file}")

        # RSI 指标（可选）
        self.rsi_indicator = (
            RelativeStrengthIndex(period=config.rsi_period) if config.enable_rsi_stop_loss else None
        )
        self.rsi: float | None = None

        # 市场狂热度监控
        self.current_funding_rate: float | None = None
        self.funding_rate_annual: float | None = None
        self.market_euphoria_level: str = "NORMAL"
        self.euphoria_reduced: bool = False

        # 持仓跟踪
        self.entry_price: Decimal | None = None
        self.quantity: Decimal | None = None
        self.entry_bar_count = 0
        self.highest_high: float | None = None

        # 订单状态跟踪
        self._pending_entry_order = False

    def on_start(self) -> None:
        """策略启动时初始化"""
        super().on_start()

        self.log.info(
            f"Keltner RS Breakout 启动 (重构版本): "
            f"EMA={self.config.ema_period}, ATR={self.config.atr_period}, "
            f"SMA={self.config.sma_period}, BTC={self.config.btc_instrument_id}"
        )

        # 解析 base symbol（用于缓存机制）
        self._parse_base_symbol()

        # 初始化 RSI 指标
        if self.rsi_indicator:
            self.rsi_indicator.update_raw(0.0)

        # 订阅 Bar 数据
        bar_type = BarType.from_str(self.config.bar_type)
        self.subscribe_bars(bar_type)

        # 订阅 BTC Bar 数据
        if self.instrument.id != self.btc_instrument_id:
            btc_bar_type_str = self.config.bar_type.replace(
                self.instrument.id.symbol.value, self.btc_instrument_id.symbol.value
            )
            btc_bar_type = BarType.from_str(btc_bar_type_str)
            self.subscribe_bars(btc_bar_type)

        # 订阅 Funding Rate 数据
        if self.config.enable_euphoria_filter:
            funding_data_type = DataType(
                FundingRateData, metadata={"instrument_id": self.instrument.id}
            )
            self.subscribe_data(funding_data_type)
            self.log.info(f"已订阅 Funding Rate 数据: {self.instrument.id}")

    def on_stop(self) -> None:
        """策略停止时清理资源"""
        bar_type = BarType.from_str(self.config.bar_type)
        self.unsubscribe_bars(bar_type)

        if self.instrument.id != self.btc_instrument_id:
            btc_bar_type_str = self.config.bar_type.replace(
                self.instrument.id.symbol.value, self.btc_instrument_id.symbol.value
            )
            btc_bar_type = BarType.from_str(btc_bar_type_str)
            self.unsubscribe_bars(btc_bar_type)

        if self.config.enable_euphoria_filter:
            funding_data_type = DataType(
                FundingRateData, metadata={"instrument_id": self.instrument.id}
            )
            self.unsubscribe_data(funding_data_type)

    def on_data(self, data: CustomData) -> None:
        """处理自定义数据（如 Funding Rate）"""
        if isinstance(data, FundingRateData):
            self._handle_funding_rate(data)

    def _handle_funding_rate(self, data: FundingRateData) -> None:
        """处理 Funding Rate 数据并更新市场狂热度等级"""
        self.current_funding_rate = float(data.funding_rate)
        self.funding_rate_annual = float(data.funding_rate_annual)

        old_level = self.market_euphoria_level
        if self.funding_rate_annual >= self.config.funding_rate_danger_annual:
            self.market_euphoria_level = "DANGER"
        elif self.funding_rate_annual >= self.config.funding_rate_warning_annual:
            self.market_euphoria_level = "WARNING"
        else:
            self.market_euphoria_level = "NORMAL"
            self.euphoria_reduced = False

        if old_level != self.market_euphoria_level:
            self.log.warning(
                f"市场狂热度等级变化: {old_level} -> {self.market_euphoria_level}, "
                f"Funding Rate: {self.current_funding_rate:.4%}, "
                f"年化: {self.funding_rate_annual:.2f}%"
            )

        if (
            self.market_euphoria_level == "DANGER"
            and self.quantity is not None
            and not self.euphoria_reduced
        ):
            self._handle_euphoria_reduce_position()

    def _process_main_instrument_bar(self, bar: Bar) -> None:
        """处理主标的 Bar 数据"""
        high = float(bar.high)
        low = float(bar.low)
        close = float(bar.close)
        volume = float(bar.volume)

        # 更新 Keltner 指标
        self.keltner.update(high, low, close, volume)

        # 更新 RS 计算器
        self.rs_calculator.update_symbol_price(bar.ts_event, close)

        # 更新 RSI 指标
        if self.rsi_indicator:
            self.rsi_indicator.handle_bar(bar)
            self.rsi = self.rsi_indicator.value

    def _process_btc_bar(self, bar: Bar) -> None:
        """处理 BTC Bar 数据"""
        high = float(bar.high)
        low = float(bar.low)
        close = float(bar.close)

        # 更新 BTC 市场状态过滤器
        self.btc_regime_filter.update(high, low, close)

        # 更新 RS 计算器
        self.rs_calculator.update_benchmark_price(bar.ts_event, close)

    def _handle_position_management(self, bar: Bar) -> None:
        """处理持仓管理"""
        if self.highest_high is None:
            self.highest_high = float(bar.high)
        else:
            self.highest_high = max(self.highest_high, float(bar.high))

        self.entry_bar_count += 1
        self._handle_exit(bar)

    def _is_symbol_active(self) -> bool:
        """判断当前币种是否活跃"""
        if self.universe_manager is None:
            return True

        try:
            from utils.instrument_helpers import parse_instrument_id

            symbol, _, _ = parse_instrument_id(str(self.instrument.id))
            base_symbol = symbol.replace("-", "") if symbol else ""
        except Exception:
            instrument_str = str(self.instrument.id)
            base_symbol = instrument_str.split("-")[0].split(".")[0]

        return self.universe_manager.is_active(base_symbol)

    def _check_entry_conditions(self, bar: Bar) -> bool:
        """检查入场条件"""
        close = float(bar.close)
        volume = float(bar.volume)

        # 基本条件
        if self._pending_entry_order:
            return False

        if not self._is_symbol_active():
            return False

        # 市场过滤器
        if self.config.enable_btc_regime_filter:
            if not self.btc_regime_filter.is_favorable_for_altcoins():
                return False

        if self.config.enable_euphoria_filter:
            if self.market_euphoria_level in ("DANGER", "WARNING"):
                return False

        # 价格和相对强度
        if self.keltner.sma is None or close < self.keltner.sma:
            return False

        if not self.rs_calculator.is_strong(threshold=RS_THRESHOLD):
            return False

        # 成交量
        if not self.entry_signals.check_volume_surge(volume, self.keltner.volume_sma):
            return False

        # Keltner 突破
        keltner_trigger_upper, _ = self.keltner.get_keltner_trigger_bands()
        if not self.entry_signals.check_keltner_breakout(close, keltner_trigger_upper):
            return False

        # 上影线比例
        if not self.entry_signals.check_wick_ratio(float(bar.high), float(bar.low), close):
            return False

        return True

    def on_bar(self, bar: Bar) -> None:
        """处理 Bar 数据"""
        if bar.bar_type.instrument_id == self.instrument.id:
            self._process_main_instrument_bar(bar)
        elif bar.bar_type.instrument_id == self.btc_instrument_id:
            self._process_btc_bar(bar)
            return
        else:
            return

        # 更新 Universe
        if self.universe_manager:
            self.universe_manager.update(bar.ts_event)

        # 等待指标准备好
        if not self.keltner.is_ready():
            return

        # 检查 Squeeze 状态
        keltner_upper, keltner_lower = self.keltner.get_keltner_base_bands()
        is_squeezing = self.squeeze_detector.check_squeeze(
            self.keltner.bb.upper,
            self.keltner.bb.lower,
            keltner_upper,
            keltner_lower,
        )

        # 持仓管理
        if self.portfolio.is_net_long(self.instrument.id):
            self._handle_position_management(bar)
            return

        # 入场检查
        if self._check_entry_conditions(bar):
            self._handle_entry(bar, is_squeezing)

    def _handle_entry(self, bar: Bar, is_squeezing: bool) -> None:
        """处理开仓逻辑"""
        close = float(bar.close)

        # 检查持仓数量限制
        total_positions = len(self.cache.positions_open())
        if total_positions >= self.config.max_positions:
            return

        # 判断是否为高确信度设置
        high_conviction = self.squeeze_detector.is_high_conviction(is_squeezing)

        # 计算仓位
        qty = self._calculate_position_size(bar, high_conviction)
        if not qty or qty <= 0:
            return

        # 下单
        order = self.order_factory.market(
            instrument_id=self.instrument.id,
            order_side=OrderSide.BUY,
            quantity=self.instrument.make_qty(qty),
        )
        self.submit_order(order)
        self._pending_entry_order = True

        # 记录持仓信息
        self.entry_price = Decimal(close).quantize(TARGET_PRECISION, ROUND_HALF_UP)
        self.quantity = qty.quantize(TARGET_PRECISION, ROUND_HALF_UP)
        self.entry_bar_count = 0
        self.highest_high = float(bar.high)
        self.euphoria_reduced = False

        keltner_trigger_upper, _ = self.keltner.get_keltner_trigger_bands()
        conviction_type = "高确信度" if high_conviction else "普通"
        self.log.info(
            f"开仓做多 ({conviction_type}): "
            f"price={close:.2f}, trigger={keltner_trigger_upper:.2f}, "
            f"qty={qty}, squeeze={is_squeezing}"
        )

    def _calculate_position_size(self, bar: Bar, high_conviction: bool) -> Decimal:
        """计算仓位大小"""
        account = self.portfolio.account(self.instrument.id.venue)
        if not account:
            return Decimal("0")

        equity = account.balance_total(self.instrument.quote_currency)
        if not equity or equity.as_decimal() <= 0:
            return Decimal("0")

        equity_decimal = equity.as_decimal()

        # 百分比模式
        if self.config.qty_percent is not None:
            qty_pct = Decimal(str(self.config.qty_percent))
            leverage = Decimal(str(self.config.leverage))
            price = bar.close.as_decimal()
            qty = (equity_decimal * qty_pct * leverage) / price
            return self.instrument.make_qty(qty)

        # ATR 风险模式
        if self.keltner.atr is None:
            return Decimal("0")

        stop_distance = Decimal(str(self.config.stop_loss_atr_multiplier)) * Decimal(
            str(self.keltner.atr)
        )
        min_stop_distance = bar.close.as_decimal() * Decimal(str(self.config.min_stop_distance_pct))

        if stop_distance < min_stop_distance:
            self.log.warning(
                f"ATR过小({self.keltner.atr:.6f})，使用最小止损距离{min_stop_distance}"
            )
            stop_distance = min_stop_distance

        risk_pct = Decimal(
            str(
                self.config.high_conviction_risk_pct
                if high_conviction
                else self.config.base_risk_pct
            )
        )
        risk_amount = equity_decimal * risk_pct * Decimal(str(self.config.leverage))
        qty = risk_amount / stop_distance

        min_qty = Decimal(str(self.instrument.size_increment))
        if qty < min_qty:
            self.log.warning(f"计算的仓位数量过小: raw_qty={qty}, min_qty={min_qty}")
            return Decimal("0")

        return qty

    def _handle_exit(self, bar: Bar) -> None:
        """处理出场逻辑"""
        close = float(bar.close)

        # 1. 时间止损
        if self.exit_signals.check_time_stop(
            self.entry_bar_count, self.highest_high, self.entry_price
        ):
            self.close_all_positions(self.instrument.id)
            self.log.info(
                f"时间止损平仓: bars={self.entry_bar_count}, "
                f"highest={self.highest_high:.2f}, entry={self.entry_price:.2f}"
            )
            self._reset_position_tracking()
            return

        # 2. Chandelier Exit
        if self.exit_signals.check_chandelier_exit(close, self.highest_high, self.keltner.atr):
            trailing_stop = self.highest_high - (
                self.config.stop_loss_atr_multiplier * self.keltner.atr
            )
            self.close_all_positions(self.instrument.id)
            self.log.info(
                f"Chandelier Exit 平仓: "
                f"price={close:.2f}, stop={trailing_stop:.2f}, "
                f"highest={self.highest_high:.2f}"
            )
            self._reset_position_tracking()
            return

        # 3. 抛物线止盈
        if self.exit_signals.check_parabolic_profit(close, self.keltner.ema):
            self.close_all_positions(self.instrument.id)
            self.log.info(f"抛物线止盈平仓: price={close:.2f}, ema={self.keltner.ema:.2f}")
            self._reset_position_tracking()
            return

        # 4. RSI 超买止盈
        if self.exit_signals.check_rsi_overbought(self.rsi):
            self.close_all_positions(self.instrument.id)
            self.log.info(f"RSI 超买右侧平仓: price={close:.2f}, rsi={self.rsi:.2f}")
            self._reset_position_tracking()
            return

        # 5. 保本止损
        self.exit_signals.update_breakeven_status(close, self.entry_price, self.keltner.atr)

        if self.exit_signals.check_breakeven_stop(close, self.entry_price):
            breakeven_stop_price = float(self.entry_price) * 1.002
            self.close_all_positions(self.instrument.id)
            self.log.info(
                f"🛡️ 保本止损平仓: price={close:.2f}, "
                f"breakeven_stop={breakeven_stop_price:.2f}, "
                f"entry={self.entry_price:.2f}"
            )
            self._reset_position_tracking()
            return

    def _handle_euphoria_reduce_position(self) -> None:
        """处理市场狂热状态下的减仓逻辑"""
        if self.quantity is None or self.entry_price is None:
            return

        reduce_quantity = (
            self.quantity * Decimal(str(self.config.euphoria_reduce_position_pct))
        ).quantize(TARGET_PRECISION, ROUND_DOWN)

        if reduce_quantity <= 0:
            return

        self.log.warning(
            f"🔥 市场狂热减仓: 当前仓位={self.quantity}, "
            f"减仓数量={reduce_quantity}, 减仓比例={self.config.euphoria_reduce_position_pct:.0%}, "
            f"Funding Rate 年化={self.funding_rate_annual:.2f}%"
        )

        order = self.order_factory.market(
            instrument_id=self.instrument.id,
            order_side=OrderSide.SELL,
            quantity=reduce_quantity,
        )
        self.submit_order(order)
        self.euphoria_reduced = True

    def _reset_position_tracking(self) -> None:
        """重置持仓跟踪变量"""
        self.entry_price = None
        self.quantity = None
        self.entry_bar_count = 0
        self.highest_high = None
        self.exit_signals.reset()

    def on_order_filled(self, event) -> None:
        """订单成交回调"""
        super().on_order_filled(event)
        self._pending_entry_order = False

    def on_order_rejected(self, event) -> None:
        """订单拒绝回调"""
        super().on_order_rejected(event)
        self._pending_entry_order = False
        self.log.error(f"订单被拒绝: {event.reason}")
