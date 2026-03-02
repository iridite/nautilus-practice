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

from nautilus_trader.model.data import Bar, BarType, CustomData, DataType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId

from config.constants import (
    BASE_RISK_PCT,
    DEFAULT_ATR_PERIOD_LONG,
    DEFAULT_BB_PERIOD,
    DEFAULT_BB_STD,
    DEFAULT_EMA_PERIOD,
    DEFAULT_KELTNER_BASE_MULTIPLIER,
    DEFAULT_KELTNER_TRIGGER_MULTIPLIER,
    DEFAULT_SMA_PERIOD,
    DEFAULT_VOLUME_MULTIPLIER,
    EUPHORIA_REDUCE_POSITION_PCT,
    FILTER_BLOCKER_THRESHOLD,
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
)
from strategy.common.indicators import (
    KeltnerChannel,
    RelativeStrengthCalculator,
)
from strategy.common.signals import EntrySignalGenerator, ExitSignalGenerator, SqueezeDetector
from strategy.common.universe import DynamicUniverseManager
from strategy.core.base import BaseStrategy, BaseStrategyConfig
from utils import get_project_root
from utils.custom_data import FundingRateData
from live.funding_rate_monitor import FundingRateMonitor
from live.circuit_breaker import CircuitBreakerManager, InstrumentType

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
    max_upper_wick_ratio: float = MAX_UPPER_WICK_RATIO
    min_body_ratio: float = 0.4  # K线最小实体比例（实体/全长）
    max_position_risk_pct: float = 0.2  # 单个资产最大仓位占比 (20%)
    min_atr: float = 0.0001  # 最小 ATR 保护值

    # 过滤器参数
    volume_multiplier: float = DEFAULT_VOLUME_MULTIPLIER
    rs_short_lookback_days: int = RS_SHORT_PERIOD
    rs_long_lookback_days: int = RS_LONG_PERIOD
    rs_short_weight: float = RS_SHORT_WEIGHT
    rs_long_weight: float = RS_LONG_WEIGHT
    squeeze_memory_days: int = SQUEEZE_MEMORY_DAYS

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
    Keltner RS Breakout 策略 - 纯粹趋势跟踪版本

    核心理念：
    - 移除所有预测性指标 (RSI, MACD, ADX, CHOP)
    - 移除固定止盈逻辑 (deviation_threshold, breakeven)
    - 禁用做空功能
    - 实现纯粹的 Chandelier Exit (只升不降)
    - 波动率平价建仓 + 仓位上限保护

    使用模块化组件：
    - KeltnerChannel: Keltner 通道指标
    - RelativeStrengthCalculator: 相对强度计算
    - EntrySignalGenerator: 入场信号生成
    - ExitSignalGenerator: 出场信号生成
    - SqueezeDetector: Squeeze 状态检测
    - DynamicUniverseManager: 动态标的池管理
    """

    # 日志格式常量（避免每次日志调用时重复计算字符串乘法）
    _LOG_SEPARATOR = "=" * 60
    _LOG_SUBSEPARATOR = "-" * 60

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

        self.entry_signals = EntrySignalGenerator(
            volume_multiplier=config.volume_multiplier,
            max_upper_wick_ratio=config.max_upper_wick_ratio,
            min_body_ratio=config.min_body_ratio,
        )

        self.exit_signals = ExitSignalGenerator(
            enable_time_stop=config.enable_time_stop,
            time_stop_bars=config.time_stop_bars,
            time_stop_momentum_threshold=config.time_stop_momentum_threshold,
            stop_loss_atr_multiplier=config.stop_loss_atr_multiplier,
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

        # 市场狂热度监控
        self.current_funding_rate: float | None = None
        self.funding_rate_annual: float | None = None
        self.market_euphoria_level: str = "NORMAL"
        self.euphoria_reduced: bool = False

        # 资金费率熔断器（仅在 sandbox/live 模式启用）
        self.funding_monitor: FundingRateMonitor | None = None
        self.circuit_breaker: CircuitBreakerManager | None = None
        try:
            # 尝试初始化熔断器（如果在 sandbox/live 环境）
            self.funding_monitor = FundingRateMonitor()
            self.circuit_breaker = CircuitBreakerManager(
                funding_monitor=self.funding_monitor,
                fallback_threshold_annual=config.funding_rate_warning_annual,
                circuit_breaker_annual=config.funding_rate_danger_annual,
            )
            self.log.info(
                f"资金费率熔断器已启用: "
                f"现货回退阈值={config.funding_rate_warning_annual}%, "
                f"熔断阈值={config.funding_rate_danger_annual}%"
            )
        except Exception as e:
            # 回测模式或无网络环境，熔断器不可用
            self.log.warning(f"资金费率熔断器初始化失败（回测模式下正常）: {e}")
            self.funding_monitor = None
            self.circuit_breaker = None

        # 持仓跟踪（仅做多）
        self.entry_price: Decimal | None = None
        self.quantity: Decimal | None = None
        self.entry_bar_count = 0
        self.highest_high: float | None = None
        self.trailing_stop: float | None = None  # Chandelier Exit 追踪止损线

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
            "price_below_sma": 0,
            "rs_weak": 0,
            "volume_low": 0,
            "keltner_no_breakout": 0,
            "wick_ratio": 0,
            "body_quality": 0,
            "passed_all": 0,
        }
        # 防止内存泄漏：定期重置统计计数器
        self._stats_reset_threshold = 1_000_000  # 每处理 100 万根 K 线重置一次

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

        self.log.info(f"\n{self._LOG_SEPARATOR}")
        self.log.info(f"Filter Statistics for {symbol}")
        self.log.info(f"{self._LOG_SEPARATOR}")
        self.log.info(f"Total bars processed: {total}")
        self.log.info(f"{self._LOG_SUBSEPARATOR}")

        # 计算每个过滤器的拦截率
        filters = [
            ("Not in Universe", "not_in_universe"),
            ("Price < SMA(200)", "price_below_sma"),
            ("RS Weak", "rs_weak"),
            ("Volume Low", "volume_low"),
            ("Keltner No Breakout", "keltner_no_breakout"),
            ("Wick Ratio", "wick_ratio"),
            ("Body Quality", "body_quality"),
        ]

        for name, key in filters:
            count = self.filter_stats[key]
            pct = (count / total * 100) if total > 0 else 0
            self.log.info(f"{name:25s}: {count:6d} ({pct:5.2f}%)")

        passed = self.filter_stats["passed_all"]
        passed_pct = (passed / total * 100) if total > 0 else 0
        self.log.info(f"{self._LOG_SUBSEPARATOR}")
        self.log.info(f"{'Passed All Filters':25s}: {passed:6d} ({passed_pct:5.2f}%)")
        self.log.info(f"{self._LOG_SEPARATOR}\n")

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
                if pct > (FILTER_BLOCKER_THRESHOLD * 100):  # 拦截率超过阈值的过滤器
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

    def _process_btc_bar(self, bar: Bar) -> None:
        """处理 BTC Bar 数据"""
        close = float(bar.close)

        self.log.debug(
            f"[{self.instrument.symbol}] Processing BTC bar: ts={bar.ts_event}, close={close}"
        )

        # 更新 RS 计算器
        self.rs_calculator.update_benchmark_price(bar.ts_event, close)

    def _handle_long_position_management(self, bar: Bar) -> None:
        """处理做多持仓管理"""
        # 更新持仓期间最高价
        if self.highest_high is None:
            self.highest_high = float(bar.high)
        else:
            self.highest_high = max(self.highest_high, float(bar.high))

        # 更新 Chandelier Exit 追踪止损线（只升不降）
        new_trailing_stop = self.highest_high - (
            self.config.stop_loss_atr_multiplier * self.keltner.atr
        )
        if self.trailing_stop is None:
            self.trailing_stop = new_trailing_stop
        else:
            # 只升不降：只有当新止损线更高时才更新
            self.trailing_stop = max(self.trailing_stop, new_trailing_stop)

        self.entry_bar_count += 1
        self._handle_long_exit(bar)

    def _is_symbol_active(self) -> bool:
        """判断当前币种是否活跃（使用缓存）"""
        return self._is_active_cache

    def _check_entry_conditions(self, bar: Bar) -> bool:
        """检查入场条件"""
        close = float(bar.close)
        volume = float(bar.volume)
        symbol = self.instrument.id.symbol.value

        self.filter_stats["total_bars"] += 1

        # 防止内存泄漏：定期重置统计计数器（避免长时间运行导致整数溢出）
        if self.filter_stats["total_bars"] >= self._stats_reset_threshold:
            self.log.info(
                f"[{symbol}] 重置过滤器统计（已处理 {self.filter_stats['total_bars']} 根 K 线）"
            )
            for key in self.filter_stats:
                self.filter_stats[key] = 0
            # 当前 bar 应该计数
            self.filter_stats["total_bars"] = 1

        # 基本条件
        if self._pending_entry_order:
            self.log.debug(f"[{symbol}] ❌ Pending entry order exists")
            return False

        if not self._is_symbol_active():
            self.filter_stats["not_in_universe"] += 1
            self.log.debug(f"[{symbol}] ❌ Not in Universe")
            return False

        # 市场过滤器
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
        # 特殊情况：如果主标的就是 BTC，跳过 RS 检查（BTC 作为 benchmark 本身）
        if self.instrument.id == self.btc_instrument_id:
            # BTC 作为主标的时，跳过 RS 过滤器（无需与自己比较）
            rs_value = 1.0  # 设为 1.0 表示"总是通过 RS 检查"
            self.log.debug(f"[{symbol}] ✓ BTC as main instrument, RS check skipped")
        else:
            rs_value = self.rs_calculator.calculate_rs()
            if rs_value is None or rs_value <= RS_THRESHOLD:
                self.filter_stats["rs_weak"] += 1
                self.log.debug(f"[{symbol}] ❌ RS not strong: {rs_value}")
                return False
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

        # K线实体质量检测
        if not self.entry_signals.check_body_quality(
            float(bar.open), float(bar.high), float(bar.low), close
        ):
            self.filter_stats["body_quality"] += 1
            self.log.debug(f"[{symbol}] ❌ Body quality check failed")
            return False

        # Squeeze 状态仅用于判断高确信度，不作为入场必要条件
        # 这样可以捕捉更多早期突破机会

        self.filter_stats["passed_all"] += 1
        self.log.info(f"[{symbol}] ✅ All entry conditions passed at {bar.ts_event}!")
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

        # 持仓管理
        if self.portfolio.is_net_long(self.instrument.id):
            self._handle_long_position_management(bar)
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

        # 资金费率熔断器检查（仅在 sandbox/live 模式）
        target_instrument_id = self.instrument.id
        if self.circuit_breaker:
            try:
                # 提取交易对符号（如 "ETHUSDT"）
                symbol = self.instrument.id.symbol.value.replace("-PERP", "")

                # 使用事件循环安全的方式调用异步方法
                import asyncio

                try:
                    # 尝试获取当前事件循环
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # 事件循环正在运行,使用 run_until_complete 会失败
                        # 改为跳过熔断器检查并记录警告
                        self.log.warning(
                            "Circuit breaker check skipped: event loop already running. "
                            "Consider making _handle_entry async or using sync circuit breaker."
                        )
                        decision = None
                    else:
                        # 事件循环未运行,可以安全使用
                        decision = loop.run_until_complete(
                            self.circuit_breaker.evaluate_signal(symbol, str(self.instrument.id))
                        )
                except RuntimeError:
                    # 没有事件循环,创建新的
                    decision = asyncio.run(
                        self.circuit_breaker.evaluate_signal(symbol, str(self.instrument.id))
                    )

                # 如果熔断器检查被跳过,继续正常执行(不做熔断)
                if decision is None:
                    pass  # 继续执行
                # 根据决策结果处理
                elif decision.decision == InstrumentType.REJECT:
                    self.log.warning(f"🚫 熔断器拒绝信号: {symbol} - {decision.reason}")
                    return
                elif decision.decision == InstrumentType.SPOT:
                    # 切换到现货标的
                    spot_instrument_id = InstrumentId.from_str(decision.instrument_id)
                    target_instrument_id = spot_instrument_id
                    self.log.info(
                        f"💱 现货替代: {symbol} - {decision.reason}, "
                        f"切换到 {decision.instrument_id}"
                    )
                else:
                    # 正常执行永续合约
                    self.log.debug(f"✅ 正常执行: {symbol} - {decision.reason}")
            except Exception as e:
                # 熔断器失败时采用保守策略：拒绝信号
                self.log.error(f"熔断器检查失败: {e}，拒绝信号")
                return

        # 下单
        order = self.order_factory.market(
            instrument_id=target_instrument_id,
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
        """
        计算仓位大小（波动率平价 + 仓位上限）

        波动率平价原理：
        - 固定风险金额 = 账户权益 × 风险百分比
        - 止损距离 = ATR × 止损倍数
        - 仓位数量 = 固定风险金额 / 止损距离
        - 波动率越高 → 止损距离越大 → 仓位越小

        仓位上限保护：
        - 单个资产最大仓位 = 账户权益 × max_position_risk_pct
        - 防止单一资产过度集中
        """
        account = self.portfolio.account(self.instrument.id.venue)
        if not account:
            return Decimal("0")

        equity = account.balance_total(self.instrument.quote_currency)
        if not equity or equity.as_decimal() <= 0:
            return Decimal("0")

        equity_decimal = equity.as_decimal()
        price = bar.close.as_decimal()

        # 百分比模式（向后兼容）
        if self.config.qty_percent is not None:
            qty_pct = Decimal(str(self.config.qty_percent))
            leverage = Decimal(str(self.config.leverage))
            qty = (equity_decimal * qty_pct * leverage) / price
            return self.instrument.make_qty(qty)

        # 波动率平价模式
        # 验证 ATR 有效性，防止除零和无效计算
        if self.keltner.atr is None or self.keltner.atr < self.config.min_atr:
            self.log.warning(
                f"ATR 无效或过小: {self.keltner.atr}, 最小要求: {self.config.min_atr}, 跳过仓位计算"
            )
            return Decimal("0")

        # 额外检查：ATR 不应超过价格的 50%（数据异常保护）
        # 使用 Decimal 进行精确计算，避免 float 精度损失
        atr_decimal = Decimal(str(self.keltner.atr))
        price_threshold = price * Decimal("0.5")
        if atr_decimal > price_threshold:
            self.log.error(
                f"ATR 异常过大: {atr_decimal} > {price_threshold} (价格的50%), 可能存在数据错误"
            )
            return Decimal("0")

        # 1. 计算止损距离（基于 ATR）
        stop_distance = Decimal(str(self.config.stop_loss_atr_multiplier)) * Decimal(
            str(self.keltner.atr)
        )
        min_stop_distance = price * Decimal(str(self.config.min_stop_distance_pct))

        if stop_distance < min_stop_distance:
            self.log.warning(
                f"ATR过小({self.keltner.atr:.6f})，使用最小止损距离{min_stop_distance}"
            )
            stop_distance = min_stop_distance

        # 2. 根据确信度选择风险百分比
        if high_conviction:
            risk_pct = Decimal(str(self.config.high_conviction_risk_pct))
        else:
            risk_pct = Decimal(str(self.config.base_risk_pct))

        # 3. 计算基于风险的仓位（波动率平价）
        risk_amount = equity_decimal * risk_pct * Decimal(str(self.config.leverage))
        qty_by_risk = risk_amount / stop_distance

        # 4. 计算仓位上限（防止单一资产过度集中）
        max_position_value = equity_decimal * Decimal(str(self.config.max_position_risk_pct))
        max_qty = max_position_value / price

        # 5. 取两者较小值
        qty = min(qty_by_risk, max_qty)

        # 6. 检查最小数量
        min_qty = Decimal(str(self.instrument.size_increment))
        if qty < min_qty:
            self.log.warning(f"计算的仓位数量过小: raw_qty={qty}, min_qty={min_qty}")
            return Decimal("0")

        # 7. 日志记录
        if qty == max_qty:
            self.log.info(
                f"仓位受上限限制: risk_qty={qty_by_risk:.4f}, max_qty={max_qty:.4f}, "
                f"final_qty={qty:.4f} (max_position_risk={self.config.max_position_risk_pct:.1%})"
            )

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

        # 2. Chandelier Exit (使用只升不降的追踪止损线)
        if self.trailing_stop is not None and close < self.trailing_stop:
            self.close_all_positions(self.instrument.id)
            self.log.info(
                f"Chandelier Exit 平仓: "
                f"price={close:.2f}, stop={self.trailing_stop:.2f}, "
                f"highest={self.highest_high:.2f}"
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
        self.trailing_stop = None
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

    def on_position_closed(self, event) -> None:
        """持仓平仓回调"""
        super().on_position_closed(event)
