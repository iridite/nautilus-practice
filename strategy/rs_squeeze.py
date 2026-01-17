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
    kc_mult: float = 1.4  # 放宽：KC Multiplier = 1.4 (增加信号频率)
    atr_period: int = 20
    ema_fast_period: int = 20
    ema_slow_period: int = 200

    # --- Volume Filter Params ---
    volume_period: int = 20  # 成交量 MA 周期
    volume_filter_mult: float = 0.0  # 暂时禁用成交量过滤 (设为 0 表示不检查)

    # --- Relative Strength (RS) Params ---
    rs_lookback: int = 24  # Lookback for RS calculation (24 hours)
    rs_threshold: float = 1.0  # 设计规范：RS > 1.0 (Asset_Return > BTC_Return)

    # --- Risk Management ---
    # 设计规范：单笔风险 3%
    risk_per_trade: float = 0.03
    # 杠杆封顶：最大杠杆倍数 (防止 ATR 过小时杠杆失控)
    max_leverage: float = 3.0
    # 优化：止损距离 = 2 * ATR (放宽止损，减少被震出)
    stop_loss_mult: float = 2.0
    # 优化：盈亏比 2.5:1 后才启动保本 (2 ATR 止损 * 2.5 = 5 ATR 盈利)
    breakeven_mult: float = 5.0
    # BE Offset (Entry + 0.2%)
    breakeven_offset: float = 0.002
    # 时间保护强制平仓：持仓超过 N 小时后强制市价平仓
    max_holding_hours: int = 72
    # 保证金占用限制：已用保证金超过总余额的 N% 时停止新开仓
    max_margin_usage: float = 0.80

    # --- Filters ---
    max_concurrent_positions: int = 3
    # 优化：同一个币种 24 小时内最多开仓 1 次
    cooldown_period_hours: int = 24
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
    - 放量确认 (Volume Filter)：突破时成交量必须高于平均

    Logic Overview:
    1.  **Warmup**: Wait for indicators (EMA, BB, KC) and History buffers to fill.
    2.  **Universe Check**: Only trade if the instrument is in the allowed list for the current month.
    3.  **Data Sync**: Ensure Asset and Benchmark bars are time-aligned.
    4.  **Market State**:
        -   Calculate 'Squeeze': BB(20,2) 完全在 KC(20,1.2) 内部
        -   Calculate 'RS': Asset_Return / BTC_Return over 24h (RS > 1)
    5.  **Entry Signal (Long Only)**:
        -   Price > EMA200 (Uptrend).
        -   In Squeeze State.
        -   RS > 1.0 (Outperforming BTC).
        -   Breakout: Close > 前 2 根 K 线的最高价
        -   Volume > 20-period Average Volume * 1.2 (放量突破)
        -   BTC 4H > EMA200 (Market Regime Filter).
    6.  **Exit Logic**:
        -   Stop Loss: Entry - 2 * ATR
        -   Trailing Stop to Breakeven: 盈利 > 5 * ATR (2.5:1 盈亏比) 时移动止损至开仓价
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
        self.asset_highs = deque(maxlen=config.breakout_lookback)
        # 成交量缓冲区：用于计算平均成交量
        self.asset_volumes = deque(maxlen=config.volume_period)

        # --- Data Sync: 记录最后一个 benchmark bar 的时间戳 ---
        self._last_benchmark_ts: int = 0
        self._last_asset_ts: int = 0

        # --- State Flags ---
        self._is_squeeze = False
        self._entry_price: Optional[Decimal] = None
        self._breakeven_triggered = False
        self._last_exit_ts: int = 0  # Timestamp in nanoseconds
        self._last_entry_ts: int = 0  # 记录上次入场时间用于 cooldown
        self._position_open_ts: int = 0  # 记录仓位开仓时间，用于 72h 强制平仓
        self._last_warmup_log_ts: int = 0

        # --- Debug Counters ---
        self._debug_bar_count: int = 0
        self._debug_signal_checks: int = 0
        self._debug_last_status_log: int = 0

        # --- Filter Statistics (用于诊断为什么没有信号通过) ---
        self._filter_stats: Dict[str, int] = {
            "no_breakout_level": 0,
            "data_not_synced": 0,
            "in_cooldown": 0,
            "max_positions": 0,
            "margin_limit": 0,  # 新增：保证金占用限制
            "trend_filter": 0,
            "not_in_squeeze": 0,
            "rs_filter": 0,
            "breakout_filter": 0,
            "low_volume": 0,  # 新增：成交量过滤
            "btc_bear_market": 0,
            "all_passed": 0,
        }
        self._last_filter_summary_ts: int = 0

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
        self.log.debug(f"📊 Subscribed to main bar: {self.bar_type}")

        # 2. Benchmark for RS (e.g. BTCUSDT 1H)
        self.subscribe_bars(self.benchmark_bar_type)
        self.log.debug(f"📊 Subscribed to benchmark bar: {self.benchmark_bar_type}")

        # 3. Benchmark for Trend (e.g. BTCUSDT 4H)
        self.subscribe_bars(self.btc_4h_bar_type)
        self.log.debug(f"📊 Subscribed to BTC 4H bar: {self.btc_4h_bar_type}")

        self.log.debug(
            f"🚀 Strategy started for {self.instrument_id}. "
            f"Benchmark: {self.benchmark_id}, "
            f"Bar types: main={self.bar_type}, benchmark={self.benchmark_bar_type}, "
            f"btc_4h={self.btc_4h_bar_type}"
        )

    def on_bar(self, bar: Bar):
        """
        Main Event Handler.
        Dispatches logic based on the incoming Bar's type.
        """
        super().on_bar(bar)

        # 记录首次接收到的 bar（每种类型只记录一次）
        if not hasattr(self, "_first_bar_logged"):
            self._first_bar_logged = set()

        bar_type_str = str(bar.bar_type)
        if bar_type_str not in self._first_bar_logged:
            self._first_bar_logged.add(bar_type_str)
            self.log.debug(
                f"📥 First bar received: {bar_type_str}, "
                f"ts={bar.ts_event}, close={bar.close}"
            )

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
        self._debug_bar_count += 1

        # 1. Update Indicators & Buffers
        self.asset_closes.append(Decimal(str(bar.close)))

        # 注意：先计算 breakout level（排除当前 bar），再 append 当前 high
        # 设计规范：breakout 基于前 N 根 K 线的最高价
        self._prev_breakout_level = max(self.asset_highs) if self.asset_highs else None
        self.asset_highs.append(Decimal(str(bar.high)))

        # 收集成交量数据
        self.asset_volumes.append(Decimal(str(bar.volume)))

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
        else:
            # 每小时打印一次状态日志（避免刷屏）
            if bar.ts_event - self._debug_last_status_log > 3600 * 1_000_000_000:
                self._debug_last_status_log = bar.ts_event
                self.log.debug(
                    f"[{self.instrument_id}] Not in universe for {self._current_month}"
                )

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
            and len(self.asset_volumes) >= self.config.volume_period  # 新增：成交量缓冲
        )

        # 仅在首次完成 warmup 时输出一次日志
        if is_ready and self._last_warmup_log_ts == 0:
            self._last_warmup_log_ts = self.clock.timestamp_ns()
            self.log.debug(
                f"✅ Warmup complete for {self.instrument_id}. "
                f"EMA200={self.ema_slow.value:.2f}, BB/KC initialized, "
                f"Asset closes={len(self.asset_closes)}, Benchmark closes={len(self.benchmark_closes)}, "
                f"Volume buffer={len(self.asset_volumes)}"
            )

        return is_ready

    def _check_data_sync(self) -> bool:
        """
        检查 Asset 和 Benchmark 数据是否时间对齐。
        设计规范：如果某一时刻 BTC 无数据，该 Asset 的计算必须跳过。

        Returns True if data is synchronized (timestamps match).
        """
        if self._last_asset_ts == 0 or self._last_benchmark_ts == 0:
            return False

        # 同步检查：Asset bar 和 Benchmark bar 应该代表同一个时间点
        # 在回测中，两者的 ts_event 应该相等（同一个 bar 的开始时间）
        # 设计规范：不允许超过 1 分钟的偏差
        tolerance_ns = (
            60 * 1_000_000_000
        )  # 1分钟容差 (回测中通常为 0，留少量容差防止边界问题)

        is_synced = abs(self._last_asset_ts - self._last_benchmark_ts) <= tolerance_ns

        # 首次同步成功时记录日志
        if is_synced and not hasattr(self, "_sync_logged"):
            self._sync_logged = True
            self.log.debug(
                f"✅ Data sync established for {self.instrument_id}. "
                f"Asset_ts={self._last_asset_ts}, Benchmark_ts={self._last_benchmark_ts}"
            )

        return is_synced

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

            # Check matching logic:
            # Universe 格式: "BCHUSDT:USDT", "SOLUSDT:USDT"
            # Instrument ID 格式: "BCHUSDT-PERP.BINANCE"
            # Symbol 格式: "BCHUSDT-PERP"
            #
            # 需要提取 base symbol (去掉 -PERP 后缀和 :USDT 后缀)
            symbol = str(self.instrument_id.symbol)  # e.g. "BCHUSDT-PERP"
            full_id = str(self.instrument_id)  # e.g. "BCHUSDT-PERP.BINANCE"

            # 提取 base symbol: "BCHUSDT-PERP" -> "BCHUSDT"
            base_symbol = symbol.replace("-PERP", "").replace("-SWAP", "")

            # 直接匹配
            is_in = full_id in month_symbols or symbol in month_symbols

            if not is_in:
                # 尝试 base symbol 匹配 (考虑 Universe 中的 :USDT 格式)
                for valid_sym in month_symbols:
                    # "BCHUSDT:USDT" -> "BCHUSDT"
                    valid_base = valid_sym.split(":")[0]
                    if base_symbol == valid_base:
                        is_in = True
                        break

            # 仅在状态变化时输出日志
            if is_in != self._is_in_universe:
                self.log.debug(
                    f"📋 Universe status changed for {self.instrument_id}: "
                    f"month={current_month}, in_universe={is_in}, "
                    f"month_symbols={list(month_symbols)[:5]}..."
                )

            self._is_in_universe = is_in

    def _update_squeeze_status(self):
        """
        计算是否处于 'Squeeze' (波动率挤压) 状态。

        设计规范：
        BB(20, 2) 完全在 KC(20, 1.2) 内部，即：
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

        # 设计规范：Squeeze 条件 = BB 完全嵌套在 KC 内部
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

    def _calculate_avg_volume(self) -> Decimal:
        """计算过去 N 周期的平均成交量"""
        if len(self.asset_volumes) == 0:
            return Decimal("0")
        return sum(self.asset_volumes) / Decimal(len(self.asset_volumes))

    def _has_open_position(self) -> bool:
        return len(self.cache.positions_open(instrument_id=self.instrument_id)) > 0

    def _check_entry_signal(self, bar: Bar):
        """
        Evaluates market conditions for a Long Entry.

        优化后的入场门控 (Confluence)：
        0. 唯一持仓限制：每个币种同时只能持有一个仓位
        1. 趋势在 EMA200 之上
        2. 处于 Squeeze 状态 (BB 完全在 KC 内部)
        3. RS 评分高于 1.0
        4. 价格突破前 2 根 K 线的最高价
        5. 成交量 > 平均成交量 * 1.2 (放量突破)
        6. BTC 4H > EMA200 (市场环境过滤)
        7. 24 小时冷却期
        8. 排除 BTC 自交易（RS 相对自己永远是 1.0）
        9. 保证金占用限制
        """
        self._debug_signal_checks += 1

        # 0. Position Check: 唯一持仓限制 - 每个币种同时只能持有一个仓位
        if self._has_open_position():
            return

        # 0.1 排除 BTC 自交易：BTC 的 RS 相对自己永远是 1.0，无法产生有效信号
        if self.instrument_id == self.benchmark_id:
            return

        # 1. Pre-conditions: 需要前期 high 数据来检测 breakout
        if self._prev_breakout_level is None:
            self._filter_stats["no_breakout_level"] += 1
            return

        # 2. Data Sync Check: 确保 Asset 和 Benchmark 数据同步
        if not self._check_data_sync():
            self._filter_stats["data_not_synced"] += 1
            return

        # 3. Cooldown Check (优化：同一个币种 24 小时内最多开仓 1 次)
        # 使用入场时间而不是出场时间，防止连续入场
        cooldown_ns = self.config.cooldown_period_hours * 3600 * 1_000_000_000
        if bar.ts_event < (self._last_entry_ts + cooldown_ns):
            self._filter_stats["in_cooldown"] += 1
            return

        # 4. Max Concurrency Check (Basic protection)
        # Note: This checks ALL positions in the engine.
        open_positions = len(self.cache.positions_open())
        if open_positions >= self.config.max_concurrent_positions:
            self._filter_stats["max_positions"] += 1
            return

        # 4.1 Margin Usage Check: 保证金占用超过 80% 时停止新开仓
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
                    self.log.warning(
                        f"⚠️ MARGIN LIMIT: {self.instrument_id} margin usage "
                        f"{margin_ratio:.2%} >= {self.config.max_margin_usage:.0%}. Skipping entry."
                    )
                    return

        # 5. Market Logic
        current_price = Decimal(str(bar.close))
        current_volume = Decimal(str(bar.volume))
        ema_slow = Decimal(str(self.ema_slow.value))

        # A. Trend Filter: Price > EMA200
        if current_price <= ema_slow:
            self._filter_stats["trend_filter"] += 1
            return

        # B. Squeeze Filter: BB(20,2) 完全在 KC(20,1.2) 内部
        if not self._is_squeeze:
            self._filter_stats["not_in_squeeze"] += 1
            return

        # C. Relative Strength: RS > 1.0 (Asset 表现优于 BTC)
        rs = self._calculate_rs()
        if rs <= Decimal(str(self.config.rs_threshold)):
            self._filter_stats["rs_filter"] += 1
            return

        # D. Breakout Check
        # 设计规范：价格突破前 2 根 K 线的最高价
        if current_price <= self._prev_breakout_level:
            self._filter_stats["breakout_filter"] += 1
            return

        # E. Volume Filter (可选): 过滤无量突破
        # 当 volume_filter_mult > 0 时启用：当前成交量必须 > 平均成交量 * mult
        if self.config.volume_filter_mult > 0:
            avg_volume = self._calculate_avg_volume()
            volume_threshold = avg_volume * Decimal(str(self.config.volume_filter_mult))
            if current_volume <= volume_threshold:
                self._filter_stats["low_volume"] += 1
                return

        # F. Benchmark 4H Filter (Bear Market Detector)
        # Only apply if data is available
        if self.btc_ema_4h.initialized:
            btc_bar = self.cache.bar(self.btc_4h_bar_type)
            if btc_bar:
                btc_price = Decimal(str(btc_bar.close))
                btc_ema = Decimal(str(self.btc_ema_4h.value))
                if btc_price < btc_ema:
                    # Bear market -> Filter Longs
                    self._filter_stats["btc_bear_market"] += 1
                    return

        # If we reached here, all systems go
        self._filter_stats["all_passed"] += 1

        # 构建日志消息（volume_threshold 仅在启用过滤时有值）
        vol_info = ""
        if self.config.volume_filter_mult > 0:
            avg_volume = self._calculate_avg_volume()
            volume_threshold = avg_volume * Decimal(str(self.config.volume_filter_mult))
            vol_info = (
                f", Volume={current_volume:.2f} > Threshold={volume_threshold:.2f}"
            )

        self.log.debug(
            f"🎯 ALL FILTERS PASSED for {self.instrument_id}! "
            f"Price={current_price:.2f}, RS={rs:.4f}, Squeeze=True{vol_info}"
        )
        self._execute_entry(current_price, rs, bar.ts_event)

    def _execute_entry(self, current_price: Decimal, rs_value: Decimal, ts_event: int):
        """
        Executes entry orders with risk management.

        设计规范：
        - 单笔风险 = 账户余额 * 3%
        - 止损位 = Entry - 2 * ATR
        - 仓位 = Risk Amount / (Entry - StopLoss)
        - 杠杆封顶 = 3x (防止 ATR 过小时杠杆失控)
        """
        atr = Decimal(str(self.atr.value))
        risk_dist = atr * Decimal(str(self.config.stop_loss_mult))

        # Calculate Position Size
        account = self._get_account()
        if not account:
            return

        equity = account.balance(self.instrument.quote_currency).total.as_decimal()

        # 🛡️ 负余额保护：账户余额 <= 0 时禁止开仓
        if equity <= Decimal("0"):
            self.log.warning(
                f"⚠️ NEGATIVE BALANCE PROTECTION: equity={equity}, "
                f"refusing to open new position on {self.instrument_id}"
            )
            return

        risk_amt = equity * Decimal(str(self.config.risk_per_trade))

        # 设计规范：Qty = Risk Amount / Risk Distance per Unit
        if risk_dist <= 0:
            return
        raw_qty = risk_amt / risk_dist

        # 🛡️ 杠杆封顶：计算实际杠杆并限制在 max_leverage 以内
        max_leverage = Decimal(str(self.config.max_leverage))
        notional_value = raw_qty * current_price
        effective_leverage = notional_value / equity

        if effective_leverage > max_leverage:
            # 重新计算仓位使杠杆不超过上限
            old_qty = raw_qty
            raw_qty = (equity * max_leverage) / current_price
            self.log.info(
                f"🛡️ LEVERAGE CAP: {self.instrument_id} leverage {effective_leverage:.2f}x "
                f"exceeded {max_leverage}x limit. Qty reduced: {old_qty:.6f} -> {raw_qty:.6f}"
            )

        try:
            qty = self.instrument.make_qty(raw_qty)
            if qty <= 0:
                return
        except Exception as e:
            self.log.warning(f"Qty Calc Error: {e}")
            return

        # Place Orders
        self.log.info(
            f"ENTRY SIGNAL: {self.instrument_id} Price={current_price:.2f}, "
            f"RS={rs_value:.4f}, Qty={qty}, SL_dist={risk_dist:.2f}"
        )

        # 1. Market Buy
        entry_order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=qty,
        )
        self.submit_order(entry_order)

        # 2. Stop Loss (Stop Market)
        # 优化：止损位 = Entry - 2 * ATR
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
        self._last_entry_ts = ts_event  # 记录入场时间用于 cooldown
        self._position_open_ts = ts_event  # 记录开仓时间用于 72h 强制平仓

    def _manage_positions(self, bar: Bar):
        """
        Manages open positions:

        优化后的出场逻辑（移除微小止盈条件）：
        1. 止损由初始止损单处理
        2. 移动保本：盈利达到 5 倍 ATR (2.5:1 盈亏比) 后，止损移至开仓价
        3. 🛡️ 紧急止损保护：如果价格跌破止损线但止损单未触发，强制平仓
        4. ⏰ 时间保护强制平仓：持仓超过 72 小时仍未触发止盈止损，强制市价平仓

        注意：已移除 EMA20 趋势退出，避免过早止盈
        """
        positions = self.cache.positions_open(instrument_id=self.instrument_id)
        if not positions:
            return
        position = positions[0]

        current_price = Decimal(str(bar.close))

        # ⏰ 时间保护强制平仓：持仓超过 72 小时仍未触发止盈止损，强制市价平仓
        if self._position_open_ts > 0:
            holding_duration_ns = bar.ts_event - self._position_open_ts
            max_holding_ns = self.config.max_holding_hours * 3600 * 1_000_000_000
            if holding_duration_ns >= max_holding_ns:
                holding_hours = holding_duration_ns / (3600 * 1_000_000_000)
                self.log.warning(
                    f"⏰ TIME PROTECTION: {self.instrument_id} held for {holding_hours:.1f}h "
                    f">= {self.config.max_holding_hours}h. Force closing position!"
                )
                # 取消所有挂单
                self.cancel_all_orders(self.instrument_id)
                # 市价平仓
                close_order = self.order_factory.market(
                    instrument_id=self.instrument_id,
                    order_side=OrderSide.SELL,
                    quantity=position.quantity,
                )
                self.submit_order(close_order)
                self._position_open_ts = 0  # 重置开仓时间
                return

        # 🛡️ 紧急止损保护：检查价格是否已跌破止损线
        # 注意：本策略为 Long Only，只检查多单方向的止损穿透
        # 如果有入场价且 ATR 有效，计算止损位并检查
        if self._entry_price and self.atr.initialized and position.is_long:
            atr = Decimal(str(self.atr.value))
            stop_loss_price = self._entry_price - (
                atr * Decimal(str(self.config.stop_loss_mult))
            )

            if current_price <= stop_loss_price:
                self.log.warning(
                    f"🚨 EMERGENCY STOP: {self.instrument_id} price {current_price:.4f} "
                    f"breached SL {stop_loss_price:.4f}. Force closing position!"
                )
                # 取消所有挂单
                self.cancel_all_orders(self.instrument_id)
                # 市价平仓
                close_order = self.order_factory.market(
                    instrument_id=self.instrument_id,
                    order_side=OrderSide.SELL,
                    quantity=position.quantity,
                )
                self.submit_order(close_order)
                return

        # 移动保本逻辑
        # 优化：盈利达到 5 倍 ATR (2.5:1 盈亏比) 后，止损移至开仓价
        if not self._breakeven_triggered and self._entry_price:
            atr = Decimal(str(self.atr.value))
            # Target to move SL: Entry + 5 * ATR (2.5:1 R:R with 2 ATR stop)
            target = self._entry_price + (
                atr * Decimal(str(self.config.breakeven_mult))
            )

            if current_price >= target:
                # New SL Price: Entry + 0.2% (slight profit protection)
                new_sl_price = self.instrument.make_price(
                    self._entry_price * (1 + Decimal(str(self.config.breakeven_offset)))
                )

                self.log.info(
                    f"MOVING SL to Breakeven: {new_sl_price} "
                    f"(Price reached {current_price:.2f} >= Target {target:.2f})"
                )

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
        # 注意：这里不再检查 balance > 0，让调用方决定如何处理负余额
        for acc in accounts:
            balance = acc.balance(self.instrument.quote_currency)
            if balance:
                return acc
        # Fallback to first available
        return accounts[0]

    def on_position_closed(self, event):
        super().on_position_closed(event)
        # Record exit timestamp for Cooldown (保留以便调试)
        self._last_exit_ts = self.clock.timestamp_ns()

    def on_stop(self):
        """Log debugging summary."""
        # 输出过滤器统计摘要
        if self._debug_signal_checks > 0:
            self.log.info(
                f"📊 Filter stats for {self.instrument_id}: "
                f"no_breakout={self._filter_stats['no_breakout_level']}, "
                f"data_sync={self._filter_stats['data_not_synced']}, "
                f"cooldown={self._filter_stats['in_cooldown']}, "
                f"trend={self._filter_stats['trend_filter']}, "
                f"squeeze={self._filter_stats['not_in_squeeze']}, "
                f"rs={self._filter_stats['rs_filter']}, "
                f"breakout={self._filter_stats['breakout_filter']}, "
                f"low_volume={self._filter_stats['low_volume']}, "
                f"btc_bear={self._filter_stats['btc_bear_market']}, "
                f"PASSED={self._filter_stats['all_passed']}"
            )

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
        self.asset_volumes.clear()
        self._is_squeeze = False
        self._entry_price = None
        self._breakeven_triggered = False
        self._last_benchmark_ts = 0
        self._last_asset_ts = 0
        self._last_entry_ts = 0
        self._debug_bar_count = 0
        self._debug_signal_checks = 0
        self._debug_last_status_log = 0
        # Reset filter stats
        for key in self._filter_stats:
            self._filter_stats[key] = 0
