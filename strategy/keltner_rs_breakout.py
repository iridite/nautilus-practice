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
from ta.trend import ADXIndicator
import pandas as pd

from config.constants import (
    BASE_RISK_PCT,
    BREAKEVEN_MULTIPLIER,
    BTC_REGIME_ATR_PERIOD,
    BTC_REGIME_SMA_PERIOD,
    DEFAULT_ATR_PERIOD_LONG,
    DEFAULT_BB_PERIOD,
    DEFAULT_BB_STD,
    DEFAULT_EMA_PERIOD,
    DEFAULT_KELTNER_BASE_MULTIPLIER,
    DEFAULT_KELTNER_TRIGGER_MULTIPLIER,
    DEFAULT_RSI_PERIOD,
    DEFAULT_SMA_PERIOD,
    DEFAULT_VOLUME_MULTIPLIER,
    DEVIATION_THRESHOLD,
    EUPHORIA_REDUCE_POSITION_PCT,
    FUNDING_RATE_DANGER_ANNUAL,
    FUNDING_RATE_WARNING_ANNUAL,
    HIGH_CONVICTION_RISK_PCT,
    MAX_HISTORY_SIZE,
    MAX_UPPER_WICK_RATIO,
    MIN_STOP_DISTANCE_PCT,
    MOMENTUM_THRESHOLD,
    RS_LONG_PERIOD,
    RS_LONG_WEIGHT,
    RS_SHORT_PERIOD,
    RS_SHORT_WEIGHT,
    RS_THRESHOLD,
    SQUEEZE_MEMORY_DAYS,
    STOP_LOSS_ATR_MULTIPLIER,
    TARGET_PRECISION_DECIMALS,
    TIME_STOP_BARS,
    VOLATILITY_THRESHOLD,
)
from strategy.common.indicators import (
    KeltnerChannel,
    MarketRegimeFilter,
    RelativeStrengthCalculator,
)
from strategy.common.signals import EntrySignalGenerator, ExitSignalGenerator, SqueezeDetector
from strategy.common.universe import DynamicUniverseManager
from strategy.core.base import BaseStrategy, BaseStrategyConfig
from utils import get_project_root
from utils.custom_data import FundingRateData
from indicators.choppiness_index import ChoppinessIndex

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

    # 市场状态机参数
    adx_period: int = 14
    chop_period: int = 14
    adx_threshold: float = 20.0
    chop_threshold: float = 61.8
    min_squeeze_duration: int = 5

    # 做空参数
    enable_short: bool = False
    short_trigger_multiplier: float = 2.8
    short_stop_atr_multiplier: float = 2.0
    short_body_position_threshold: float = 0.3


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

        # 市场状态机指标
        self.chop_indicator = ChoppinessIndex(period=config.chop_period)
        self.adx_highs = []
        self.adx_lows = []
        self.adx_closes = []
        self.adx_value: float | None = None
        self.squeeze_duration = 0  # Squeeze 持续 K 线数

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

        # 持仓跟踪（做多）
        self.entry_price: Decimal | None = None
        self.quantity: Decimal | None = None
        self.entry_bar_count = 0
        self.highest_high: float | None = None

        # 持仓跟踪（做空）
        self.short_entry_price: Decimal | None = None
        self.short_quantity: Decimal | None = None
        self.short_entry_bar_count = 0
        self.lowest_low: float | None = None

        # 订单状态跟踪
        self._pending_entry_order = False

        # 符号活跃缓存
        self._base_symbol: str | None = None
        self._is_active_cache: bool = True
        self._last_universe_period: str | None = None

        # 过滤器统计（用于调试）
        self.filter_stats = {
            "total_bars": 0,
            "not_in_universe": 0,
            "btc_regime": 0,
            "price_below_sma": 0,
            "rs_weak": 0,
            "volume_low": 0,
            "keltner_no_breakout": 0,
            "wick_ratio": 0,
            "choppy_regime": 0,
            "squeeze_duration_short": 0,
            "passed_all": 0,
        }

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
        # 注意：即使主标的是 BTC，也需要订阅（用于 RS 计算的 benchmark）
        btc_bar_type_str = self.config.bar_type.replace(
            self.instrument.id.symbol.value, self.btc_instrument_id.symbol.value
        )
        btc_bar_type = BarType.from_str(btc_bar_type_str)

        self.log.info(
            f"[{self.instrument.symbol}] Subscribing to BTC bar: "
            f"main_bar={bar_type}, btc_bar={btc_bar_type}, same={btc_bar_type == bar_type}"
        )

        # 只有当 bar_type 不同时才订阅（避免重复订阅）
        if btc_bar_type != bar_type:
            self.subscribe_bars(btc_bar_type)
            self.log.info(f"[{self.instrument.symbol}] ✅ Subscribed to BTC bar")
        else:
            self.log.info(f"[{self.instrument.symbol}] ⚠️ Skipped BTC subscription (same as main)")

        # 订阅 Funding Rate 数据
        if self.config.enable_euphoria_filter:
            funding_data_type = DataType(
                FundingRateData, metadata={"instrument_id": self.instrument.id}
            )
            self.subscribe_data(funding_data_type)
            self.log.info(f"已订阅 Funding Rate 数据: {self.instrument.id}")

    def on_stop(self) -> None:
        """策略停止时清理资源"""
        # 输出过滤器统计
        self._log_filter_statistics()

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

    def _log_filter_statistics(self) -> None:
        """输出过滤器统计信息"""
        symbol = self.instrument.id.symbol.value
        total = self.filter_stats["total_bars"]

        if total == 0:
            self.log.info(f"[{symbol}] No bars processed")
            return

        self.log.info(f"\n{'=' * 60}")
        self.log.info(f"Filter Statistics for {symbol}")
        self.log.info(f"{'=' * 60}")
        self.log.info(f"Total bars processed: {total}")
        self.log.info(f"{'-' * 60}")

        # 计算每个过滤器的拦截率
        filters = [
            ("Not in Universe", "not_in_universe"),
            ("BTC Regime", "btc_regime"),
            ("Price < SMA(200)", "price_below_sma"),
            ("RS Weak", "rs_weak"),
            ("Volume Low", "volume_low"),
            ("Keltner No Breakout", "keltner_no_breakout"),
            ("Wick Ratio", "wick_ratio"),
        ]

        for name, key in filters:
            count = self.filter_stats[key]
            pct = (count / total * 100) if total > 0 else 0
            self.log.info(f"{name:25s}: {count:6d} ({pct:5.2f}%)")

        passed = self.filter_stats["passed_all"]
        passed_pct = (passed / total * 100) if total > 0 else 0
        self.log.info(f"{'-' * 60}")
        self.log.info(f"{'Passed All Filters':25s}: {passed:6d} ({passed_pct:5.2f}%)")
        self.log.info(f"{'=' * 60}\n")

        # 警告：如果所有信号都被拦截（使用 ERROR 级别确保始终显示）
        if passed == 0 and total > 0:
            self.log.error(
                f"⚠️  [{symbol}] 100% of signals blocked by filters - no trades generated"
            )

            # 识别主要拦截器
            top_blockers = []
            for name, key in filters:
                count = self.filter_stats[key]
                pct = (count / total * 100) if total > 0 else 0
                if pct > 10:  # 拦截率超过 10% 的过滤器
                    top_blockers.append(f"{name} ({pct:.1f}%)")

            if top_blockers:
                self.log.error(f"   Main blockers: {', '.join(top_blockers)}")
                self.log.error(
                    "   Consider: adjusting filter thresholds or increasing universe_top_n"
                )

    def _parse_base_symbol(self) -> None:
        """解析并缓存 base symbol（仅在启动时执行一次）"""
        try:
            from utils.instrument_helpers import parse_instrument_id

            # 优先使用 instrument.id，如果不可用则使用 config.symbol
            instrument_str = str(self.instrument.id) if self.instrument else self.config.symbol
            symbol, _, _ = parse_instrument_id(instrument_str)
            self._base_symbol = symbol.replace("-", "") if symbol else ""
        except Exception:
            # Fallback: 从 instrument 或 config 中提取 base symbol
            instrument_str = str(self.instrument.id) if self.instrument else self.config.symbol
            self._base_symbol = instrument_str.split("-")[0].split(".")[0]

        if hasattr(self, "log"):
            self.log.info(f"解析 base symbol: {self._base_symbol}")

    def _update_active_cache(self, ts_event: int) -> None:
        """更新符号活跃缓存（仅在 universe 周期变化时更新）"""
        if self.universe_manager is None:
            self._is_active_cache = True
            return

        # 调用 update() 检查周期是否变化
        period_changed = self.universe_manager.update(ts_event)
        if period_changed:
            current_period = self.universe_manager.get_current_period()
            self._last_universe_period = current_period
            self._is_active_cache = self.universe_manager.is_active(self._base_symbol)
            self.log.debug(
                f"更新活跃缓存: period={current_period}, "
                f"symbol={self._base_symbol}, active={self._is_active_cache}"
            )

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

        # 更新 CHOP 指标
        self.chop_indicator.handle_bar(bar)

        # 更新 ADX 指标（使用 pandas）
        self.adx_highs.append(high)
        self.adx_lows.append(low)
        self.adx_closes.append(close)

        # 保持窗口大小
        max_window = self.config.adx_period + 50  # 留一些余量
        if len(self.adx_highs) > max_window:
            self.adx_highs.pop(0)
            self.adx_lows.pop(0)
            self.adx_closes.pop(0)

        # 计算 ADX (需要至少 2*period 的数据才能稳定计算)
        min_data_points = self.config.adx_period * 2
        if len(self.adx_highs) >= min_data_points:
            import pandas as pd
            from ta.trend import ADXIndicator

            df = pd.DataFrame({
                'high': self.adx_highs,
                'low': self.adx_lows,
                'close': self.adx_closes
            })
            adx_indicator = ADXIndicator(
                high=df['high'],
                low=df['low'],
                close=df['close'],
                window=self.config.adx_period
            )
            adx_series = adx_indicator.adx()
            # 只有当 ADX 计算完成时才更新值
            if not adx_series.empty and not pd.isna(adx_series.iloc[-1]):
                self.adx_value = adx_series.iloc[-1]

    def _process_btc_bar(self, bar: Bar) -> None:
        """处理 BTC Bar 数据"""
        high = float(bar.high)
        low = float(bar.low)
        close = float(bar.close)

        self.log.debug(
            f"[{self.instrument.symbol}] Processing BTC bar: ts={bar.ts_event}, close={close}"
        )

        # 更新 BTC 市场状态过滤器
        self.btc_regime_filter.update(high, low, close)

        # 更新 RS 计算器
        self.rs_calculator.update_benchmark_price(bar.ts_event, close)

    def get_market_regime(self) -> str:
        """
        获取市场状态

        Returns:
            "BEAR": BTC < SMA(200)
            "CHOPPY": ADX < 20 or CHOP > 61.8
            "BULL": 其他情况
        """
        # 检查 BTC 市场状态
        if not self.btc_regime_filter.is_bullish_regime():
            return "BEAR"

        # 检查震荡状态
        if self.adx_value is not None and self.adx_value < self.config.adx_threshold:
            return "CHOPPY"

        if self.chop_indicator.initialized and self.chop_indicator.value > self.config.chop_threshold:
            return "CHOPPY"

        return "BULL"

    def _handle_long_position_management(self, bar: Bar) -> None:
        """处理做多持仓管理"""
        if self.highest_high is None:
            self.highest_high = float(bar.high)
        else:
            self.highest_high = max(self.highest_high, float(bar.high))

        self.entry_bar_count += 1
        self._handle_long_exit(bar)

    def _handle_short_position_management(self, bar: Bar) -> None:
        """处理做空持仓管理"""
        if self.lowest_low is None:
            self.lowest_low = float(bar.low)
        else:
            self.lowest_low = min(self.lowest_low, float(bar.low))

        self.short_entry_bar_count += 1
        self._handle_short_exit(bar)

    def _is_symbol_active(self) -> bool:
        """判断当前币种是否活跃（使用缓存）"""
        return self._is_active_cache

    def _check_entry_conditions(self, bar: Bar) -> bool:
        """检查入场条件"""
        close = float(bar.close)
        volume = float(bar.volume)
        symbol = self.instrument.id.symbol.value

        self.filter_stats["total_bars"] += 1

        # 基本条件
        if self._pending_entry_order:
            self.log.debug(f"[{symbol}] ❌ Pending entry order exists")
            return False

        if not self._is_symbol_active():
            self.filter_stats["not_in_universe"] += 1
            self.log.debug(f"[{symbol}] ❌ Not in Universe")
            return False

        # 市场过滤器
        if self.config.enable_btc_regime_filter:
            if not self.btc_regime_filter.is_favorable_for_altcoins():
                self.filter_stats["btc_regime"] += 1
                self.log.debug(f"[{symbol}] ❌ BTC regime unfavorable")
                return False

        if self.config.enable_euphoria_filter:
            if self.market_euphoria_level in ("DANGER", "WARNING"):
                self.log.debug(f"[{symbol}] ❌ Market euphoria: {self.market_euphoria_level}")
                return False

        # 价格和相对强度
        if self.keltner.sma is None or close < self.keltner.sma:
            self.filter_stats["price_below_sma"] += 1
            self.log.debug(f"[{symbol}] ❌ Price < SMA(200): {close:.2f} < {self.keltner.sma}")
            return False

        # RS 计算（短路优化：避免重复��算）
        # 特殊情况：如果主标的就是 BTC，RS 视为 0（不强于自己）
        if self.instrument.id == self.btc_instrument_id:
            rs_value = 0.0
        else:
            rs_value = self.rs_calculator.calculate_rs()
        if rs_value is None or rs_value <= RS_THRESHOLD:
            self.filter_stats["rs_weak"] += 1
            self.log.debug(f"[{symbol}] ❌ RS not strong: {rs_value}")
            return False

        # 成交量
        if not self.entry_signals.check_volume_surge(volume, self.keltner.volume_sma):
            self.filter_stats["volume_low"] += 1
            vol_ratio = volume / self.keltner.volume_sma if self.keltner.volume_sma else 0
            self.log.debug(f"[{symbol}] ❌ Volume surge failed: {vol_ratio:.2f}x")
            return False

        # Keltner 突破
        keltner_trigger_upper, _ = self.keltner.get_keltner_trigger_bands()
        if not self.entry_signals.check_keltner_breakout(close, keltner_trigger_upper):
            self.filter_stats["keltner_no_breakout"] += 1
            self.log.debug(
                f"[{symbol}] ❌ Keltner breakout failed: {close:.2f} vs {keltner_trigger_upper:.2f}"
            )
            return False

        # 上影线比例
        if not self.entry_signals.check_wick_ratio(float(bar.high), float(bar.low), close):
            self.filter_stats["wick_ratio"] += 1
            self.log.debug(f"[{symbol}] ❌ Wick ratio check failed")
            return False

        # 市场状态机过滤：只在非震荡市场交易
        market_regime = self.get_market_regime()
        if market_regime == "CHOPPY":
            self.filter_stats["choppy_regime"] += 1
            self.log.debug(
                f"[{symbol}] ❌ Market is choppy: ADX={self.adx_value}, CHOP={self.chop_indicator.value}"
            )
            return False

        # Squeeze 持续时间检查
        # 注意：这里需要在 on_bar 中更新 squeeze_duration
        if self.squeeze_duration < self.config.min_squeeze_duration:
            self.filter_stats["squeeze_duration_short"] += 1
            self.log.debug(
                f"[{symbol}] ❌ Squeeze duration too short: {self.squeeze_duration} < {self.config.min_squeeze_duration}"
            )
            return False

        self.filter_stats["passed_all"] += 1
        self.log.info(f"[{symbol}] ✅ All entry conditions passed at {bar.ts_event}!")
        return True

    def _check_short_entry_conditions(self, bar: Bar) -> bool:
        """检查做空入场条件"""
        close = float(bar.close)
        high = float(bar.high)
        low = float(bar.low)
        volume = float(bar.volume)
        symbol = self.instrument.id.symbol.value

        # 基本条件
        if self._pending_entry_order:
            self.log.debug(f"[{symbol}] ❌ SHORT: Pending entry order exists")
            return False

        if not self._is_symbol_active():
            self.log.debug(f"[{symbol}] ❌ SHORT: Not in Universe")
            return False

        # 市场过滤器：只在熊市做空
        market_regime = self.get_market_regime()
        if market_regime != "BEAR":
            self.log.debug(f"[{symbol}] ❌ SHORT: Not in BEAR regime (current: {market_regime})")
            return False

        # 价格必须低于 SMA(200)
        if self.keltner.sma is None or close > self.keltner.sma:
            self.log.debug(f"[{symbol}] ❌ SHORT: Price > SMA(200): {close:.2f} > {self.keltner.sma}")
            return False

        # 成交量检查
        if not self.entry_signals.check_volume_surge(volume, self.keltner.volume_sma):
            vol_ratio = volume / self.keltner.volume_sma if self.keltner.volume_sma else 0
            self.log.debug(f"[{symbol}] ❌ SHORT: Volume surge failed: {vol_ratio:.2f}x")
            return False

        # Keltner 下轨突破（使用做空专用倍数）
        # 计算做空触发下轨
        if self.keltner.ema is None or self.keltner.atr is None:
            return False

        short_trigger_lower = self.keltner.ema - (self.config.short_trigger_multiplier * self.keltner.atr)
        if close > short_trigger_lower:
            self.log.debug(
                f"[{symbol}] ❌ SHORT: No breakdown: {close:.2f} > {short_trigger_lower:.2f}"
            )
            return False

        # 实体位置过滤：收盘价必须在 K 线底部 30% 区域
        bar_range = high - low
        if bar_range > 0:
            body_position = (close - low) / bar_range
            if body_position > self.config.short_body_position_threshold:
                self.log.debug(
                    f"[{symbol}] ❌ SHORT: Body position too high: {body_position:.2%} > {self.config.short_body_position_threshold:.2%}"
                )
                return False

        # Squeeze 持续时间检查
        if self.squeeze_duration < self.config.min_squeeze_duration:
            self.log.debug(
                f"[{symbol}] ❌ SHORT: Squeeze duration too short: {self.squeeze_duration} < {self.config.min_squeeze_duration}"
            )
            return False

        self.log.info(f"[{symbol}] ✅ SHORT: All entry conditions passed at {bar.ts_event}!")
        return True

    def on_bar(self, bar: Bar) -> None:
        """处理 Bar 数据"""
        is_main_instrument = bar.bar_type.instrument_id == self.instrument.id
        is_btc_instrument = bar.bar_type.instrument_id == self.btc_instrument_id

        # DEBUG: 记录 bar 接收情况
        if self.instrument.symbol.value == "BTCUSDT-PERP":
            self.log.debug(
                f"[{self.instrument.symbol}] Received bar: "
                f"bar_instrument={bar.bar_type.instrument_id}, "
                f"is_main={is_main_instrument}, is_btc={is_btc_instrument}"
            )

        # 先处理 BTC benchmark bar（如果是）
        if is_btc_instrument:
            self._process_btc_bar(bar)

        # 处理主标的 bar
        if is_main_instrument:
            self._process_main_instrument_bar(bar)
        elif not is_btc_instrument:
            # 既不是主标的也不是 BTC，忽略
            return
        else:
            # 是 BTC 但不是主标的，已处理完毕
            return

        # 更新 Universe 和活跃缓存
        if self.universe_manager:
            self._update_active_cache(bar.ts_event)

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

        # 更新 Squeeze 持续时间计数器
        if is_squeezing:
            self.squeeze_duration += 1
        else:
            self.squeeze_duration = 0

        # 持仓管理
        if self.portfolio.is_net_long(self.instrument.id):
            self._handle_long_position_management(bar)
            return

        if self.portfolio.is_net_short(self.instrument.id):
            self._handle_short_position_management(bar)
            return

        # 入场检查
        if self._check_entry_conditions(bar):
            self._handle_entry(bar, is_squeezing)

        # 做空入场检查（仅在熊市且启用做空时）
        if self.config.enable_short and self.get_market_regime() == "BEAR":
            if self._check_short_entry_conditions(bar):
                self._handle_short_entry(bar, is_squeezing)

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

    def _handle_short_entry(self, bar: Bar, is_squeezing: bool) -> None:
        """处理做空开仓逻辑"""
        close = float(bar.close)

        # 检查持仓数量限制
        total_positions = len(self.cache.positions_open())
        if total_positions >= self.config.max_positions:
            return

        # 判断是否为高确信度设置
        high_conviction = self.squeeze_detector.is_high_conviction(is_squeezing)

        # 计算仓位（使用做空专用止损倍数）
        qty = self._calculate_short_position_size(bar, high_conviction)
        if not qty or qty <= 0:
            return

        # 下单
        order = self.order_factory.market(
            instrument_id=self.instrument.id,
            order_side=OrderSide.SELL,
            quantity=self.instrument.make_qty(qty),
        )
        self.submit_order(order)
        self._pending_entry_order = True

        # 记录持仓信息
        self.short_entry_price = Decimal(close).quantize(TARGET_PRECISION, ROUND_HALF_UP)
        self.short_quantity = qty.quantize(TARGET_PRECISION, ROUND_HALF_UP)
        self.short_entry_bar_count = 0
        self.lowest_low = float(bar.low)

        # 计算做空触发下轨
        short_trigger_lower = self.keltner.ema - (self.config.short_trigger_multiplier * self.keltner.atr)
        conviction_type = "高确信度" if high_conviction else "普通"
        self.log.info(
            f"开仓做空 ({conviction_type}): "
            f"price={close:.2f}, trigger={short_trigger_lower:.2f}, "
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

    def _calculate_short_position_size(self, bar: Bar, high_conviction: bool) -> Decimal:
        """计算做空仓位大小（使用做空专用止损倍数）"""
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

        # ATR 风险模式（使用做空专用止损倍数）
        if self.keltner.atr is None:
            return Decimal("0")

        stop_distance = Decimal(str(self.config.short_stop_atr_multiplier)) * Decimal(
            str(self.keltner.atr)
        )
        min_stop_distance = bar.close.as_decimal() * Decimal(str(self.config.min_stop_distance_pct))

        if stop_distance < min_stop_distance:
            self.log.warning(
                f"SHORT: ATR过小({self.keltner.atr:.6f})，使用最小止损距离{min_stop_distance}"
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
            self.log.warning(f"SHORT: 计算的仓位数量过小: raw_qty={qty}, min_qty={min_qty}")
            return Decimal("0")

        return qty

    def _handle_long_exit(self, bar: Bar) -> None:
        """处理做多出场逻辑"""
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
        if self.entry_price is not None:
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

    def _handle_short_exit(self, bar: Bar) -> None:
        """处理做空出场逻辑"""
        close = float(bar.close)

        # 1. 时间止损（做空版本）
        if self.exit_signals.check_time_stop(
            self.short_entry_bar_count, self.lowest_low, self.short_entry_price
        ):
            self.close_all_positions(self.instrument.id)
            self.log.info(
                f"SHORT: 时间止损平仓: bars={self.short_entry_bar_count}, "
                f"lowest={self.lowest_low:.2f}, entry={self.short_entry_price:.2f}"
            )
            self._reset_short_position_tracking()
            return

        # 2. Chandelier Exit（做空版本：使用 lowest_low）
        if self.keltner.atr is not None and self.lowest_low is not None:
            trailing_stop = self.lowest_low + (
                self.config.short_stop_atr_multiplier * self.keltner.atr
            )
            if close >= trailing_stop:
                self.close_all_positions(self.instrument.id)
                self.log.info(
                    f"SHORT: Chandelier Exit 平仓: "
                    f"price={close:.2f}, stop={trailing_stop:.2f}, "
                    f"lowest={self.lowest_low:.2f}"
                )
                self._reset_short_position_tracking()
                return

        # 3. 抛物线止盈（做空版本：价格上穿 EMA）
        if self.keltner.ema is not None and close > self.keltner.ema:
            self.close_all_positions(self.instrument.id)
            self.log.info(f"SHORT: 抛物线止盈平仓: price={close:.2f}, ema={self.keltner.ema:.2f}")
            self._reset_short_position_tracking()
            return

        # 4. 保本止损（做空版本）
        if self.short_entry_price is not None and self.keltner.atr is not None:
            # 当价格下跌超过 1.5 ATR 时，移动止损到入场价附近
            price_move = float(self.short_entry_price) - close
            if price_move > self.config.breakeven_multiplier * self.keltner.atr:
                breakeven_stop_price = float(self.short_entry_price) * 0.998  # 略低于入场价
                if close >= breakeven_stop_price:
                    self.close_all_positions(self.instrument.id)
                    self.log.info(
                        f"SHORT: 🛡️ 保本止损平仓: price={close:.2f}, "
                        f"breakeven_stop={breakeven_stop_price:.2f}, "
                        f"entry={self.short_entry_price:.2f}"
                    )
                    self._reset_short_position_tracking()
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

    def _reset_short_position_tracking(self) -> None:
        """重置做空持仓跟踪变量"""
        self.short_entry_price = None
        self.short_quantity = None
        self.short_entry_bar_count = 0
        self.lowest_low = None

    def on_order_filled(self, event) -> None:
        """订单成交回调"""
        super().on_order_filled(event)
        self._pending_entry_order = False

    def on_order_rejected(self, event) -> None:
        """订单拒绝回调"""
        super().on_order_rejected(event)
        self._pending_entry_order = False
        self.log.error(f"订单被拒绝: {event.reason}")
