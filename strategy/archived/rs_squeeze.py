"""
RS-Squeeze Strategy - V3.0 "Early Momentum Explosion"

核心理念:
- RS 加速: 捕捉动能爆发的起点
- 市价入场: 抓住行情启动的第一时间
- 宽松追踪: 追求 Big Win
"""

import bisect
import json
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, Optional, Set

from nautilus_trader.indicators import (
    AverageTrueRange,
    BollingerBands,
    ExponentialMovingAverage,
    KeltnerChannel,
)
from nautilus_trader.model.data import Bar, BarSpecification, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId

from strategy.base import BaseStrategy, BaseStrategyConfig


class RSSqueezeConfig(BaseStrategyConfig):
    """Configuration for RS Squeeze Strategy V3.0"""

    bar_type: str = ""
    benchmark_id: str = "BTCUSDT-PERP.BINANCE"
    benchmark_bar_type: Optional[str] = None
    benchmark_trend_bar_type: Optional[str] = None

    # Universe
    universe_filepath: str = str(
        Path(__file__).parent.parent.resolve() / "data" / "universe_25.json"
    )

    # Indicators
    bb_period: int = 20
    bb_std: float = 2.0
    kc_period_ema: int = 20
    kc_mult: float = 1.4
    atr_period: int = 20
    ema_fast_period: int = 20
    ema_slow_period: int = 200
    ema_trend_exit_period: int = 50

    # Volume
    volume_ma_period: int = 20
    volume_filter_mult: float = 1.6

    # RS Acceleration
    rs_lookback_6h: int = 6
    rs_lookback_12h: int = 12
    rs_lookback_24h: int = 24
    rs_acceleration_gap: float = 0.03
    rs_gap_6h: float = 0.03
    rs_gap_12h: float = 0.05
    rs_gap_24h: float = 0.07

    # Adaptive RS Gap for Mid-Caps
    mid_cap_rank_threshold: int = 50
    mid_cap_rs_gap_addon: float = 0.02

    # Squeeze Tightness
    bb_width_period: int = 100
    bb_width_percentile: float = 0.50

    # Squeeze Maturity
    squeeze_maturity_bars: int = 2

    # Anti-Exhaustion Filter
    anti_exhaustion_enabled: bool = True
    extension_filter_enabled: bool = False

    # Risk Management
    risk_per_trade: float = 0.05
    max_leverage: float = 3.0
    stop_loss_mult: float = 1.5
    breakeven_mult: float = 4.0
    breakeven_offset: float = 0.002
    max_holding_hours: int = 72
    max_margin_usage: float = 0.80

    # Trailing Stop
    trailing_stop_trigger_mult: float = 2.5
    trailing_stop_atr_mult: float = 3.0

    # EMA Trend Exit
    ema_trend_exit_enabled: bool = False

    # Filters
    max_concurrent_positions: int = 5
    cooldown_period_hours: int = 24
    btc_ema_period: int = 200


class RSSqueezeStrategy(BaseStrategy):
    """
    RS-Squeeze V3.0 - Early Momentum Explosion

    Entry: Market order when RS accelerates + Squeeze + Anti-Exhaustion
    Exit: Trailing stop (3.0 * ATR) for big wins
    """

    # Time Constants
    NANOSECONDS_PER_SECOND = 1_000_000_000
    NANOSECONDS_PER_MINUTE = 60 * NANOSECONDS_PER_SECOND
    NANOSECONDS_PER_HOUR = 3600 * NANOSECONDS_PER_SECOND
    DATA_SYNC_TOLERANCE_NS = NANOSECONDS_PER_MINUTE

    # Class variables for statistics collection
    _all_filter_stats: Dict[str, Dict[str, int]] = {}
    _all_trade_metrics: list = []
    _session_id: Optional[str] = None
    _instance_count: int = 0

    def __init__(self, config: RSSqueezeConfig):
        super().__init__(config)

        # Auto-reset class variables for new backtest session
        if RSSqueezeStrategy._instance_count == 0:
            RSSqueezeStrategy._all_filter_stats.clear()
            RSSqueezeStrategy._all_trade_metrics.clear()

        RSSqueezeStrategy._instance_count += 1

        # Identifiers
        self.instrument_id = InstrumentId.from_str(config.instrument_id)

        # Bar Types
        self.bar_type = BarType.from_str(config.bar_type)

        if config.benchmark_bar_type:
            self.benchmark_bar_type = BarType.from_str(config.benchmark_bar_type)
            self.benchmark_id = self.benchmark_bar_type.instrument_id
        else:
            self.benchmark_id = InstrumentId.from_str(config.benchmark_id)
            self.benchmark_bar_type = BarType(self.benchmark_id, self.bar_type.spec)

        if config.benchmark_trend_bar_type:
            self.btc_4h_bar_type = BarType.from_str(config.benchmark_trend_bar_type)
        else:
            self.btc_4h_bar_type = self._get_higher_timeframe_bar_type(
                self.bar_type, self.benchmark_id, "4-HOUR"
            )

        # Indicators
        self.bb = BollingerBands(config.bb_period, config.bb_std)
        self.kc = KeltnerChannel(config.kc_period_ema, config.kc_mult)
        self.atr = AverageTrueRange(config.atr_period)
        self.ema_fast = ExponentialMovingAverage(config.ema_fast_period)
        self.ema_slow = ExponentialMovingAverage(config.ema_slow_period)
        self.ema_trend_exit = ExponentialMovingAverage(config.ema_trend_exit_period)
        self.btc_ema_4h = ExponentialMovingAverage(config.btc_ema_period)

        # Data Buffers
        max_lookback = max(
            config.rs_lookback_6h, config.rs_lookback_12h, config.rs_lookback_24h
        )
        self.asset_closes = deque(maxlen=max_lookback + 1)
        self.benchmark_closes = deque(maxlen=max_lookback + 1)
        self.asset_volumes = deque(maxlen=config.volume_ma_period)
        self.bb_widths = deque(maxlen=config.bb_width_period)

        # Data Sync
        self._last_benchmark_ts: int = 0
        self._last_asset_ts: int = 0

        # State Flags
        self._is_squeeze = False
        self._squeeze_consecutive_bars: int = 0
        self._entry_price: Optional[Decimal] = None
        self._breakeven_triggered = False
        self._trailing_stop_active = False
        self._highest_high_since_entry: Optional[Decimal] = None
        self._last_exit_ts: int = 0
        self._last_entry_ts: int = 0
        self._position_open_ts: int = 0
        self._last_warmup_log_ts: int = 0

        # Universe Rank State
        self._universe_rank_map: Dict[str, Dict[str, int]] = {}
        self._current_rank: int = 0

        # Debug Counters
        self._debug_bar_count: int = 0
        self._debug_signal_checks: int = 0
        self._debug_last_status_log: int = 0

        # Filter Statistics
        self._filter_stats: Dict[str, int] = {
            "data_not_synced": 0,
            "in_cooldown": 0,
            "max_positions": 0,
            "margin_limit": 0,
            "fail_trend": 0,
            "fail_squeeze": 0,
            "fail_squeeze_maturity": 0,
            "fail_bb_width": 0,
            "fail_extension": 0,
            "fail_rs": 0,
            "fail_btc_bear": 0,
            "all_passed": 0,
        }
        self._last_filter_summary_ts: int = 0

        # Entry Metrics
        self._entry_metrics: Dict[str, Dict] = {}

        # Universe State
        self._universe_map: Dict[str, Set[str]] = {}
        self._current_month: str = ""
        self._is_in_universe: bool = False

        # Strategy Control Flag
        self._strategy_disabled: bool = False

        self._load_universe_config()

    def _get_higher_timeframe_bar_type(
        self, base_bar_type: BarType, instrument_id: InstrumentId, period: str
    ) -> BarType:
        """Constructs a higher timeframe BarType."""
        spec_str = str(base_bar_type.spec)
        parts = spec_str.split("-")
        price_type = parts[-1] if len(parts) >= 3 else "MIDPOINT"
        new_spec_str = f"{period}-{price_type}"
        return BarType(instrument_id, BarSpecification.from_str(new_spec_str))

    def _load_universe_config(self):
        """Loads the universe JSON file."""
        if not self.config.universe_filepath:
            return

        try:
            with open(self.config.universe_filepath, "r") as f:
                data = json.load(f)
                for month, symbols_list in data.items():
                    self._universe_map[month] = set(symbols_list)
                    self._universe_rank_map[month] = {
                        sym: idx + 1 for idx, sym in enumerate(symbols_list)
                    }
            self.log.debug(
                f"[{self.instrument_id}] Universe config loaded: {len(self._universe_map)} months."
            )
        except Exception as e:
            self.log.error(f"Failed to load universe file: {e}")

    def _get_current_rank(self) -> int:
        """Returns current instrument rank (1-based), 0 if unknown."""
        if not self._universe_rank_map or not self._current_month:
            return 0

        month_ranks = self._universe_rank_map.get(self._current_month)
        if not month_ranks:
            return 0

        symbol = str(self.instrument_id.symbol)
        base_symbol = symbol.replace("-PERP", "").replace("-SWAP", "")

        if base_symbol in month_ranks:
            return month_ranks[base_symbol]

        usdt_symbol = f"{base_symbol}:USDT"
        if usdt_symbol in month_ranks:
            return month_ranks[usdt_symbol]

        return 0

    @staticmethod
    def _to_decimal(value) -> Decimal:
        """Convert indicator value to Decimal."""
        if hasattr(value, "value"):
            return Decimal(str(value.value))
        return Decimal(str(value))

    def on_start(self):
        """Subscribe to data feeds."""
        super().on_start()

        self.instrument = self.cache.instrument(self.instrument_id)
        if not self.instrument:
            self.log.error(f"Instrument not found in cache: {self.instrument_id}")
            self._strategy_disabled = True
            return

        # Reject BTC self-trading (RS against self is always 0)
        if self.instrument_id == self.benchmark_id:
            self.log.warning(
                f"⚠️ STRATEGY DISABLED: {self.instrument_id} is the benchmark itself. "
                f"RS (Relative Strength) against self is always 0."
            )
            self._strategy_disabled = True
            return

        self.subscribe_bars(self.bar_type)
        self.subscribe_bars(self.benchmark_bar_type)
        self.subscribe_bars(self.btc_4h_bar_type)

    def on_bar(self, bar: Bar):
        """Main event handler."""
        super().on_bar(bar)

        # Early exit if strategy is disabled
        if self._strategy_disabled:
            return

        # A. Handle Benchmark 4H (Trend Filter)
        if bar.bar_type == self.btc_4h_bar_type:
            self.btc_ema_4h.handle_bar(bar)
            return

        # B. Handle Benchmark 1H (RS Calculation)
        if bar.bar_type == self.benchmark_bar_type:
            self.benchmark_closes.append(Decimal(str(bar.close)))
            self._last_benchmark_ts = bar.ts_event
            if self.instrument_id != self.benchmark_id:
                return

        # C. Handle Trading Instrument 1H
        if (
            bar.bar_type.instrument_id == self.instrument_id
            and bar.bar_type.spec == self.bar_type.spec
        ):
            self._last_asset_ts = bar.ts_event
            self._on_instrument_bar(bar)

    def _on_instrument_bar(self, bar: Bar):
        """Core logic for the trading instrument."""
        self._debug_bar_count += 1

        # Update Indicators & Buffers
        self.asset_closes.append(Decimal(str(bar.close)))
        self.asset_volumes.append(Decimal(str(bar.volume)))

        self.bb.handle_bar(bar)
        self.kc.handle_bar(bar)
        self.atr.handle_bar(bar)
        self.ema_fast.handle_bar(bar)
        self.ema_slow.handle_bar(bar)
        self.ema_trend_exit.handle_bar(bar)

        # Update Context
        self._update_universe_status(bar.ts_event)
        self._update_squeeze_status()

        # Check Warmup
        if not self._check_warmup_status():
            return

        # Trading Decision
        if self._has_open_position():
            self._manage_positions(bar)
        elif self._is_in_universe:
            self._check_entry_signal(bar)

    def _check_warmup_status(self) -> bool:
        """Returns True if all required data is ready."""
        max_lookback = max(
            self.config.rs_lookback_6h,
            self.config.rs_lookback_12h,
            self.config.rs_lookback_24h,
        )
        is_ready = (
            self.ema_slow.initialized
            and self.bb.initialized
            and self.kc.initialized
            and len(self.asset_closes) > max_lookback
            and len(self.benchmark_closes) > max_lookback
            and len(self.asset_volumes) >= self.config.volume_ma_period
        )

        if is_ready and self._last_warmup_log_ts == 0:
            self._last_warmup_log_ts = self.clock.timestamp_ns()

        return is_ready

    def _check_data_sync(self) -> bool:
        """Check if Asset and Benchmark data are time-aligned."""
        if self._last_asset_ts == 0 or self._last_benchmark_ts == 0:
            return False

        is_synced = (
            abs(self._last_asset_ts - self._last_benchmark_ts)
            <= self.DATA_SYNC_TOLERANCE_NS
        )

        if is_synced and not hasattr(self, "_sync_logged"):
            self._sync_logged = True

        return is_synced

    def _update_universe_status(self, ts_event: int):
        """Updates _is_in_universe flag based on current month."""
        if not self._universe_map:
            self._is_in_universe = True
            return

        dt = datetime.fromtimestamp(ts_event / 1e9, tz=timezone.utc)
        current_month = dt.strftime("%Y-%m")

        if current_month != self._current_month:
            self._current_month = current_month
            month_symbols = self._universe_map.get(current_month, set())

            symbol = str(self.instrument_id.symbol)
            full_id = str(self.instrument_id)
            base_symbol = symbol.replace("-PERP", "").replace("-SWAP", "")

            is_in = full_id in month_symbols or symbol in month_symbols

            if not is_in:
                for valid_sym in month_symbols:
                    valid_base = valid_sym.split(":")[0]
                    if base_symbol == valid_base:
                        is_in = True
                        break

            self._is_in_universe = is_in

    def _update_squeeze_status(self):
        """Calculate Squeeze state (BB inside KC)."""
        if not self.bb.initialized or not self.kc.initialized:
            return

        bb_upper = self._to_decimal(self.bb.upper)
        bb_lower = self._to_decimal(self.bb.lower)
        bb_middle = self._to_decimal(self.bb.middle)
        kc_upper = self._to_decimal(self.kc.upper)
        kc_lower = self._to_decimal(self.kc.lower)

        if bb_middle > 0:
            bb_width = (bb_upper - bb_lower) / bb_middle
            self.bb_widths.append(bb_width)

        current_squeeze = (bb_upper < kc_upper) and (bb_lower > kc_lower)

        if current_squeeze:
            self._squeeze_consecutive_bars += 1
        else:
            self._squeeze_consecutive_bars = 0

        self._is_squeeze = current_squeeze

    def _is_squeeze_mature(self) -> bool:
        """Check if squeeze is mature (consecutive N bars)."""
        return self._squeeze_consecutive_bars >= self.config.squeeze_maturity_bars

    def _check_extension_filter(self, current_price: Decimal) -> bool:
        """Check if price is not overextended from EMA."""
        if not self.config.extension_filter_enabled:
            return True

        if not self.ema_fast.initialized or not self.atr.initialized:
            return True

        ema_fast = self._to_decimal(self.ema_fast.value)
        atr = self._to_decimal(self.atr.value)

        if current_price <= 0:
            return True

        atr_relative = atr / current_price
        max_extension = ema_fast * (Decimal("1") + atr_relative)

        return current_price < max_extension

    def _is_bb_width_tight(self) -> bool:
        """Check if BB Width is in lower percentile."""
        if len(self.bb_widths) < self.config.bb_width_period:
            return True

        current_width = self.bb_widths[-1]
        sorted_widths = sorted(self.bb_widths)

        position = bisect.bisect_left(sorted_widths, current_width)
        percentile = position / len(sorted_widths)

        return percentile <= self.config.bb_width_percentile

    def _calculate_return(self, closes: deque, lookback: int) -> Decimal:
        """Calculate return over lookback period."""
        if len(closes) < lookback + 1:
            return Decimal("0")

        close_now = closes[-1]
        close_ago = closes[-(lookback + 1)]

        if close_ago == 0:
            return Decimal("0")

        return (close_now - close_ago) / close_ago

    def _check_anti_exhaustion(self, current_price: Decimal) -> bool:
        """Check if price is below Upper Bollinger Band."""
        if not self.config.anti_exhaustion_enabled:
            return True

        if not self.bb.initialized:
            return True

        bb_upper = self._to_decimal(self.bb.upper)
        return current_price < bb_upper

    def _check_rs_acceleration(self) -> tuple[bool, str, Decimal, Decimal]:
        """
        V3.0 RS Acceleration Detection.

        Entry if:
        1. Asset_Return_6h > BTC_Return_6h + rs_acceleration_gap (3%)
        2. Asset_Return_6h > Asset_Return_24h (momentum accelerating)
        """
        if len(self.asset_closes) < self.config.rs_lookback_24h + 1:
            return (False, "insufficient_data", Decimal("0"), Decimal("0"))
        if len(self.benchmark_closes) < self.config.rs_lookback_6h + 1:
            return (False, "insufficient_benchmark_data", Decimal("0"), Decimal("0"))

        asset_return_6h = self._calculate_return(
            self.asset_closes, self.config.rs_lookback_6h
        )
        asset_return_24h = self._calculate_return(
            self.asset_closes, self.config.rs_lookback_24h
        )
        btc_return_6h = self._calculate_return(
            self.benchmark_closes, self.config.rs_lookback_6h
        )

        rs_gap_6h = asset_return_6h - btc_return_6h

        # Adaptive RS Gap for mid-caps
        rank = self._get_current_rank()
        gap_addon = Decimal("0")
        if rank > 0 and rank > self.config.mid_cap_rank_threshold:
            gap_addon = Decimal(str(self.config.mid_cap_rs_gap_addon))

        required_gap = Decimal(str(self.config.rs_acceleration_gap)) + gap_addon

        if rs_gap_6h <= required_gap:
            return (False, "rs_gap_insufficient", asset_return_6h, rs_gap_6h)

        if asset_return_6h <= asset_return_24h:
            return (False, "momentum_exhausting", asset_return_6h, rs_gap_6h)

        return (True, "acceleration_confirmed", asset_return_6h, rs_gap_6h)

    def _check_laddered_rs(self) -> tuple[bool, str]:
        """Laddered RS filter (legacy, for compatibility)."""
        max_lookback = max(
            self.config.rs_lookback_6h,
            self.config.rs_lookback_12h,
            self.config.rs_lookback_24h,
        )

        if len(self.asset_closes) < max_lookback + 1:
            return (False, "insufficient_data")
        if len(self.benchmark_closes) < max_lookback + 1:
            return (False, "insufficient_benchmark_data")

        rank = self._get_current_rank()
        gap_addon = Decimal("0")
        if rank > 0 and rank > self.config.mid_cap_rank_threshold:
            gap_addon = Decimal(str(self.config.mid_cap_rs_gap_addon))

        windows = [
            (self.config.rs_lookback_6h, self.config.rs_gap_6h, "6h"),
            (self.config.rs_lookback_12h, self.config.rs_gap_12h, "12h"),
            (self.config.rs_lookback_24h, self.config.rs_gap_24h, "24h"),
        ]

        for lookback, gap_threshold, window_name in windows:
            asset_return = self._calculate_return(self.asset_closes, lookback)
            btc_return = self._calculate_return(self.benchmark_closes, lookback)
            rs_gap = asset_return - btc_return
            required_gap = Decimal(str(gap_threshold)) + gap_addon

            if rs_gap > required_gap:
                return (True, window_name)

        return (False, "none")

    def _calculate_avg_volume(self) -> Decimal:
        """Calculate average volume."""
        if len(self.asset_volumes) == 0:
            return Decimal("0")
        return sum(self.asset_volumes) / Decimal(len(self.asset_volumes))

    def _has_open_position(self) -> bool:
        return len(self.cache.positions_open(instrument_id=self.instrument_id)) > 0

    def _check_entry_signal(self, bar: Bar):
        """Evaluate market conditions for Long Entry."""
        self._debug_signal_checks += 1

        if self._has_open_position():
            return

        # Data Sync Check
        if not self._check_data_sync():
            self._filter_stats["data_not_synced"] += 1
            return

        # Cooldown Check
        cooldown_ns = self.config.cooldown_period_hours * self.NANOSECONDS_PER_HOUR
        if bar.ts_event < (self._last_entry_ts + cooldown_ns):
            self._filter_stats["in_cooldown"] += 1
            return

        # Max Concurrency Check
        open_positions = len(self.cache.positions_open())
        if open_positions >= self.config.max_concurrent_positions:
            self._filter_stats["max_positions"] += 1
            return

        # Margin Usage Check
        account = self._get_account()
        if account:
            equity = account.balance(self.instrument.quote_currency).total.as_decimal()
            margin_used = account.balance(
                self.instrument.quote_currency
            ).locked.as_decimal()
            if equity > Decimal("0"):
                margin_ratio = margin_used / equity
                if margin_ratio >= Decimal(str(self.config.max_margin_usage)):
                    self._filter_stats["margin_limit"] += 1
                    return

        # V3.0 Lift-off Trigger Detection
        current_price = Decimal(str(bar.close))
        ema_slow = Decimal(str(self.ema_slow.value))

        # A. Trend Filter: Price > EMA200
        if current_price <= ema_slow:
            self._filter_stats["fail_trend"] += 1
            return

        # B. Squeeze Filter
        if not self._is_squeeze:
            self._filter_stats["fail_squeeze"] += 1
            return

        # B.1 Squeeze Maturity Filter
        if not self._is_squeeze_mature():
            self._filter_stats["fail_squeeze_maturity"] += 1
            return

        # C. RS Acceleration Filter
        rs_passed, rs_reason, asset_return_6h, rs_gap_6h = self._check_rs_acceleration()
        if not rs_passed:
            self._filter_stats["fail_rs"] += 1
            return

        # D. Anti-Exhaustion Filter
        if not self._check_anti_exhaustion(current_price):
            self._filter_stats["fail_extension"] += 1
            return

        # E. Benchmark 4H Filter
        if self.btc_ema_4h.initialized:
            btc_bar = self.cache.bar(self.btc_4h_bar_type)
            if btc_bar:
                btc_price = Decimal(str(btc_bar.close))
                btc_ema = Decimal(str(self.btc_ema_4h.value))
                if btc_price < btc_ema:
                    self._filter_stats["fail_btc_bear"] += 1
                    return

        # All conditions passed
        self._filter_stats["all_passed"] += 1

        bb_width_pct = self._get_bb_width_percentile()
        rs_score = self._calculate_rs_score()

        current_volume = Decimal(str(bar.volume))
        avg_volume = self._calculate_avg_volume()
        volume_mult = Decimal("0")
        if avg_volume > 0:
            volume_mult = current_volume / avg_volume

        self.log.info(
            f"🚀 LIFT-OFF DETECTED for {self.instrument_id}! "
            f"Price={current_price:.2f}, RS_Reason={rs_reason}, "
            f"Asset_6h_Ret={asset_return_6h:.4f}, RS_Gap_6h={rs_gap_6h:.4f}, "
            f"RS_Score={rs_score:.4f}, BB_Width_Pct={bb_width_pct:.2f}, "
            f"Volume_Mult={volume_mult:.2f}"
        )

        self._execute_entry(
            current_price,
            rs_reason,
            bar.ts_event,
            rs_score,
            bb_width_pct,
            volume_mult,
        )

    def _calculate_rs_score(self) -> Decimal:
        """Calculate max RS Gap across all windows."""
        max_lookback = max(
            self.config.rs_lookback_6h,
            self.config.rs_lookback_12h,
            self.config.rs_lookback_24h,
        )

        if len(self.asset_closes) < max_lookback + 1:
            return Decimal("0")
        if len(self.benchmark_closes) < max_lookback + 1:
            return Decimal("0")

        max_rs_gap = Decimal("0")
        for lookback in [
            self.config.rs_lookback_6h,
            self.config.rs_lookback_12h,
            self.config.rs_lookback_24h,
        ]:
            asset_return = self._calculate_return(self.asset_closes, lookback)
            btc_return = self._calculate_return(self.benchmark_closes, lookback)
            rs_gap = asset_return - btc_return
            if rs_gap > max_rs_gap:
                max_rs_gap = rs_gap

        return max_rs_gap

    def _get_bb_width_percentile(self) -> Decimal:
        """Get BB Width percentile position."""
        if len(self.bb_widths) < 2:
            return Decimal("0.5")

        current_width = self.bb_widths[-1]
        sorted_widths = sorted(self.bb_widths)

        position = bisect.bisect_left(sorted_widths, current_width)

        return Decimal(str(position / len(sorted_widths)))

    def _execute_entry(
        self,
        current_price: Decimal,
        rs_window: str,
        ts_event: int,
        rs_score: Decimal = Decimal("0"),
        bb_width_pct: Decimal = Decimal("0"),
        volume_mult: Decimal = Decimal("0"),
    ):
        """Execute entry orders with risk management."""
        atr = Decimal(str(self.atr.value))
        risk_dist = atr * Decimal(str(self.config.stop_loss_mult))

        account = self._get_account()
        if not account:
            return

        equity = account.balance(self.instrument.quote_currency).total.as_decimal()

        if equity <= Decimal("0"):
            self.log.warning(
                f"⚠️ NEGATIVE BALANCE: equity={equity}, refusing to open position"
            )
            return

        risk_amt = equity * Decimal(str(self.config.risk_per_trade))

        if risk_dist <= 0:
            return
        raw_qty = risk_amt / risk_dist

        # Leverage cap
        max_leverage = Decimal(str(self.config.max_leverage))
        notional_value = raw_qty * current_price
        effective_leverage = notional_value / equity

        if effective_leverage > max_leverage:
            raw_qty = (equity * max_leverage) / current_price

        try:
            qty = self.instrument.make_qty(raw_qty)
            if qty <= 0:
                return
        except Exception as e:
            self.log.warning(f"Qty Calc Error: {e}")
            return

        # Place Orders
        entry_order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=qty,
        )
        self.submit_order(entry_order)

        sl_price_raw = current_price - risk_dist
        sl_price = self.instrument.make_price(sl_price_raw)

        sl_order = self.order_factory.stop_market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.SELL,
            quantity=qty,
            trigger_price=sl_price,
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(sl_order)

        # Update State
        self._entry_price = current_price
        self._breakeven_triggered = False
        self._trailing_stop_active = False
        self._highest_high_since_entry = current_price
        self._last_entry_ts = ts_event
        self._position_open_ts = ts_event

        # Record metrics
        self._entry_metrics[str(self.instrument_id)] = {
            "asset": str(self.instrument_id.symbol),
            "entry_price": float(current_price),
            "rs_window": rs_window,
            "rs_score": float(rs_score),
            "bb_width_pct": float(bb_width_pct),
            "volume_mult": float(volume_mult),
            "entry_ts": ts_event,
        }

    def _manage_positions(self, bar: Bar):
        """Manage open positions."""
        positions = self.cache.positions_open(instrument_id=self.instrument_id)
        if not positions:
            return
        position = positions[0]

        current_price = Decimal(str(bar.close))
        current_high = Decimal(str(bar.high))

        if self._highest_high_since_entry is not None:
            self._highest_high_since_entry = max(
                self._highest_high_since_entry, current_high
            )
        else:
            self._highest_high_since_entry = current_high

        # Time Protection: Force close after max holding hours
        if self._position_open_ts > 0:
            holding_duration_ns = bar.ts_event - self._position_open_ts
            max_holding_ns = self.config.max_holding_hours * self.NANOSECONDS_PER_HOUR
            if holding_duration_ns >= max_holding_ns:
                self.cancel_all_orders(self.instrument_id)
                close_order = self.order_factory.market(
                    instrument_id=self.instrument_id,
                    order_side=OrderSide.SELL,
                    quantity=position.quantity,
                )
                self.submit_order(close_order)
                self._position_open_ts = 0
                return

        # Emergency Stop: Force close if price breaches SL
        if self._entry_price and self.atr.initialized and position.is_long:
            atr = Decimal(str(self.atr.value))
            stop_loss_price = self._entry_price - (
                atr * Decimal(str(self.config.stop_loss_mult))
            )

            if current_price <= stop_loss_price:
                self.cancel_all_orders(self.instrument_id)
                close_order = self.order_factory.market(
                    instrument_id=self.instrument_id,
                    order_side=OrderSide.SELL,
                    quantity=position.quantity,
                )
                self.submit_order(close_order)
                return

        # Trailing Stop
        if self._entry_price and self.atr.initialized and position.is_long:
            atr = Decimal(str(self.atr.value))
            profit = current_price - self._entry_price
            trigger_profit = atr * Decimal(str(self.config.trailing_stop_trigger_mult))

            if profit >= trigger_profit:
                if self._highest_high_since_entry:
                    trailing_sl_price = self._highest_high_since_entry - (
                        atr * Decimal(str(self.config.trailing_stop_atr_mult))
                    )

                    breakeven_price = self._entry_price * (
                        1 + Decimal(str(self.config.breakeven_offset))
                    )
                    trailing_sl_price = max(trailing_sl_price, breakeven_price)

                    if not self._trailing_stop_active:
                        self._trailing_stop_active = True

                    new_sl_price = self.instrument.make_price(trailing_sl_price)

                    self.cancel_all_orders(self.instrument_id)
                    sl_order = self.order_factory.stop_market(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.SELL,
                        quantity=position.quantity,
                        trigger_price=new_sl_price,
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(sl_order)

        # EMA Trend Exit (optional, disabled by default)
        if getattr(self.config, "ema_trend_exit_enabled", False):
            if self.ema_trend_exit.initialized and position.is_long:
                ema_trend_exit = Decimal(str(self.ema_trend_exit.value))
                if current_price < ema_trend_exit:
                    if self._entry_price and current_price > self._entry_price:
                        self.cancel_all_orders(self.instrument_id)
                        close_order = self.order_factory.market(
                            instrument_id=self.instrument_id,
                            order_side=OrderSide.SELL,
                            quantity=position.quantity,
                        )
                        self.submit_order(close_order)
                        return

    def _get_account(self):
        """Find account with quote currency balance."""
        accounts = self.cache.accounts()
        if not accounts:
            return None
        for acc in accounts:
            balance = acc.balance(self.instrument.quote_currency)
            if balance:
                return acc
        return accounts[0]

    def on_order_filled(self, event):
        super().on_order_filled(event)

    def on_order_canceled(self, event):
        super().on_order_canceled(event)

    def on_position_closed(self, event):
        super().on_position_closed(event)
        self._last_exit_ts = self.clock.timestamp_ns()

        instrument_key = str(self.instrument_id)
        if instrument_key in self._entry_metrics:
            metrics = self._entry_metrics[instrument_key]
            entry_price = Decimal(str(metrics["entry_price"]))
            exit_price = (
                Decimal(str(event.avg_px_close))
                if hasattr(event, "avg_px_close")
                else Decimal("0")
            )
            pnl_pct = Decimal("0")
            if entry_price > 0 and exit_price > 0:
                pnl_pct = (exit_price - entry_price) / entry_price * 100

            result = "WINNER" if pnl_pct > 0 else "LOSER"

            trade_record = {
                "asset": metrics["asset"],
                "result": result,
                "pnl_pct": float(pnl_pct),
                "entry_rs_score": metrics["rs_score"],
                "entry_bb_width_pct": metrics["bb_width_pct"],
                "entry_volume_mult": metrics["volume_mult"],
            }
            RSSqueezeStrategy._all_trade_metrics.append(trade_record)

            del self._entry_metrics[instrument_key]

    def on_stop(self):
        if self._debug_signal_checks > 0:
            RSSqueezeStrategy._all_filter_stats[str(self.instrument_id)] = {
                "signal_checks": self._debug_signal_checks,
                **self._filter_stats.copy(),
            }

        self.cancel_all_orders(self.instrument_id)
        self.close_all_positions(self.instrument_id)

    @classmethod
    def get_filter_stats_summary(cls) -> Dict[str, Dict[str, int]]:
        return cls._all_filter_stats.copy()

    @classmethod
    def get_trade_metrics(cls) -> list:
        return cls._all_trade_metrics.copy()

    @classmethod
    def reset_class_stats(cls):
        cls._all_filter_stats.clear()
        cls._all_trade_metrics.clear()
        cls._instance_count = 0

    @classmethod
    def print_filter_stats_report(cls):
        """Print filter statistics summary report."""
        if not cls._all_filter_stats:
            return

        total_stats = {
            "signal_checks": 0,
            "data_not_synced": 0,
            "in_cooldown": 0,
            "max_positions": 0,
            "margin_limit": 0,
            "fail_trend": 0,
            "fail_squeeze": 0,
            "fail_squeeze_maturity": 0,
            "fail_bb_width": 0,
            "fail_extension": 0,
            "fail_rs": 0,
            "fail_btc_bear": 0,
            "all_passed": 0,
        }

        for inst_id, stats in cls._all_filter_stats.items():
            for key in total_stats:
                total_stats[key] += stats.get(key, 0)

        print("\n" + "=" * 70)
        print("📊 FILTER STATISTICS SUMMARY (V3.0 Early Momentum Explosion)")
        print("=" * 70)
        print(f"Total Instruments: {len(cls._all_filter_stats)}")
        print(f"Total Signal Checks: {total_stats['signal_checks']:,}")
        print("-" * 70)
        print("PRE-CHECKS:")
        print(f"  data_not_synced:      {total_stats['data_not_synced']:>8,}")
        print(f"  in_cooldown:          {total_stats['in_cooldown']:>8,}")
        print(f"  max_positions:        {total_stats['max_positions']:>8,}")
        print(f"  margin_limit:         {total_stats['margin_limit']:>8,}")
        print("-" * 70)
        print("CORE FILTERS:")
        print(f"  fail_trend:           {total_stats['fail_trend']:>8,}")
        print(f"  fail_squeeze:         {total_stats['fail_squeeze']:>8,}")
        print(f"  fail_squeeze_maturity:{total_stats['fail_squeeze_maturity']:>8,}")
        print(f"  fail_rs:              {total_stats['fail_rs']:>8,}")
        print(f"  fail_extension:       {total_stats['fail_extension']:>8,}")
        print(f"  fail_btc_bear:        {total_stats['fail_btc_bear']:>8,}")
        print("-" * 70)
        print(f"🚀 ALL_PASSED:          {total_stats['all_passed']:>8,}")
        print("=" * 70)

        if cls._all_trade_metrics:
            winners = [t for t in cls._all_trade_metrics if t["result"] == "WINNER"]
            losers = [t for t in cls._all_trade_metrics if t["result"] == "LOSER"]

            print("\n" + "=" * 70)
            print("📈 TRADE METRICS ANALYSIS")
            print("=" * 70)
            print(
                f"Total: {len(cls._all_trade_metrics)} | "
                f"Winners: {len(winners)} | Losers: {len(losers)}"
            )

            if winners:
                avg_pnl_win = sum(t["pnl_pct"] for t in winners) / len(winners)
            else:
                avg_pnl_win = 0
            if losers:
                avg_pnl_lose = sum(t["pnl_pct"] for t in losers) / len(losers)
            else:
                avg_pnl_lose = 0

            print(f"\nAvg Winner: {avg_pnl_win:+.2f}%")
            print(f"Avg Loser:  {avg_pnl_lose:+.2f}%")
            if losers and avg_pnl_lose != 0:
                rr_ratio = abs(avg_pnl_win / avg_pnl_lose)
                print(f"R/R Ratio:  {rr_ratio:.2f}")

            print("=" * 70 + "\n")

    def on_reset(self):
        super().on_reset()
        self.bb.reset()
        self.kc.reset()
        self.atr.reset()
        self.ema_fast.reset()
        self.ema_slow.reset()
        self.ema_trend_exit.reset()
        self.btc_ema_4h.reset()
        self.asset_closes.clear()
        self.benchmark_closes.clear()
        self.asset_volumes.clear()
        self.bb_widths.clear()
        self._is_squeeze = False
        self._squeeze_consecutive_bars = 0
        self._entry_price = None
        self._breakeven_triggered = False
        self._trailing_stop_active = False
        self._highest_high_since_entry = None
        self._last_benchmark_ts = 0
        self._last_asset_ts = 0
        self._last_entry_ts = 0
        self._debug_bar_count = 0
        self._debug_signal_checks = 0
        self._debug_last_status_log = 0
        for key in self._filter_stats:
            self._filter_stats[key] = 0
        self._entry_metrics.clear()
