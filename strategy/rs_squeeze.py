import json
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Optional, Set

from nautilus_trader.config import StrategyConfig

# Indicators
from nautilus_trader.indicators import (
    AverageTrueRange,
    BollingerBands,
    ExponentialMovingAverage,
    KeltnerChannel,
)
from nautilus_trader.model.data import Bar, BarSpecification, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.position import Position
from nautilus_trader.trading.strategy import Strategy

from strategy.base import BaseStrategy, BaseStrategyConfig


class RSSqueezeConfig(BaseStrategyConfig):
    """
    Configuration for RS Squeeze Strategy.

    This config defines parameters for a specific instrument instance,
    while also handling global settings like Universe and Benchmark.
    """

    bar_type: str = ""
    benchmark_id: str = "BTCUSDT.BINANCE"

    # --- Universe Logic ---
    # Path to a JSON file mapping "YYYY-MM" -> [Symbol List]
    universe_filepath: Optional[str] = None

    # --- Indicator Params ---
    bb_period: int = 20
    bb_std: float = 2.0
    kc_period_ema: int = 20
    kc_mult: float = 1.5
    atr_period: int = 20
    ema_fast_period: int = 20
    ema_slow_period: int = 200

    # --- Relative Strength (RS) Params ---
    rs_lookback: int = 24  # Lookback for RS calculation (e.g. 24 hours)
    rs_threshold: float = 1.05  # RS must be > 1.05

    # --- Risk Management ---
    risk_per_trade: float = 0.03  # 3% risk per trade
    stop_loss_mult: float = 2.0  # Initial SL distance in ATR
    breakeven_mult: float = 2.5  # Move to BE when profit > 2.5 * ATR
    breakeven_offset: float = 0.002  # BE Offset (Entry + 0.2%)

    # --- Filters ---
    max_concurrent_positions: int = 3
    cooldown_period_hours: int = 24
    squeeze_threshold_mult: float = 0.9  # BB Width must be < 0.9 * KC Width
    btc_ema_period: int = 200  # Period for BTC 4H Trend Filter


class RSSqueezeStrategy(BaseStrategy):
    """
    Refactored RS-Squeeze Strategy.

    Logic Overview:
    1.  **Warmup**: Wait for indicators (EMA, BB, KC) and History buffers to fill.
    2.  **Universe Check**: Only trade if the instrument is in the allowed list for the current month.
    3.  **Market State**:
        -   Calculate 'Squeeze' (Low Volatility): Bollinger Width < Keltner Width.
        -   Calculate 'RS' (Relative Strength): Asset Performance / Benchmark Performance over 24h.
    4.  **Entry Signal (Long Only)**:
        -   Price > EMA200 (Uptrend).
        -   In Squeeze State.
        -   RS > Threshold (Outperforming BTC).
        -   Breakout of recent Highs.
        -   BTC 4H > EMA200 (Market Regime Filter).
    5.  **Exit Logic**:
        -   Stop Loss (ATR based).
        -   Trailing Stop to Breakeven.
        -   Trend Exit (Close < EMA20).
    """

    def __init__(self, config: RSSqueezeConfig):
        super().__init__(config)

        # --- Identifiers ---
        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        self.benchmark_id = InstrumentId.from_str(config.benchmark_id)

        # --- Bar Types ---
        # 1. Trading Bar (e.g. 1-HOUR)
        self.bar_type = BarType.from_str(config.bar_type)

        # 2. Benchmark Bar (Same timeframe as trading, e.g. 1-HOUR) for RS Calculation
        self.benchmark_bar_type = BarType(self.benchmark_id, self.bar_type.spec)

        # 3. Benchmark Higher TF Bar (e.g. 4-HOUR) for Regime Filter
        # We construct this dynamically to match the feed style (Midpoint/Last/Trade)
        self.btc_4h_bar_type = self._get_higher_timeframe_bar_type(
            self.bar_type, self.benchmark_id, "4-HOUR"
        )

        # --- Indicators ---
        self.bb = BollingerBands(config.bb_period, config.bb_std)
        self.kc = KeltnerChannel(config.kc_period_ema, config.kc_mult)
        self.atr = AverageTrueRange(config.atr_period)
        self.ema_fast = ExponentialMovingAverage(config.ema_fast_period)
        self.ema_slow = ExponentialMovingAverage(config.ema_slow_period)
        self.btc_ema_4h = ExponentialMovingAverage(config.btc_ema_period)

        # --- Data Buffers ---
        # +1 to calculate returns (need T-24 close to compare with T-0)
        self.asset_closes = deque(maxlen=config.rs_lookback + 1)
        self.benchmark_closes = deque(maxlen=config.rs_lookback + 1)
        self.asset_highs = deque(maxlen=5)  # Keep a few highs for breakout check

        # --- State Flags ---
        self._is_squeeze = False
        self._entry_price: Optional[Decimal] = None
        self._breakeven_triggered = False
        self._last_exit_ts: int = 0  # Timestamp in nanoseconds
        self._last_warmup_log_ts: int = 0

        # --- Universe State ---
        self._universe_map: Dict[str, Set[str]] = {}
        self._current_month: str = ""
        self._is_in_universe: bool = False

        # Initial Load
        self._load_universe_config()

    def _get_higher_timeframe_bar_type(
        self, base_bar_type: BarType, instrument_id: InstrumentId, period: str
    ) -> BarType:
        """Constructs a higher timeframe BarType based on the base specification."""
        spec_str = str(base_bar_type.spec)
        parts = spec_str.split("-")
        # Example: 1-MINUTE-LAST -> 4-HOUR-LAST
        price_type = parts[-1] if len(parts) >= 3 else "MIDPOINT"
        new_spec_str = f"{period}-{price_type}"
        return BarType(instrument_id, BarSpecification.from_str(new_spec_str))

    def _load_universe_config(self):
        """Loads the universe JSON file into memory."""
        if not self.config.universe_filepath:
            return

        try:
            with open(self.config.universe_filepath, "r") as f:
                data = json.load(f)
                # Optimize: Convert lists to sets for O(1) lookup
                self._universe_map = {k: set(v) for k, v in data.items()}
            self.log.info(
                f"[{self.instrument_id}] Universe config loaded: {len(self._universe_map)} months."
            )
        except Exception as e:
            self.log.error(f"Failed to load universe file: {e}")

    def on_start(self):
        """Subscribe to data feeds."""
        super().on_start()

        self.instrument = self.cache.instrument(self.instrument_id)
        if not self.instrument:
            self.log.error(f"Instrument not found in cache: {self.instrument_id}")
            self.stop()
            return

        # 1. Trading Instrument (e.g. SOLUSDT 1H)
        self.subscribe_bars(self.bar_type)

        # 2. Benchmark for RS (e.g. BTCUSDT 1H)
        self.subscribe_bars(self.benchmark_bar_type)

        # 3. Benchmark for Trend (e.g. BTCUSDT 4H)
        self.subscribe_bars(self.btc_4h_bar_type)

        self.log.info(
            f"Strategy started for {self.instrument_id}. Benchmark: {self.benchmark_id}"
        )

    def on_bar(self, bar: Bar):
        """
        Main Event Handler.
        Dispatches logic based on the incoming Bar's type.
        """
        super().on_bar(bar)

        # A. Handle Benchmark 4H (Trend Filter)
        if bar.bar_type == self.btc_4h_bar_type:
            self.btc_ema_4h.handle_bar(bar)
            return

        # B. Handle Benchmark 1H (RS Calculation)
        if bar.bar_type == self.benchmark_bar_type:
            self.benchmark_closes.append(Decimal(str(bar.close)))
            # IMPORTANT: If we are trading BTC, we must NOT return here.
            # We must proceed to process it as a trading instrument too.
            if self.instrument_id != self.benchmark_id:
                return

        # C. Handle Trading Instrument 1H
        # Note: Check strict equality of instrument_id and spec to avoid cross-talk
        if (
            bar.bar_type.instrument_id == self.instrument_id
            and bar.bar_type.spec == self.bar_type.spec
        ):
            self._on_instrument_bar(bar)

    def _on_instrument_bar(self, bar: Bar):
        """
        Core logic for the trading instrument.
        Called once per bar (e.g. hourly).
        """

        # 1. Update Indicators & Buffers
        self.asset_closes.append(Decimal(str(bar.close)))
        self.asset_highs.append(Decimal(str(bar.high)))

        self.bb.handle_bar(bar)
        self.kc.handle_bar(bar)
        self.atr.handle_bar(bar)
        self.ema_fast.handle_bar(bar)
        self.ema_slow.handle_bar(bar)

        # 2. Update Context (Universe & Squeeze State)
        self._update_universe_status(bar.ts_event)
        self._update_squeeze_status()

        # 3. Check Warmup
        if not self._check_warmup_status():
            return

        # 4. Trading Decision Logic
        if self._has_open_position():
            self._manage_positions(bar)
        elif self._is_in_universe:
            # We only look for new entries if we are in the universe this month
            self._check_entry_signal(bar)

    def _check_warmup_status(self) -> bool:
        """
        Returns True if all required data is ready.
        Logs status periodically if warming up.
        """
        # Note: BTC 4H EMA is soft-required (code handles if it's not ready),
        # so we don't block the whole strategy on it.
        is_ready = (
            self.ema_slow.initialized
            and self.bb.initialized
            and self.kc.initialized
            and len(self.asset_closes) > self.config.rs_lookback
            and len(self.benchmark_closes) > self.config.rs_lookback
        )

        if not is_ready:
            # Throttle logs to once per minute (simulated time)
            now = self.clock.timestamp_ns()
            if now - self._last_warmup_log_ts > 60 * 1e9:
                self._last_warmup_log_ts = now
                missing = []
                if not self.ema_slow.initialized:
                    missing.append(
                        f"EMA_Slow({self.ema_slow.count}/{self.config.ema_slow_period})"
                    )
                if len(self.asset_closes) <= self.config.rs_lookback:
                    missing.append(
                        f"AssetHistory({len(self.asset_closes)}/{self.config.rs_lookback})"
                    )
                if len(self.benchmark_closes) <= self.config.rs_lookback:
                    missing.append(
                        f"BenchmarkHistory({len(self.benchmark_closes)}/{self.config.rs_lookback})"
                    )
                self.log.info(
                    f"Warming up {self.instrument_id}... Missing: {', '.join(missing)}"
                )

        return is_ready

    def _update_universe_status(self, ts_event: int):
        """Updates `_is_in_universe` flag based on current month."""
        if not self._universe_map:
            # If no universe file is loaded, assume allowed.
            self._is_in_universe = True
            return

        dt = datetime.fromtimestamp(ts_event / 1e9, tz=timezone.utc)
        current_month = dt.strftime("%Y-%m")

        if current_month != self._current_month:
            self._current_month = current_month
            month_symbols = self._universe_map.get(current_month, set())

            # Check matching logic (Exact Match or Prefix)
            # 1. Exact ID: "BTCUSDT.BINANCE"
            # 2. Symbol: "BTCUSDT"
            # 3. Colon Format (Common in data files): "BTCUSDT:USDT"
            symbol = self.instrument_id.symbol
            full_id = str(self.instrument_id)

            is_in = full_id in month_symbols or symbol in month_symbols

            if not is_in:
                # Try finding if symbol is a prefix in the universe list (e.g. "BTCUSDT" matches "BTCUSDT:USDT")
                for valid_sym in month_symbols:
                    if valid_sym.startswith(symbol):
                        is_in = True
                        break

            self._is_in_universe = is_in
            if is_in:
                self.log.info(
                    f"Universe Update: {self.instrument_id} is ACTIVE for {current_month}"
                )
            else:
                self.log.info(
                    f"Universe Update: {self.instrument_id} is INACTIVE for {current_month}"
                )

    def _update_squeeze_status(self):
        """Calculates if we are in a 'Squeeze' (Low Volatility)."""
        if not self.bb.initialized or not self.kc.initialized:
            return

        # Safely get values
        bb_upper = getattr(self.bb.upper, "value", self.bb.upper)
        bb_lower = getattr(self.bb.lower, "value", self.bb.lower)
        kc_upper = getattr(self.kc.upper, "value", self.kc.upper)
        kc_lower = getattr(self.kc.lower, "value", self.kc.lower)

        bb_width = Decimal(str(bb_upper - bb_lower))
        kc_width = Decimal(str(kc_upper - kc_lower))

        # Squeeze Condition: BB Width < (KC Width * Threshold)
        threshold = kc_width * Decimal(str(self.config.squeeze_threshold_mult))
        is_squeeze = bb_width < threshold

        if is_squeeze and not self._is_squeeze:
            self.log.debug(f"Squeeze STARTED (BB Width: {bb_width:.4f})")
        elif not is_squeeze and self._is_squeeze:
            self.log.debug("Squeeze ENDED")

        self._is_squeeze = is_squeeze

    def _calculate_rs(self) -> Decimal:
        """
        Relative Strength = (Asset / Asset_24h_ago) / (Benchmark / Benchmark_24h_ago)
        """
        asset_ret = self.asset_closes[-1] / self.asset_closes[0]
        bench_ret = self.benchmark_closes[-1] / self.benchmark_closes[0]
        return asset_ret / bench_ret

    def _has_open_position(self) -> bool:
        return len(self.cache.positions_open(instrument_id=self.instrument_id)) > 0

    def _check_entry_signal(self, bar: Bar):
        """
        Evaluates market conditions for a Long Entry.
        """
        # 1. Pre-conditions
        if len(self.asset_highs) < 2:
            return

        # 2. Cooldown Check (prevent re-entry immediately after stop out)
        cooldown_ns = self.config.cooldown_period_hours * 3600 * 1_000_000_000
        if bar.ts_event < (self._last_exit_ts + cooldown_ns):
            return

        # 3. Max Concurrency Check (Basic protection)
        # Note: This checks ALL positions in the engine.
        if len(self.cache.positions_open()) >= self.config.max_concurrent_positions:
            return

        # 4. Market Logic
        current_price = Decimal(str(bar.close))
        ema_slow = Decimal(str(self.ema_slow.value))

        # A. Trend Filter: Price > EMA200
        if current_price <= ema_slow:
            return

        # B. Squeeze Filter
        if not self._is_squeeze:
            return

        # C. Relative Strength
        rs = self._calculate_rs()
        if rs <= Decimal(str(self.config.rs_threshold)):
            return

        # D. Breakout Check
        # We need Price > Max(Recent Highs)
        breakout_level = max(self.asset_highs)
        if current_price <= breakout_level:
            # Strict breakout: Close > Highest High of last N bars
            return

        # E. Benchmark 4H Filter (Bear Market Detector)
        # Only apply if data is available
        if self.btc_ema_4h.initialized:
            btc_bar = self.cache.bar_last(self.btc_4h_bar_type)
            if btc_bar:
                btc_price = Decimal(str(btc_bar.close))
                btc_ema = Decimal(str(self.btc_ema_4h.value))
                if btc_price < btc_ema:
                    # Bear market -> Filter Longs
                    self.log.debug("Signal skipped: BTC 4H Bear Filter active.")
                    return

        # If we reached here, all systems go
        self._execute_entry(current_price, rs)

    def _execute_entry(self, current_price: Decimal, rs_value: Decimal):
        """Executes entry orders with risk management."""
        atr = Decimal(str(self.atr.value))
        risk_dist = atr * Decimal(str(self.config.stop_loss_mult))

        # Calculate Position Size
        account = self._get_account()
        if not account:
            return

        equity = account.balance(self.instrument.quote_currency).total.as_decimal()
        risk_amt = equity * Decimal(str(self.config.risk_per_trade))

        # Qty = Risk Amount / Risk Distance per Unit
        if risk_dist <= 0:
            return
        raw_qty = risk_amt / risk_dist

        try:
            qty = self.instrument.make_qty(raw_qty)
            if qty <= 0:
                return
        except Exception as e:
            self.log.error(f"Qty Calc Error: {e}")
            return

        # Place Orders
        self.log.info(
            f"ENTRY SIGNAL: {self.instrument_id} Price={current_price:.2f}, RS={rs_value:.2f}, Qty={qty}"
        )

        # 1. Market Buy
        entry_order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=qty,
        )
        self.submit_order(entry_order)

        # 2. Stop Loss (Stop Market)
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

    def _manage_positions(self, bar: Bar):
        """
        Manages open positions:
        1. Trend Exit (Close < EMA20)
        2. Trailing Stop to Breakeven
        """
        positions = self.cache.positions_open(instrument_id=self.instrument_id)
        if not positions:
            return
        position = positions[0]

        current_price = Decimal(str(bar.close))
        ema_fast = Decimal(str(self.ema_fast.value))

        # 1. Trend Exit: Close < EMA_Fast (20)
        if current_price < ema_fast:
            self.log.info(
                f"EXIT SIGNAL (Trend): Price {current_price:.2f} < EMA20 {ema_fast:.2f}"
            )
            self.close_all_positions(self.instrument_id)
            return

        # 2. Trailing to Breakeven
        if not self._breakeven_triggered and self._entry_price:
            atr = Decimal(str(self.atr.value))
            # Target to move SL: Entry + 2.5 * ATR
            target = self._entry_price + (
                atr * Decimal(str(self.config.breakeven_mult))
            )

            if current_price >= target:
                # New SL Price: Entry + 0.2%
                new_sl_price = self.instrument.make_price(
                    self._entry_price * (1 + Decimal(str(self.config.breakeven_offset)))
                )

                self.log.info(f"MOVING SL to Breakeven: {new_sl_price}")

                # Cancel old SLs
                self.cancel_all_orders(self.instrument_id)

                # Submit New SL
                sl_order = self.order_factory.stop_market(
                    instrument_id=self.instrument_id,
                    order_side=OrderSide.SELL,
                    quantity=position.quantity,
                    trigger_price=new_sl_price,
                    time_in_force=TimeInForce.GTC,
                )
                self.submit_order(sl_order)
                self._breakeven_triggered = True

    def _get_account(self):
        """Helper to find the correct account with quote currency balance."""
        accounts = self.cache.accounts()
        if not accounts:
            return None
        # Try to find account with quote currency (e.g. USDT)
        for acc in accounts:
            if not acc.balance(self.instrument.quote_currency).is_empty():
                return acc
        # Fallback to first available
        return accounts[0]

    def on_position_closed(self, position: Position):
        super().on_position_closed(position)
        self.log.info(
            f"Position Closed: {position.instrument_id}, PnL={position.realized_pnl}"
        )
        # Record exit timestamp for Cooldown
        self._last_exit_ts = self.clock.timestamp_ns()

    def on_stop(self):
        self.cancel_all_orders(self.instrument_id)
        self.close_all_positions(self.instrument_id)

    def on_reset(self):
        super().on_reset()
        self.bb.reset()
        self.kc.reset()
        self.atr.reset()
        self.ema_fast.reset()
        self.ema_slow.reset()
        self.btc_ema_4h.reset()
        self.asset_closes.clear()
        self.benchmark_closes.clear()
        self.asset_highs.clear()
        self._is_squeeze = False
        self._entry_price = None
        self._breakeven_triggered = False
