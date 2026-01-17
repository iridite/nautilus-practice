import json
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Optional, Set

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

from strategy.base import BaseStrategy, BaseStrategyConfig


class RSSqueezeConfig(BaseStrategyConfig):
    """
    Configuration for RS Squeeze Strategy.

    This config defines parameters for a specific instrument instance,
    while also handling global settings like Universe and Benchmark.
    """

    bar_type: str = ""
    benchmark_id: str = "BTCUSDT-PERP.BINANCE"  # 默认使用永续合约格式
    benchmark_bar_type: Optional[str] = (
        None  # 由引擎注入，如 "BTCUSDT-PERP.BINANCE-1-HOUR-LAST"
    )
    benchmark_trend_bar_type: Optional[str] = (
        None  # 由引擎注入，如 "BTCUSDT-PERP.BINANCE-4-HOUR-LAST"
    )

    # --- Universe Logic ---
    # Path to a JSON file mapping "YYYY-MM" -> [Symbol List]
    universe_filepath: Optional[str] = None

    # --- Indicator Params ---
    bb_period: int = 20
    bb_std: float = 2.0
    kc_period_ema: int = 20
    kc_mult: float = 1.5  # 设计规范：KC Multiplier = 1.5
    atr_period: int = 20
    ema_fast_period: int = 20
    ema_slow_period: int = 200

    # --- Relative Strength (RS) Params ---
    rs_lookback: int = 24  # Lookback for RS calculation (24 hours)
    rs_threshold: float = 1.0  # 设计规范：RS > 1.0 (Asset_Return > BTC_Return)

    # --- Risk Management ---
    # 设计规范：单笔风险 2%-3%，使用 3%
    risk_per_trade: float = 0.03
    # 设计规范：止损距离 = 1.5 * ATR
    stop_loss_mult: float = 1.5
    # 设计规范：盈利达到 1.5 倍 ATR 后移动止损至保本
    breakeven_mult: float = 1.5
    # BE Offset (Entry + 0.2%)
    breakeven_offset: float = 0.002

    # --- Filters ---
    max_concurrent_positions: int = 3
    # 设计规范：同一个 4H 时间窗内只允许触发 1 次入场
    cooldown_period_hours: int = 4
    # Breakout 窗口：前 2 根 K 线
    breakout_lookback: int = 2
    btc_ema_period: int = 200  # Period for BTC 4H Trend Filter


class RSSqueezeStrategy(BaseStrategy):
    """
    RS-Squeeze (Relative Strength + Squeeze Momentum) 狙击策略

    核心哲学：
    - 强者恒强 (Relative Strength)：只交易表现优于大盘（BTC）的币种
    - 静极思动 (Volatility Squeeze)：寻找波动率极度收缩（蓄势）的状态
    - 二段确认 (The Trigger)：价格必须突破近期的物理高点

    Logic Overview:
    1.  **Warmup**: Wait for indicators (EMA, BB, KC) and History buffers to fill.
    2.  **Universe Check**: Only trade if the instrument is in the allowed list for the current month.
    3.  **Data Sync**: Ensure Asset and Benchmark bars are time-aligned.
    4.  **Market State**:
        -   Calculate 'Squeeze': BB 完全在 KC 内部 (BB_Upper < KC_Upper AND BB_Lower > KC_Lower)
        -   Calculate 'RS': Asset_Return / BTC_Return over 24h (RS > 1)
    5.  **Entry Signal (Long Only)**:
        -   Price > EMA200 (Uptrend).
        -   In Squeeze State.
        -   RS > 1.0 (Outperforming BTC).
        -   Breakout: Close > 前 2 根 K 线的最高价
        -   BTC 4H > EMA200 (Market Regime Filter).
    6.  **Exit Logic**:
        -   Stop Loss: Entry - 1.5 * ATR
        -   Trailing Stop to Breakeven: 盈利 > 1.5 * ATR 时移动止损至开仓价
        -   Trend Exit: Close < EMA20
    """

    def __init__(self, config: RSSqueezeConfig):
        super().__init__(config)

        # --- Identifiers ---
        self.instrument_id = InstrumentId.from_str(config.instrument_id)

        # --- Bar Types ---
        # 1. Trading Bar (e.g. 1-HOUR)
        self.bar_type = BarType.from_str(config.bar_type)

        # 2. Benchmark Bar (Same timeframe as trading, e.g. 1-HOUR) for RS Calculation
        # 优先使用引擎注入的 benchmark_bar_type，否则回退到基于 benchmark_id 构造
        if config.benchmark_bar_type:
            self.benchmark_bar_type = BarType.from_str(config.benchmark_bar_type)
            self.benchmark_id = self.benchmark_bar_type.instrument_id
        else:
            self.benchmark_id = InstrumentId.from_str(config.benchmark_id)
            self.benchmark_bar_type = BarType(self.benchmark_id, self.bar_type.spec)

        # 3. Benchmark Higher TF Bar (e.g. 4-HOUR) for Regime Filter
        # 优先使用引擎注入的 benchmark_trend_bar_type，否则动态构造
        if config.benchmark_trend_bar_type:
            self.btc_4h_bar_type = BarType.from_str(config.benchmark_trend_bar_type)
        else:
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
        # 设计规范：保留前 N 根 K 线的 high 用于 breakout 检测
        self.asset_highs = deque(maxlen=config.breakout_lookback + 1)

        # --- Data Sync: 记录最后一个 benchmark bar 的时间戳 ---
        self._last_benchmark_ts: int = 0
        self._last_asset_ts: int = 0

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

        # Breakout reference (前 N 根 bar 的最高价，不包括当前 bar)
        self._prev_breakout_level: Optional[Decimal] = None

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
            self.log.debug(
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
            self._last_benchmark_ts = bar.ts_event
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
            self._last_asset_ts = bar.ts_event
            self._on_instrument_bar(bar)

    def _on_instrument_bar(self, bar: Bar):
        """
        Core logic for the trading instrument.
        Called once per bar (e.g. hourly).
        """

        # 1. Update Indicators & Buffers
        self.asset_closes.append(Decimal(str(bar.close)))

        # 注意：先计算 breakout level（排除当前 bar），再 append 当前 high
        # 设计规范：breakout 基于前 N 根 K 线的最高价
        self._prev_breakout_level = max(self.asset_highs) if self.asset_highs else None
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
        Logs status only once when warmup completes.
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

        # 仅在首次完成 warmup 时输出一次日志
        if is_ready and self._last_warmup_log_ts == 0:
            self._last_warmup_log_ts = self.clock.timestamp_ns()
            self.log.info(f"✅ Warmup complete for {self.instrument_id}")

        return is_ready

    def _check_data_sync(self) -> bool:
        """
        检查 Asset 和 Benchmark 数据是否时间对齐。
        设计规范：如果某一时刻 BTC 无数据，该 Asset 的计算必须跳过。

        Returns True if data is synchronized (timestamps match).
        """
        if self._last_asset_ts == 0 or self._last_benchmark_ts == 0:
            return False

        # 允许一定的时间容差（同一小时内视为同步）
        # 1H bar 的容差：3600秒 = 3600 * 1e9 纳秒
        tolerance_ns = 3600 * 1_000_000_000

        return abs(self._last_asset_ts - self._last_benchmark_ts) < tolerance_ns

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
            symbol = str(self.instrument_id.symbol)  # Convert Symbol object to string
            full_id = str(self.instrument_id)

            is_in = full_id in month_symbols or symbol in month_symbols

            if not is_in:
                # Try finding if symbol is a prefix in the universe list (e.g. "BTCUSDT" matches "BTCUSDT:USDT")
                for valid_sym in month_symbols:
                    if valid_sym.startswith(symbol):
                        is_in = True
                        break

            self._is_in_universe = is_in

    def _update_squeeze_status(self):
        """
        计算是否处于 'Squeeze' (波动率挤压) 状态。

        设计规范：
        BB 完全在 KC 内部，即：
        - BB_Upper < KC_Upper
        - BB_Lower > KC_Lower
        """
        if not self.bb.initialized or not self.kc.initialized:
            return

        # Safely get values
        bb_upper = getattr(self.bb.upper, "value", self.bb.upper)
        bb_lower = getattr(self.bb.lower, "value", self.bb.lower)
        kc_upper = getattr(self.kc.upper, "value", self.kc.upper)
        kc_lower = getattr(self.kc.lower, "value", self.kc.lower)

        # 设计规范：Squeeze 条件 = BB 完全缩进 KC 内部
        # BB_Upper < KC_Upper AND BB_Lower > KC_Lower
        self._is_squeeze = (bb_upper < kc_upper) and (bb_lower > kc_lower)

    def _calculate_rs(self) -> Decimal:
        """
        相对强度 (Relative Strength) 计算

        设计规范：
        Asset_Return = (Close_Now - Close_24h_ago) / Close_24h_ago
        BTC_Return = (BTC_Close_Now - BTC_Close_24h_ago) / BTC_Close_24h_ago
        RS = (1 + Asset_Return) / (1 + BTC_Return)

        当 RS > 1 时，表示 Asset 表现优于 BTC (Asset_Return > BTC_Return)
        """
        # 计算价格比率（等价于 1 + Return）
        asset_ratio = self.asset_closes[-1] / self.asset_closes[0]
        bench_ratio = self.benchmark_closes[-1] / self.benchmark_closes[0]

        # RS = Asset 价格比率 / Benchmark 价格比率
        # 当 RS > 1 时，意味着 Asset 收益率 > Benchmark 收益率
        return asset_ratio / bench_ratio

    def _has_open_position(self) -> bool:
        return len(self.cache.positions_open(instrument_id=self.instrument_id)) > 0

    def _check_entry_signal(self, bar: Bar):
        """
        Evaluates market conditions for a Long Entry.

        设计规范入场门控 (Confluence)：
        1. 趋势在 EMA200 之上
        2. 处于 Squeeze 状态
        3. RS 评分高于 1.0
        4. 价格突破前 2 根 K 线的最高价
        5. BTC 4H > EMA200 (市场环境过滤)
        """
        # 1. Pre-conditions: 需要前期 high 数据来检测 breakout
        if self._prev_breakout_level is None:
            return

        # 2. Data Sync Check: 确保 Asset 和 Benchmark 数据同步
        if not self._check_data_sync():
            return

        # 3. Cooldown Check (设计规范：同一个 4H 时间窗内只允许 1 次入场)
        cooldown_ns = self.config.cooldown_period_hours * 3600 * 1_000_000_000
        if bar.ts_event < (self._last_exit_ts + cooldown_ns):
            return

        # 4. Max Concurrency Check (Basic protection)
        # Note: This checks ALL positions in the engine.
        if len(self.cache.positions_open()) >= self.config.max_concurrent_positions:
            return

        # 5. Market Logic
        current_price = Decimal(str(bar.close))
        ema_slow = Decimal(str(self.ema_slow.value))

        # A. Trend Filter: Price > EMA200
        if current_price <= ema_slow:
            return

        # B. Squeeze Filter: BB 完全在 KC 内部
        if not self._is_squeeze:
            return

        # C. Relative Strength: RS > 1.0 (Asset 表现优于 BTC)
        rs = self._calculate_rs()
        if rs <= Decimal(str(self.config.rs_threshold)):
            return

        # D. Breakout Check
        # 设计规范：价格突破前 2 根 K 线的最高价
        if current_price <= self._prev_breakout_level:
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
                    return

        # If we reached here, all systems go
        self._execute_entry(current_price, rs)

    def _execute_entry(self, current_price: Decimal, rs_value: Decimal):
        """
        Executes entry orders with risk management.

        设计规范：
        - 单笔风险 = 账户余额 * 3%
        - 止损位 = Entry - 1.5 * ATR
        - 仓位 = Risk Amount / (Entry - StopLoss)
        """
        atr = Decimal(str(self.atr.value))
        risk_dist = atr * Decimal(str(self.config.stop_loss_mult))

        # Calculate Position Size
        account = self._get_account()
        if not account:
            return

        equity = account.balance(self.instrument.quote_currency).total.as_decimal()
        risk_amt = equity * Decimal(str(self.config.risk_per_trade))

        # 设计规范：Qty = Risk Amount / Risk Distance per Unit
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
            f"ENTRY SIGNAL: {self.instrument_id} Price={current_price:.2f}, RS={rs_value:.4f}, Qty={qty}"
        )

        # 1. Market Buy
        entry_order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=qty,
        )
        self.submit_order(entry_order)

        # 2. Stop Loss (Stop Market)
        # 设计规范：止损位 = Entry - 1.5 * ATR
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

        设计规范：
        1. 追踪退出：价格回落并收盘于 1H EMA20 之下
        2. 移动保本：盈利达到 1.5 倍 ATR 后，止损移至开仓价
        """
        positions = self.cache.positions_open(instrument_id=self.instrument_id)
        if not positions:
            return
        position = positions[0]

        current_price = Decimal(str(bar.close))
        ema_fast = Decimal(str(self.ema_fast.value))

        # 1. Trend Exit: Close < EMA_Fast (20)
        # 设计规范：追踪退出 - 价格回落并收盘于 1H EMA20 之下
        if current_price < ema_fast:
            self.log.info(
                f"EXIT SIGNAL (Trend): Price {current_price:.2f} < EMA20 {ema_fast:.2f}"
            )
            self.close_all_positions(self.instrument_id)
            return

        # 2. Trailing to Breakeven
        # 设计规范：盈利达到 1.5 倍 ATR 后，止损移至开仓价
        if not self._breakeven_triggered and self._entry_price:
            atr = Decimal(str(self.atr.value))
            # Target to move SL: Entry + 1.5 * ATR
            target = self._entry_price + (
                atr * Decimal(str(self.config.breakeven_mult))
            )

            if current_price >= target:
                # New SL Price: Entry + 0.2% (slight profit protection)
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

    def on_position_closed(self, event):
        super().on_position_closed(event)
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
        self._last_benchmark_ts = 0
        self._last_asset_ts = 0
