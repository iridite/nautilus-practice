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

    === V3.0 核心优化: "Early Momentum Explosion" 入场逻辑 ===
    诊断发现:
    - V2.0 "Pullback to EMA20" 失败，因为它捕捉的是疲惫的动能
    - Avg Winner 0.67 USDT 不可接受，需要追求 "Big Win"
    - 高 RS 在回调入场逻辑下变成了逆势指标（买在吹顶）

    新逻辑 (Lift-off Trigger):
    1. 入场方式: MARKET ORDER (Taker) - 抓住行情启动的第一时间
    2. RS 加速检测: Asset_Return_6h > BTC_Return_6h + 0.03
       AND Asset_Return_6h > Asset_Return_24h (确保捕捉行情开始，而非结束)
    3. 防疲惫过滤: Close < Upper_BB (价格未突破布林带上轨)
    4. Squeeze: 至少连续 2 根 K 线处于挤压状态
    5. 出场: 移除 EMA 趋势退出，仅靠 Trailing Stop 追踪利润
    6. 目标: 捕捉 30u+ 的 Max Winner，而不是 0.6u 的小赢
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
    # 注意：列表中的顺序即为成交量排名（降序），用于 Adaptive RS Gap
    universe_filepath: Optional[str] = None

    # --- Indicator Params ---
    bb_period: int = 20
    bb_std: float = 2.0
    kc_period_ema: int = 20
    kc_mult: float = 1.4  # 放宽：KC Multiplier = 1.4 (增加信号频率)
    atr_period: int = 20
    ema_fast_period: int = 20
    ema_slow_period: int = 200
    # V3.0: EMA 趋势退出已移除，保留指标仅供参考
    ema_trend_exit_period: int = 50

    # --- Volume Filter Params ---
    volume_ma_period: int = 20  # 成交量 MA 周期（用于计算 20 周期平均成交量）
    volume_filter_mult: float = 1.6  # 成交量爆发验证（V3.0 仅用于记录，不作为过滤条件）

    # --- V3.0 RS Acceleration Params ---
    # RS 加速检测：捕捉行情启动的第一时间
    # Entry if: Asset_Return_6h > BTC_Return_6h + rs_acceleration_gap
    #       AND Asset_Return_6h > Asset_Return_24h (6h 收益 > 24h 收益 = 动能加速)
    rs_lookback_6h: int = 6  # 6 小时窗口 (用于加速检测)
    rs_lookback_12h: int = 12  # 12 小时窗口 (保留用于记录)
    rs_lookback_24h: int = 24  # 24 小时窗口 (用于加速对比)
    rs_acceleration_gap: float = 0.03  # V3.0: 6h 必须跑赢 BTC 3%
    # 以下参数保留用于向后兼容，V3.0 不再使用阶梯式 RS
    rs_gap_6h: float = 0.03  # V3.0: 统一使用 rs_acceleration_gap
    rs_gap_12h: float = 0.05  # (保留)
    rs_gap_24h: float = 0.07  # (保留)

    # --- Adaptive RS Gap for Mid-Caps ---
    # 中盘币 (排名 > 50) 需要更高的 RS Gap 确信度
    mid_cap_rank_threshold: int = 50  # 排名阈值：> 50 视为中盘币
    mid_cap_rs_gap_addon: float = 0.02  # 中盘币额外 RS Gap 要求 (+2%)

    # --- Squeeze Tightness Params ---
    bb_width_period: int = 100  # BB Width 分位数计算周期
    bb_width_percentile: float = 0.50  # BB Width 分位数阈值 (V3.0 仅用于记录)

    # --- Squeeze Maturity Filter ---
    # 挤压成熟度过滤：挤压状态必须连续保持至少 N 根 K 线
    squeeze_maturity_bars: int = 2  # V3.0: 至少连续 2 根 K 线处于挤压状态

    # --- V3.0 Anti-Exhaustion Filter (防疲惫过滤器) ---
    # 替代 V2.0 的 Extension Filter
    # Entry ONLY if: Close < Upper_Bollinger_Band
    # 如果价格已在布林带外，不入场，等待下一次挤压
    anti_exhaustion_enabled: bool = True

    # --- V2.0 Pullback Entry Logic (V3.0 已禁用) ---
    # 回调入场逻辑已废弃，V3.0 使用市价单直接入场
    pullback_entry_enabled: bool = False  # V3.0: 禁用回调入场，改用市价单
    pullback_order_expiry_hours: int = 4  # 限价单过期时间（保留用于向后兼容）

    # --- V2.0 Extension Filter (V3.0 已废弃) ---
    # 已被 Anti-Exhaustion Filter 替代
    extension_filter_enabled: bool = False  # V3.0: 禁用

    # --- Risk Management ---
    # V3.0: 单笔风险 5% (更激进，配合紧止损)
    risk_per_trade: float = 0.05
    # 杠杆封顶：最大杠杆倍数 3.0x (防止 ATR 过小时杠杆失控)
    max_leverage: float = 3.0
    # V3.0: 止损距离 = 1.5 * ATR (紧止损允许更大仓位)
    stop_loss_mult: float = 1.5
    # 保本触发：盈利 > 4.0 * ATR 后才移动止损至保本价 (延迟保本，给交易更多呼吸空间)
    breakeven_mult: float = 4.0
    # BE Offset (Entry + 0.2%)
    breakeven_offset: float = 0.002
    # 时间保护强制平仓：持仓超过 N 小时后强制市价平仓
    max_holding_hours: int = 72
    # 保证金占用限制：已用保证金超过总余额的 N% 时停止新开仓
    max_margin_usage: float = 0.80

    # --- V3.0 Trailing Stop ("Big Win" Exit Logic) ---
    # 核心目标：捕捉 30u+ 的 Max Winner，而不是 0.6u 的小赢
    # 触发条件：盈利 >= 2.5 * ATR 后激活追踪止损
    trailing_stop_trigger_mult: float = 2.5
    # V3.0: 追踪止损距离 = Highest_High - 3.0 * ATR (更宽松的追踪，给利润更多奔跑空间)
    trailing_stop_atr_mult: float = 3.0

    # --- V3.0 EMA Trend Exit (已移除) ---
    # V2.0 的 EMA 趋势退出会扼杀赢家，V3.0 移除此逻辑
    ema_trend_exit_enabled: bool = False

    # --- Filters ---
    max_concurrent_positions: int = 5  # 最大并发仓位数
    # 同一个币种 24 小时内最多开仓 1 次
    cooldown_period_hours: int = 24
    # Breakout 窗口：前 2 根 K 线
    breakout_lookback: int = 2
    btc_ema_period: int = 200  # Period for BTC 4H Trend Filter


class RSSqueezeStrategy(BaseStrategy):
    """
    RS-Squeeze (Relative Strength + Squeeze Momentum) 狙击策略 - V3.0 Early Momentum Explosion
    "Lift-off Trigger" 动能爆发捕捉版

    类变量用于收集所有实例的过滤器统计，供回测结束后统一输出。

    === V3.0 核心优化: "Early Momentum Explosion" 动能爆发入场 ===
    失败分析 (V2.0):
    - "Pullback to EMA20" 失败，因为它捕捉的是疲惫的动能
    - Avg Winner 0.67 USDT 不可接受，需要追求 "Big Win"
    - 高 RS 在回调入场逻辑下变成了逆势指标（买在吹顶）

    核心哲学 (V3.0):
    - RS 加速 (RS Acceleration)：捕捉动能爆发的起点，而非终点
    - 静极思动 (Volatility Squeeze)：寻找波动率极度收缩（蓄势）的状态
    - 防疲惫过滤 (Anti-Exhaustion)：价格未突破布林带上轨才入场
    - 市价入场 (Market Order)：抓住行情启动的第一时间，不等回调
    - 宽松追踪 (Wide Trailing)：给赢家更多呼吸空间，追求 30u+ 的 Max Winner

    Logic Overview (V3.0 "Lift-off Trigger"):
    1.  **Warmup**: Wait for indicators (EMA, BB, KC) and History buffers to fill.
    2.  **Universe Check**: Only trade Universe-25 (top liquidity leaders).
    3.  **Data Sync**: Ensure Asset and Benchmark bars are time-aligned.
    4.  **Market State**:
        -   Calculate 'Squeeze': BB(20,2) 完全在 KC(20,1.4) 内部，至少连续 2 根 K 线
        -   Calculate 'RS Acceleration': Asset_6h_Return > BTC_6h_Return + 3%
            AND Asset_6h_Return > Asset_24h_Return (动能加速，而非疲惫)
    5.  **Entry Signal (Lift-off Trigger)** - 单阶段市价入场：
        -   Price > EMA200 (Uptrend).
        -   In Squeeze State >= 2 bars (BB 完全在 KC 内部).
        -   RS Acceleration: 6h 跑赢 BTC 3%，且 6h 收益 > 24h 收益.
        -   Anti-Exhaustion: Close < Upper_BB (价格未在布林带外).
        -   BTC 4H > EMA200 (Market Regime Filter).
        -   → MARKET ORDER 入场
    6.  **Exit Logic ("Big Win" Focus)**:
        -   Stop Loss: Entry - 1.5 * ATR (紧止损允许更大仓位)
        -   Trailing Stop: 盈利 >= 2.5 * ATR 后激活
        -   Trailing Distance: Highest_High - 3.0 * ATR (宽松追踪，让利润奔跑)
        -   **移除** EMA 趋势退出 (会扼杀赢家)

    Risk Model:
        -   Risk Per Trade: 5% of equity (Compounding)
        -   Stop Loss: 1.5 * ATR
        -   Max Leverage: 3.0x
        -   Max Concurrent Trades: 5
        -   Target: 捕捉 30u+ 的 Max Winner，Avg Winner >= 5.0 USDT
    """

    # --- 类变量：收集所有实例的过滤器统计 (用于回测结束后统一输出) ---
    _all_filter_stats: Dict[str, Dict[str, int]] = {}
    _all_trade_metrics: list = []  # 收集所有交易的入场指标

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
        self.ema_trend_exit = ExponentialMovingAverage(config.ema_trend_exit_period)
        self.btc_ema_4h = ExponentialMovingAverage(config.btc_ema_period)

        # --- Data Buffers ---
        # 阶梯式 RS 需要 24 小时窗口的数据 (+1 for comparison)
        max_lookback = max(
            config.rs_lookback_6h, config.rs_lookback_12h, config.rs_lookback_24h
        )
        self.asset_closes = deque(maxlen=max_lookback + 1)
        self.benchmark_closes = deque(maxlen=max_lookback + 1)
        # 设计规范：保留前 N 根 K 线的 high 用于 breakout 检测
        self.asset_highs = deque(maxlen=config.breakout_lookback)
        # 成交量缓冲区：用于计算 20 周期平均成交量
        self.asset_volumes = deque(maxlen=config.volume_ma_period)
        # BB Width 缓冲区：用于计算 BB Width 分位数
        self.bb_widths = deque(maxlen=config.bb_width_period)

        # --- Data Sync: 记录最后一个 benchmark bar 的时间戳 ---
        self._last_benchmark_ts: int = 0
        self._last_asset_ts: int = 0

        # --- State Flags ---
        self._is_squeeze = False
        self._squeeze_consecutive_bars: int = 0  # 连续挤压 K 线计数
        self._entry_price: Optional[Decimal] = None
        self._breakeven_triggered = False
        self._trailing_stop_active = False  # 追踪止损是否激活
        self._highest_high_since_entry: Optional[Decimal] = None  # 入场后最高价
        self._last_exit_ts: int = 0  # Timestamp in nanoseconds
        self._last_entry_ts: int = 0  # 记录上次入场时间用于 cooldown
        self._position_open_ts: int = 0  # 记录仓位开仓时间，用于 72h 强制平仓
        self._last_warmup_log_ts: int = 0

        # --- Pullback Entry State (V2.0 新增) ---
        # 回调入场状态：记录待成交的限价买单信息
        self._pending_pullback_order_id: Optional[str] = (
            None  # 待成交限价单的 ClientOrderId
        )
        self._pullback_order_expiry_ts: int = 0  # 限价单过期时间戳 (纳秒)
        self._pullback_order_qty: Optional[Decimal] = None  # 限价单数量
        self._pullback_entry_metrics: Optional[Dict] = None  # 限价单入场时的指标记录

        # --- Universe Rank State ---
        # 排名直接从 universe_map 的列表顺序推导（列表已按成交量降序排列）
        self._universe_rank_map: Dict[
            str, Dict[str, int]
        ] = {}  # month -> {symbol -> rank}
        self._current_rank: int = 0  # 当前币种排名 (0 = 未知)

        # --- Debug Counters ---
        self._debug_bar_count: int = 0
        self._debug_signal_checks: int = 0
        self._debug_last_status_log: int = 0

        # --- Filter Statistics (用于诊断为什么没有信号通过) ---
        # 按照诊断要求的分类组织
        self._filter_stats: Dict[str, int] = {
            # 预检查类
            "no_breakout_level": 0,
            "data_not_synced": 0,
            "in_cooldown": 0,
            "max_positions": 0,
            "margin_limit": 0,
            # 核心过滤器类 (对应诊断分类)
            "fail_trend": 0,  # Price < EMA200
            "fail_squeeze": 0,  # Not in Squeeze
            "fail_squeeze_maturity": 0,  # Squeeze < N bars
            "fail_bb_width": 0,  # BB Width not tight
            "fail_extension": 0,  # Price overextended from EMA20
            "fail_rs": 0,  # RS Gap not met
            "fail_breakout": 0,  # No price breakout
            "fail_volume": 0,  # Volume < threshold
            "fail_btc_bear": 0,  # BTC 4H < EMA200
            # 成功通过
            "all_passed": 0,
        }
        self._last_filter_summary_ts: int = 0

        # --- Entry Metrics (用于交易关闭时输出) ---
        self._entry_metrics: Dict[str, Dict] = {}

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
        """
        Loads the universe JSON file into memory.

        Universe 文件格式: {"YYYY-MM": ["BTCUSDT:USDT", "ETHUSDT:USDT", ...]}
        列表顺序即为成交量排名（降序），用于 Adaptive RS Gap。
        """
        if not self.config.universe_filepath:
            return

        try:
            with open(self.config.universe_filepath, "r") as f:
                data = json.load(f)
                # 同时构建 set（用于 O(1) 查找）和 rank map（用于排名）
                for month, symbols_list in data.items():
                    self._universe_map[month] = set(symbols_list)
                    # 构建排名映射：列表索引 + 1 = 排名（1-based）
                    self._universe_rank_map[month] = {
                        sym: idx + 1 for idx, sym in enumerate(symbols_list)
                    }
            self.log.debug(
                f"[{self.instrument_id}] Universe config loaded: {len(self._universe_map)} months."
            )
        except Exception as e:
            self.log.error(f"Failed to load universe file: {e}")

    def _get_current_rank(self) -> int:
        """
        获取当前币种在当前月份的 Universe 排名。

        排名直接从 universe_map 的列表顺序推导（列表已按成交量降序排列）。

        Returns: 排名 (1-based)，0 表示未知或不在 Universe 中
        """
        if not self._universe_rank_map or not self._current_month:
            return 0

        month_ranks = self._universe_rank_map.get(self._current_month)
        if not month_ranks:
            return 0

        symbol = str(self.instrument_id.symbol)  # e.g. "BCHUSDT-PERP"
        base_symbol = symbol.replace("-PERP", "").replace("-SWAP", "")

        # 直接查找
        if base_symbol in month_ranks:
            return month_ranks[base_symbol]

        # 尝试带 :USDT 格式
        usdt_symbol = f"{base_symbol}:USDT"
        if usdt_symbol in month_ranks:
            return month_ranks[usdt_symbol]

        return 0

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

        # 0. Pullback 限价单过期检查 (V2.0 新增)
        # 如果有待成交的限价单且已过期，取消订单
        self._check_pullback_order_expiry(bar.ts_event)

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
        self.ema_trend_exit.handle_bar(bar)

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
        # 阶梯式 RS 需要至少 24h 的数据
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
        BB(20, 2) 完全在 KC(20, 1.4) 内部，即：
        - BB_Upper < KC_Upper
        - BB_Lower > KC_Lower

        强化规范（Squeeze Maturity Filter）：
        - BB Width 必须处于过去 100 根线的前 30% 分位数（极度收缩）
        - 挤压状态必须连续保持至少 3 根 K 线（消除假挤压）
        """
        if not self.bb.initialized or not self.kc.initialized:
            return

        # Safely get values
        bb_upper = getattr(self.bb.upper, "value", self.bb.upper)
        bb_lower = getattr(self.bb.lower, "value", self.bb.lower)
        bb_middle = getattr(self.bb.middle, "value", self.bb.middle)
        kc_upper = getattr(self.kc.upper, "value", self.kc.upper)
        kc_lower = getattr(self.kc.lower, "value", self.kc.lower)

        # 计算 BB Width（标准化的布林带宽度）
        # BB Width = (BB_Upper - BB_Lower) / BB_Middle
        if bb_middle > 0:
            bb_width = (bb_upper - bb_lower) / bb_middle
            self.bb_widths.append(bb_width)

        # 设计规范：Squeeze 条件 = BB 完全嵌套在 KC 内部
        # BB_Upper < KC_Upper AND BB_Lower > KC_Lower
        current_squeeze = (bb_upper < kc_upper) and (bb_lower > kc_lower)

        # Squeeze Maturity Filter: 追踪连续挤压 K 线数
        if current_squeeze:
            self._squeeze_consecutive_bars += 1
        else:
            self._squeeze_consecutive_bars = 0

        self._is_squeeze = current_squeeze

    def _is_squeeze_mature(self) -> bool:
        """
        检查挤压是否"成熟"：连续挤压状态至少持续 N 根 K 线。
        消除由瞬间价格尖峰引起的"假挤压"。
        """
        return self._squeeze_consecutive_bars >= self.config.squeeze_maturity_bars

    def _check_extension_filter(self, current_price: Decimal) -> bool:
        """
        动态扩展过滤器 (Anti-Chase Guard)：防止追高。

        设计规范：
        Entry ONLY permitted if: Current_Price < EMA(20) * (1 + ATR_Relative)
        其中 ATR_Relative = ATR(20) / Close，使过滤器适应币种波动性。

        目标：确保在突破期间尽可能接近移动均线支撑入场。

        Returns:
            True if price is within acceptable extension range (允许入场)
            False if price is overextended (禁止入场)
        """
        if not self.config.extension_filter_enabled:
            return True

        if not self.ema_fast.initialized or not self.atr.initialized:
            return True

        ema_fast = Decimal(str(self.ema_fast.value))
        atr = Decimal(str(self.atr.value))

        if current_price <= 0:
            return True

        # ATR_Relative = ATR(20) / Close
        atr_relative = atr / current_price

        # 最大允许扩展 = EMA(20) * (1 + ATR_Relative)
        max_extension = ema_fast * (Decimal("1") + atr_relative)

        # 如果当前价格超过最大扩展，则视为"追高"
        return current_price < max_extension

    def _is_bb_width_tight(self) -> bool:
        """
        检查当前 BB Width 是否处于过去 N 根线的前 percentile 分位数。

        强化规范：确保只有在波动率"极度"收缩后才入场。
        """
        if len(self.bb_widths) < self.config.bb_width_period:
            # 数据不足时，暂不启用此过滤（允许通过）
            return True

        current_width = self.bb_widths[-1]
        sorted_widths = sorted(self.bb_widths)

        # 计算当前宽度在历史数据中的分位数位置
        # 找到当前宽度在排序列表中的位置
        position = 0
        for w in sorted_widths:
            if w < current_width:
                position += 1
            else:
                break

        percentile = position / len(sorted_widths)

        # 如果当前宽度处于前 percentile（如前 30%），则视为足够紧
        return percentile <= self.config.bb_width_percentile

    def _calculate_return(self, closes: deque, lookback: int) -> Decimal:
        """
        计算指定窗口的收益率。

        Returns:
            (Close_Now - Close_N_ago) / Close_N_ago
        """
        if len(closes) < lookback + 1:
            return Decimal("0")

        close_now = closes[-1]
        close_ago = closes[-(lookback + 1)]

        if close_ago == 0:
            return Decimal("0")

        return (close_now - close_ago) / close_ago

    def _check_anti_exhaustion(self, current_price: Decimal) -> bool:
        """
        V3.0 防疲惫过滤器 (Anti-Exhaustion Filter)。

        设计规范：
        Entry ONLY if: Close < Upper_Bollinger_Band

        核心逻辑：
        - 如果价格已经突破布林带上轨，说明动能已经释放（blow-off top）
        - 此时不入场，等待下一次挤压蓄势
        - 我们要捕捉的是挤压后的第一次动能爆发，而非已经过度拉伸的状态

        Returns:
            True if price is below Upper BB (允许入场)
            False if price is at or above Upper BB (禁止入场 - 疲惫)
        """
        if not self.config.anti_exhaustion_enabled:
            return True

        if not self.bb.initialized:
            return True

        bb_upper = Decimal(str(getattr(self.bb.upper, "value", self.bb.upper)))

        # 如果价格 >= 布林带上轨，视为疲惫/过度拉伸
        return current_price < bb_upper

    def _check_rs_acceleration(self) -> tuple[bool, str, Decimal, Decimal]:
        """
        V3.0 RS 加速检测：捕捉动能爆发的起点，而非终点。

        设计规范：
        Entry if:
        1. Asset_Return_6h > BTC_Return_6h + rs_acceleration_gap (3%)
        2. AND Asset_Return_6h > Asset_Return_24h (动能加速，而非疲惫)

        核心逻辑：
        - 条件1 确保币种在短期内显著跑赢大盘
        - 条件2 确保我们捕捉的是行情的"开始"而非"结束"
          如果 6h 收益 < 24h 收益，说明动能正在衰减（疲惫上涨）

        Returns:
            (is_passed, reason, asset_return_6h, rs_gap_6h)
        """
        # 检查数据是否足够
        if len(self.asset_closes) < self.config.rs_lookback_24h + 1:
            return (False, "insufficient_data", Decimal("0"), Decimal("0"))
        if len(self.benchmark_closes) < self.config.rs_lookback_6h + 1:
            return (False, "insufficient_benchmark_data", Decimal("0"), Decimal("0"))

        # 计算 6h 和 24h 的 Asset 收益率
        asset_return_6h = self._calculate_return(
            self.asset_closes, self.config.rs_lookback_6h
        )
        asset_return_24h = self._calculate_return(
            self.asset_closes, self.config.rs_lookback_24h
        )

        # 计算 6h BTC 收益率
        btc_return_6h = self._calculate_return(
            self.benchmark_closes, self.config.rs_lookback_6h
        )

        # RS Gap = Asset_6h - BTC_6h
        rs_gap_6h = asset_return_6h - btc_return_6h

        # Adaptive RS Gap: 中盘币需要更高的 RS Gap
        rank = self._get_current_rank()
        gap_addon = Decimal("0")
        if rank > self.config.mid_cap_rank_threshold:
            gap_addon = Decimal(str(self.config.mid_cap_rs_gap_addon))

        required_gap = Decimal(str(self.config.rs_acceleration_gap)) + gap_addon

        # 条件1: Asset_Return_6h > BTC_Return_6h + 3%
        if rs_gap_6h <= required_gap:
            return (False, "rs_gap_insufficient", asset_return_6h, rs_gap_6h)

        # 条件2: Asset_Return_6h > Asset_Return_24h (动能加速)
        # 如果 6h 收益 <= 24h 收益，说明动能正在衰减
        if asset_return_6h <= asset_return_24h:
            return (False, "momentum_exhausting", asset_return_6h, rs_gap_6h)

        # 两个条件都满足 - 动能爆发中！
        return (True, "acceleration_confirmed", asset_return_6h, rs_gap_6h)

    def _check_laddered_rs(self) -> tuple[bool, str]:
        """
        阶梯式 RS 过滤器：检查任一窗口是否满足 RS 条件。

        设计规范（基础版）：
        (Asset_Return_6h > BTC_Return_6h + 0.04) OR
        (Asset_Return_12h > BTC_Return_12h + 0.06) OR
        (Asset_Return_24h > BTC_Return_24h + 0.10)

        Adaptive RS Gap for Mid-Caps:
        对于排名 > 50 的中盘币，增加额外的 RS Gap 要求 (+2%)
        以要求更高的确信度过滤噪音。

        注意：V3.0 已改用 _check_rs_acceleration()，此方法保留用于向后兼容。

        Returns:
            (is_passed, window_name) - 是否通过及通过的窗口名称
        """
        # 检查数据是否足够
        max_lookback = max(
            self.config.rs_lookback_6h,
            self.config.rs_lookback_12h,
            self.config.rs_lookback_24h,
        )

        if len(self.asset_closes) < max_lookback + 1:
            return (False, "insufficient_data")
        if len(self.benchmark_closes) < max_lookback + 1:
            return (False, "insufficient_benchmark_data")

        # Adaptive RS Gap: 中盘币需要更高的 RS Gap
        rank = self._get_current_rank()
        gap_addon = Decimal("0")
        if rank > self.config.mid_cap_rank_threshold:
            gap_addon = Decimal(str(self.config.mid_cap_rs_gap_addon))

        # 计算各窗口的 Asset 和 Benchmark 收益率
        windows = [
            (self.config.rs_lookback_6h, self.config.rs_gap_6h, "6h"),
            (self.config.rs_lookback_12h, self.config.rs_gap_12h, "12h"),
            (self.config.rs_lookback_24h, self.config.rs_gap_24h, "24h"),
        ]

        for lookback, gap_threshold, window_name in windows:
            asset_return = self._calculate_return(self.asset_closes, lookback)
            btc_return = self._calculate_return(self.benchmark_closes, lookback)

            # 计算 RS Gap = Asset_Return - BTC_Return
            rs_gap = asset_return - btc_return

            # 应用 Adaptive Gap: 基础阈值 + 中盘币额外要求
            required_gap = Decimal(str(gap_threshold)) + gap_addon

            # 如果 RS Gap > 阈值，则满足条件
            if rs_gap > required_gap:
                return (True, window_name)

        return (False, "none")

    def _calculate_avg_volume(self) -> Decimal:
        """计算过去 N 周期的平均成交量"""
        if len(self.asset_volumes) == 0:
            return Decimal("0")
        return sum(self.asset_volumes) / Decimal(len(self.asset_volumes))

    def _has_open_position(self) -> bool:
        return len(self.cache.positions_open(instrument_id=self.instrument_id)) > 0

    def _has_pending_pullback_order(self) -> bool:
        """
        检查是否有待成交的回调限价单。
        V2.0 新增：防止在已有限价单的情况下重复下单。
        """
        return self._pending_pullback_order_id is not None

    def _check_pullback_order_expiry(self, current_ts: int):
        """
        检查并处理回调限价单的过期。
        V2.0 新增：限价单在 N 小时内未成交则取消。

        Args:
            current_ts: 当前时间戳 (纳秒)
        """
        if not self._pending_pullback_order_id:
            return

        if current_ts >= self._pullback_order_expiry_ts:
            # 限价单已过期，取消订单
            self.log.info(
                f"⏰ PULLBACK ORDER EXPIRED: {self.instrument_id} "
                f"Limit order did not fill within {self.config.pullback_order_expiry_hours}h. Cancelling."
            )
            # 取消所有挂单（包括限价买单）
            self.cancel_all_orders(self.instrument_id)
            # 重置状态
            self._pending_pullback_order_id = None
            self._pullback_order_expiry_ts = 0
            self._pullback_order_qty = None
            self._pullback_entry_metrics = None

    def _check_entry_signal(self, bar: Bar):
        """
        Evaluates market conditions for a Long Entry.

        V3.0 "Early Momentum Explosion" - Lift-off Trigger 入场逻辑：

        核心理念：
        - 捕捉动能爆发的起点，而非终点
        - 使用市价单 (Taker) 抓住行情启动的第一时间
        - 移除"等回调"逻辑，因为它捕捉的是疲惫动能

        入场条件：
        1. 趋势在 EMA200 之上 (Uptrend)
        2. 处于 Squeeze 状态至少 2 根 K 线 (BB 完全在 KC 内部)
        3. RS 加速检测:
           - Asset_Return_6h > BTC_Return_6h + 3% (短期显著跑赢大盘)
           - AND Asset_Return_6h > Asset_Return_24h (动能加速，非疲惫)
        4. Anti-Exhaustion: Close < Upper_BB (价格未在布林带外)
        5. BTC 4H > EMA200 (市场环境过滤)

        入场方式：MARKET ORDER (Taker)
        """
        self._debug_signal_checks += 1

        # 0. Position Check: 唯一持仓限制 - 每个币种同时只能持有一个仓位
        if self._has_open_position():
            return

        # 0.1 Pending Order Check: 如果已有待成交的回调限价单，不再下新单
        # V3.0: 此逻辑保留用于向后兼容，但 pullback_entry_enabled=False
        if self._has_pending_pullback_order():
            return

        # 0.2 排除 BTC 自交易：BTC 的 RS 相对自己永远是 0，无法产生有效信号
        if self.instrument_id == self.benchmark_id:
            return

        # 1. Data Sync Check: 确保 Asset 和 Benchmark 数据同步
        if not self._check_data_sync():
            self._filter_stats["data_not_synced"] += 1
            return

        # 2. Cooldown Check (同一个币种 24 小时内最多开仓 1 次)
        cooldown_ns = self.config.cooldown_period_hours * 3600 * 1_000_000_000
        if bar.ts_event < (self._last_entry_ts + cooldown_ns):
            self._filter_stats["in_cooldown"] += 1
            return

        # 3. Max Concurrency Check (Basic protection)
        open_positions = len(self.cache.positions_open())
        if open_positions >= self.config.max_concurrent_positions:
            self._filter_stats["max_positions"] += 1
            return

        # 4. Margin Usage Check: 保证金占用超过 80% 时停止新开仓
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

        # === V3.0 Lift-off Trigger Detection ===
        current_price = Decimal(str(bar.close))
        ema_slow = Decimal(str(self.ema_slow.value))

        # A. Trend Filter: Price > EMA200
        if current_price <= ema_slow:
            self._filter_stats["fail_trend"] += 1
            return

        # B. Squeeze Filter: BB(20,2) 完全在 KC(20,1.4) 内部
        if not self._is_squeeze:
            self._filter_stats["fail_squeeze"] += 1
            return

        # B.1 Squeeze Maturity Filter: 挤压状态必须连续保持至少 2 根 K 线
        # V3.0: 确保挤压是"真实"的蓄势，而非瞬间噪音
        if not self._is_squeeze_mature():
            self._filter_stats["fail_squeeze_maturity"] += 1
            return

        # C. V3.0 RS Acceleration Filter (核心变化)
        # 替代 V2.0 的阶梯式 RS，要求同时满足：
        # 1. Asset_6h > BTC_6h + 3%
        # 2. Asset_6h > Asset_24h (动能加速)
        rs_passed, rs_reason, asset_return_6h, rs_gap_6h = self._check_rs_acceleration()
        if not rs_passed:
            self._filter_stats["fail_rs"] += 1
            return

        # D. V3.0 Anti-Exhaustion Filter (替代 V2.0 Extension Filter)
        # Entry ONLY if: Close < Upper_BB
        # 如果价格已在布林带外，说明动能已释放（blow-off top），不入场
        if not self._check_anti_exhaustion(current_price):
            self._filter_stats["fail_extension"] += 1  # 复用 extension 统计键
            return

        # E. Benchmark 4H Filter (Bear Market Detector)
        if self.btc_ema_4h.initialized:
            btc_bar = self.cache.bar(self.btc_4h_bar_type)
            if btc_bar:
                btc_price = Decimal(str(btc_bar.close))
                btc_ema = Decimal(str(self.btc_ema_4h.value))
                if btc_price < btc_ema:
                    # Bear market -> Filter Longs
                    self._filter_stats["fail_btc_bear"] += 1
                    return

        # If we reached here, all conditions passed - Lift-off confirmed!
        self._filter_stats["all_passed"] += 1

        # 计算入场时的关键指标用于后期分析
        bb_width_pct = self._get_bb_width_percentile()
        rs_score = self._calculate_rs_score()

        # 计算成交量倍数用于记录
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

        # === V3.0: 直接市价入场 (Taker) ===
        # 不再等待回调，抓住动能爆发的第一时间
        if self.config.pullback_entry_enabled:
            # 保留 V2.0 回调逻辑用于向后兼容（默认禁用）
            self._place_pullback_limit_order(
                bar.ts_event, rs_reason, rs_score, bb_width_pct, volume_mult
            )
        else:
            # V3.0 默认逻辑：直接市价入场
            self._execute_entry(
                current_price,
                rs_reason,
                bar.ts_event,
                rs_score,
                bb_width_pct,
                volume_mult,
            )

    def _calculate_rs_score(self) -> Decimal:
        """
        计算当前的 RS Score：所有窗口中最大的 RS Gap。
        用于后期分析 Winner vs Loser 的特征差异。
        """
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
        """
        获取当前 BB Width 在历史分布中的分位数位置。
        用于后期分析。
        """
        if len(self.bb_widths) < 2:
            return Decimal("0.5")

        current_width = self.bb_widths[-1]
        sorted_widths = sorted(self.bb_widths)

        position = 0
        for w in sorted_widths:
            if w < current_width:
                position += 1
            else:
                break

        return Decimal(str(position / len(sorted_widths)))

    def _place_pullback_limit_order(
        self,
        ts_event: int,
        rs_window: str,
        rs_score: Decimal,
        bb_width_pct: Decimal,
        volume_mult: Decimal,
    ):
        """
        V2.0 核心方法：在 EMA(20) 价位挂限价买单等待回调。

        "Breakout-then-Pullback" 入场逻辑：
        - 检测到突破信号后，不立即市价买入
        - 在 EMA(20) 挂限价买单等待价格回调
        - 限价单 4 小时内未成交则取消
        - 止损 = Entry - 1.2 * ATR（更紧的止损，提高仓位和风险回报比）

        Args:
            ts_event: 信号触发时间戳 (纳秒)
            rs_window: 触发 RS 信号的时间窗口
            rs_score: RS Score 用于后期分析
            bb_width_pct: BB Width 分位数用于后期分析
            volume_mult: 成交量倍数用于后期分析
        """
        if not self.ema_fast.initialized or not self.atr.initialized:
            self.log.warning(
                f"⚠️ PULLBACK ORDER SKIP: {self.instrument_id} EMA/ATR not initialized."
            )
            return

        # 限价单入场价 = EMA(20)
        ema_fast = Decimal(str(self.ema_fast.value))
        limit_price = self.instrument.make_price(ema_fast)

        # 止损距离 = 1.2 * ATR (V2.0 更紧的止损)
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
                f"refusing to place pullback order on {self.instrument_id}"
            )
            return

        risk_amt = equity * Decimal(str(self.config.risk_per_trade))

        # 设计规范：Qty = Risk Amount / Risk Distance per Unit
        if risk_dist <= 0:
            return
        raw_qty = risk_amt / risk_dist

        # 🛡️ 杠杆封顶：计算实际杠杆并限制在 max_leverage 以内
        max_leverage = Decimal(str(self.config.max_leverage))
        notional_value = raw_qty * ema_fast
        effective_leverage = notional_value / equity

        if effective_leverage > max_leverage:
            # 重新计算仓位使杠杆不超过上限
            old_qty = raw_qty
            raw_qty = (equity * max_leverage) / ema_fast
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

        # 计算限价单过期时间
        expiry_ns = self.config.pullback_order_expiry_hours * 3600 * 1_000_000_000
        expiry_ts = ts_event + expiry_ns

        self.log.info(
            f"📥 PULLBACK LIMIT ORDER: {self.instrument_id} "
            f"Limit Buy @ EMA(20)={limit_price}, Qty={qty}, "
            f"SL_dist={risk_dist:.4f}, Expiry={self.config.pullback_order_expiry_hours}h"
        )

        # 1. Place Limit Buy Order at EMA(20)
        limit_order = self.order_factory.limit(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=qty,
            price=limit_price,
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(limit_order)

        # 保存限价单状态用于后续处理
        self._pending_pullback_order_id = str(limit_order.client_order_id)
        self._pullback_order_expiry_ts = expiry_ts
        self._pullback_order_qty = qty

        # 保存入场指标用于订单成交后记录
        self._pullback_entry_metrics = {
            "asset": str(self.instrument_id.symbol),
            "limit_price": float(ema_fast),
            "rs_window": rs_window,
            "rs_score": float(rs_score),
            "bb_width_pct": float(bb_width_pct),
            "volume_mult": float(volume_mult),
            "atr": float(atr),
            "order_ts": ts_event,
        }

    def _execute_entry(
        self,
        current_price: Decimal,
        rs_window: str,
        ts_event: int,
        rs_score: Decimal = Decimal("0"),
        bb_width_pct: Decimal = Decimal("0"),
        volume_mult: Decimal = Decimal("0"),
    ):
        """
        Executes entry orders with risk management.

        设计规范（复利风险模型）：
        - 单笔风险 = 账户余额 * 3% (Compounding)
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
            f"RS_Window={rs_window}, Qty={qty}, SL_dist={risk_dist:.2f}"
        )

        # 1. Market Buy
        entry_order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=qty,
        )
        self.submit_order(entry_order)

        # 2. Stop Loss (Stop Market)
        # 止损位 = Entry - 2 * ATR
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
        self._trailing_stop_active = False  # 重置追踪止损状态
        self._highest_high_since_entry = current_price  # 初始化最高价
        self._last_entry_ts = ts_event  # 记录入场时间用于 cooldown
        self._position_open_ts = ts_event  # 记录开仓时间用于 72h 强制平仓

        # 记录入场时的关键指标，用于交易关闭时输出分析
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
        """
        Manages open positions:

        V3.0 "Big Win" 出场逻辑 - 让利润奔跑：
        1. 止损由初始止损单处理 (Entry - 1.5 * ATR)
        2. 追踪止损：盈利 >= 2.5 * ATR 后激活，追踪止损 = Highest_High - 3.0 * ATR
        3. 🛡️ 紧急止损保护：如果价格跌破止损线但止损单未触发，强制平仓
        4. ⏰ 时间保护强制平仓：持仓超过 72 小时仍未触发止盈止损，强制市价平仓

        V3.0 核心变化：
        - **移除** EMA 趋势退出 (会扼杀赢家，导致 Avg Winner 过低)
        - 追踪止损更宽松 (3.0 * ATR)，给利润更多呼吸空间
        - 目标：捕捉 30u+ 的 Max Winner，而非 0.6u 的小赢
        """
        positions = self.cache.positions_open(instrument_id=self.instrument_id)
        if not positions:
            return
        position = positions[0]

        current_price = Decimal(str(bar.close))
        current_high = Decimal(str(bar.high))

        # 更新入场后最高价（用于追踪止损）
        if self._highest_high_since_entry is not None:
            self._highest_high_since_entry = max(
                self._highest_high_since_entry, current_high
            )
        else:
            self._highest_high_since_entry = current_high

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

        # 📈 V3.0 追踪止损逻辑 (Trailing Stop - "Big Win" Focus)
        # 盈利 >= 2.5 * ATR 后激活追踪止损
        # 追踪距离 = 3.0 * ATR (更宽松，让利润奔跑)
        if self._entry_price and self.atr.initialized and position.is_long:
            atr = Decimal(str(self.atr.value))
            profit = current_price - self._entry_price
            trigger_profit = atr * Decimal(str(self.config.trailing_stop_trigger_mult))

            if profit >= trigger_profit:
                # 追踪止损激活或更新
                if self._highest_high_since_entry:
                    # V3.0: 追踪止损价 = Highest_High - 3.0 * ATR (更宽松)
                    trailing_sl_price = self._highest_high_since_entry - (
                        atr * Decimal(str(self.config.trailing_stop_atr_mult))
                    )

                    # 确保追踪止损价至少在保本价之上
                    breakeven_price = self._entry_price * (
                        1 + Decimal(str(self.config.breakeven_offset))
                    )
                    trailing_sl_price = max(trailing_sl_price, breakeven_price)

                    if not self._trailing_stop_active:
                        # 首次激活追踪止损
                        self.log.info(
                            f"📈 TRAILING STOP ACTIVATED (V3.0 Big Win): {self.instrument_id} "
                            f"profit {profit:.4f} >= {trigger_profit:.4f}. "
                            f"Trailing SL = {trailing_sl_price:.4f} (HH - {self.config.trailing_stop_atr_mult} * ATR)"
                        )
                        self._trailing_stop_active = True

                    # 更新止损单到追踪止损价
                    new_sl_price = self.instrument.make_price(trailing_sl_price)

                    # Cancel old SLs and submit new one
                    self.cancel_all_orders(self.instrument_id)
                    sl_order = self.order_factory.stop_market(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.SELL,
                        quantity=position.quantity,
                        trigger_price=new_sl_price,
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(sl_order)

        # V3.0: 移除 EMA 趋势退出
        # V2.0 的 EMA 趋势退出会扼杀赢家，导致 Avg Winner 仅 0.67 USDT
        # V3.0 仅依靠追踪止损让利润奔跑，目标 Avg Winner >= 5.0 USDT
        #
        # 如果需要启用趋势退出（向后兼容），可通过 config.ema_trend_exit_enabled 控制
        if getattr(self.config, "ema_trend_exit_enabled", False):
            if self.ema_trend_exit.initialized and position.is_long:
                ema_trend_exit = Decimal(str(self.ema_trend_exit.value))
                if current_price < ema_trend_exit:
                    # 仅在有盈利时才执行趋势退出
                    if self._entry_price and current_price > self._entry_price:
                        pnl_pct = (
                            (current_price - self._entry_price)
                            / self._entry_price
                            * 100
                        )
                        self.log.info(
                            f"📉 TREND EXIT (Legacy): {self.instrument_id} price {current_price:.4f} "
                            f"< EMA50 {ema_trend_exit:.4f}. Closing with +{pnl_pct:.2f}% profit."
                        )
                        self.cancel_all_orders(self.instrument_id)
                        close_order = self.order_factory.market(
                            instrument_id=self.instrument_id,
                            order_side=OrderSide.SELL,
                            quantity=position.quantity,
                        )
                        self.submit_order(close_order)
                        return

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

    def on_order_filled(self, event):
        """
        V2.0 核心回调：处理限价单成交后的止损设置。

        当回调限价买单成交时：
        1. 设置止损单 = Entry - 1.2 * ATR
        2. 更新入场状态变量
        3. 记录入场指标用于后期分析
        """
        super().on_order_filled(event)

        # 检查是否为我们的回调限价买单
        if self._pending_pullback_order_id is None:
            return

        order_id = str(event.client_order_id)
        if order_id != self._pending_pullback_order_id:
            return

        # 限价买单已成交！
        fill_price = Decimal(str(event.last_px))
        fill_qty = event.last_qty

        self.log.info(
            f"✅ PULLBACK LIMIT ORDER FILLED: {self.instrument_id} "
            f"Entry @ {fill_price}, Qty={fill_qty}"
        )

        # 设置止损单 = Entry - 1.2 * ATR
        if self._pullback_entry_metrics and "atr" in self._pullback_entry_metrics:
            atr = Decimal(str(self._pullback_entry_metrics["atr"]))
            risk_dist = atr * Decimal(str(self.config.stop_loss_mult))
            sl_price_raw = fill_price - risk_dist
            sl_price = self.instrument.make_price(sl_price_raw)

            sl_order = self.order_factory.stop_market(
                instrument_id=self.instrument_id,
                order_side=OrderSide.SELL,
                quantity=fill_qty,
                trigger_price=sl_price,
                time_in_force=TimeInForce.GTC,
            )
            self.submit_order(sl_order)

            self.log.info(
                f"🛡️ STOP LOSS SET: {self.instrument_id} SL @ {sl_price} "
                f"(Entry - {self.config.stop_loss_mult} * ATR)"
            )

        # 更新入场状态
        self._entry_price = fill_price
        self._breakeven_triggered = False
        self._trailing_stop_active = False
        self._highest_high_since_entry = fill_price
        self._last_entry_ts = event.ts_event
        self._position_open_ts = event.ts_event

        # 记录入场指标用于交易关闭时分析
        if self._pullback_entry_metrics:
            self._entry_metrics[str(self.instrument_id)] = {
                "asset": self._pullback_entry_metrics["asset"],
                "entry_price": float(fill_price),
                "rs_window": self._pullback_entry_metrics["rs_window"],
                "rs_score": self._pullback_entry_metrics["rs_score"],
                "bb_width_pct": self._pullback_entry_metrics["bb_width_pct"],
                "volume_mult": self._pullback_entry_metrics["volume_mult"],
                "entry_ts": event.ts_event,
            }

        # 清理待成交状态
        self._pending_pullback_order_id = None
        self._pullback_order_expiry_ts = 0
        self._pullback_order_qty = None
        self._pullback_entry_metrics = None

    def on_order_canceled(self, event):
        """
        V2.0 回调：处理限价单被取消的状态清理。

        当回调限价买单被取消（过期或手动取消）时：
        - 清理待成交状态变量
        """
        super().on_order_canceled(event)

        # 检查是否为我们的回调限价买单
        if self._pending_pullback_order_id is None:
            return

        order_id = str(event.client_order_id)
        if order_id != self._pending_pullback_order_id:
            return

        # 限价买单已取消，清理状态
        self.log.debug(
            f"📤 PULLBACK ORDER CANCELED: {self.instrument_id} "
            f"Order {order_id} was canceled."
        )

        self._pending_pullback_order_id = None
        self._pullback_order_expiry_ts = 0
        self._pullback_order_qty = None
        self._pullback_entry_metrics = None

    def on_position_closed(self, event):
        super().on_position_closed(event)
        # Record exit timestamp for Cooldown (保留以便调试)
        self._last_exit_ts = self.clock.timestamp_ns()

        # 输出交易关闭时的详细信息并收集到类变量供统一输出
        instrument_key = str(self.instrument_id)
        if instrument_key in self._entry_metrics:
            metrics = self._entry_metrics[instrument_key]
            # 计算 PnL
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

            # 收集到类变量供回测结束后统一输出
            trade_record = {
                "asset": metrics["asset"],
                "result": result,
                "pnl_pct": float(pnl_pct),
                "entry_rs_score": metrics["rs_score"],
                "entry_bb_width_pct": metrics["bb_width_pct"],
                "entry_volume_mult": metrics["volume_mult"],
            }
            RSSqueezeStrategy._all_trade_metrics.append(trade_record)

            self.log.info(
                f"📈 TRADE CLOSED [{result}]: {metrics['asset']} | "
                f"RS_Score={metrics['rs_score']:.4f} | "
                f"BB_Width_Pct={metrics['bb_width_pct']:.2f} | "
                f"Volume_Mult={metrics['volume_mult']:.2f} | "
                f"PnL={pnl_pct:+.2f}%"
            )

            # 清理已关闭的记录
            del self._entry_metrics[instrument_key]

    def on_stop(self):
        """Log debugging summary."""
        # 将本实例的过滤器统计保存到类变量，供回测结束后统一输出
        if self._debug_signal_checks > 0:
            RSSqueezeStrategy._all_filter_stats[str(self.instrument_id)] = {
                "signal_checks": self._debug_signal_checks,
                **self._filter_stats.copy(),
            }

        self.cancel_all_orders(self.instrument_id)
        self.close_all_positions(self.instrument_id)

    @classmethod
    def get_filter_stats_summary(cls) -> Dict[str, Dict[str, int]]:
        """
        获取所有实例的过滤器统计汇总。
        供 engine_high.py 在回测结束后调用并统一输出。
        """
        return cls._all_filter_stats.copy()

    @classmethod
    def get_trade_metrics(cls) -> list:
        """
        获取所有交易的入场指标记录。
        供 engine_high.py 在回测结束后调用并统一输出。
        """
        return cls._all_trade_metrics.copy()

    @classmethod
    def reset_class_stats(cls):
        """
        重置类变量统计数据。
        在每次回测开始前调用，避免多次回测数据累积。
        """
        cls._all_filter_stats.clear()
        cls._all_trade_metrics.clear()

    @classmethod
    def print_filter_stats_report(cls):
        """
        打印格式化的过滤器统计汇总报告。
        供 engine_high.py 在回测结束后调用。
        V3.0: 更新为 "Early Momentum Explosion" 报告格式。
        """
        if not cls._all_filter_stats:
            return

        # 汇总所有实例的统计
        total_stats = {
            "signal_checks": 0,
            "no_breakout_level": 0,
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
            "fail_breakout": 0,
            "fail_volume": 0,
            "fail_btc_bear": 0,
            "all_passed": 0,
        }

        for inst_id, stats in cls._all_filter_stats.items():
            for key in total_stats:
                total_stats[key] += stats.get(key, 0)

        # 打印汇总报告
        print("\n" + "=" * 70)
        print("📊 FILTER STATISTICS SUMMARY (V3.0 Early Momentum Explosion)")
        print("=" * 70)
        print(f"Total Instruments: {len(cls._all_filter_stats)}")
        print(f"Total Signal Checks: {total_stats['signal_checks']:,}")
        print("-" * 70)
        print("PRE-CHECKS (Infrastructure):")
        print(f"  data_not_synced:      {total_stats['data_not_synced']:>8,}")
        print(f"  in_cooldown:          {total_stats['in_cooldown']:>8,}")
        print(f"  max_positions:        {total_stats['max_positions']:>8,}")
        print(f"  margin_limit:         {total_stats['margin_limit']:>8,}")
        print("-" * 70)
        print("CORE FILTERS (V3.0 Lift-off Trigger):")
        print(
            f"  fail_trend:           {total_stats['fail_trend']:>8,}  (Price < EMA200)"
        )
        print(
            f"  fail_squeeze:         {total_stats['fail_squeeze']:>8,}  (Not in Squeeze)"
        )
        print(
            f"  fail_squeeze_maturity:{total_stats['fail_squeeze_maturity']:>8,}  (Squeeze < 2 bars)"
        )
        print(
            f"  fail_rs:              {total_stats['fail_rs']:>8,}  (RS Acceleration not met)"
        )
        print(
            f"  fail_extension:       {total_stats['fail_extension']:>8,}  (Anti-Exhaustion: Close >= Upper_BB)"
        )
        print(
            f"  fail_btc_bear:        {total_stats['fail_btc_bear']:>8,}  (BTC 4H < EMA200)"
        )
        print("-" * 70)
        print(
            f"🚀 ALL_PASSED (Lift-off): {total_stats['all_passed']:>8,}  (→ MARKET ORDER 入场)"
        )
        print("=" * 70)
        print(
            "📝 V3.0 说明: RS 加速检测 (6h > BTC+3% AND 6h > 24h) + 防疲惫过滤 (Close < Upper_BB)"
        )
        print("   目标: Avg Winner >= 5.0 USDT, 捕捉 30u+ 的 Max Winner")

        # 打印交易指标分析（如果有交易）
        if cls._all_trade_metrics:
            winners = [t for t in cls._all_trade_metrics if t["result"] == "WINNER"]
            losers = [t for t in cls._all_trade_metrics if t["result"] == "LOSER"]

            print("\n" + "=" * 70)
            print("📈 TRADE METRICS ANALYSIS (V3.0 Early Momentum Explosion)")
            print("=" * 70)
            print(
                f"Total Trades: {len(cls._all_trade_metrics)} | Winners: {len(winners)} | Losers: {len(losers)}"
            )

            # 计算 Avg Winner / Avg Loser
            if winners:
                avg_pnl_win = sum(t["pnl_pct"] for t in winners) / len(winners)
            else:
                avg_pnl_win = 0
            if losers:
                avg_pnl_lose = sum(t["pnl_pct"] for t in losers) / len(losers)
            else:
                avg_pnl_lose = 0

            print("\nPnL Summary:")
            print(f"  Avg Winner PnL:  {avg_pnl_win:+.2f}%")
            print(f"  Avg Loser PnL:   {avg_pnl_lose:+.2f}%")
            if losers and avg_pnl_lose != 0:
                rr_ratio = abs(avg_pnl_win / avg_pnl_lose)
                print(f"  R/R Ratio:       {rr_ratio:.2f}")

            if winners:
                avg_rs_win = sum(t["entry_rs_score"] for t in winners) / len(winners)
                avg_bb_win = sum(t["entry_bb_width_pct"] for t in winners) / len(
                    winners
                )
                avg_vol_win = sum(t["entry_volume_mult"] for t in winners) / len(
                    winners
                )
                print("\nWINNERS (avg entry metrics):")
                print(f"  RS_Score:       {avg_rs_win:.4f}")
                print(f"  BB_Width_Pct:   {avg_bb_win:.2f}")
                print(f"  Volume_Mult:    {avg_vol_win:.2f}")

            if losers:
                avg_rs_lose = sum(t["entry_rs_score"] for t in losers) / len(losers)
                avg_bb_lose = sum(t["entry_bb_width_pct"] for t in losers) / len(losers)
                avg_vol_lose = sum(t["entry_volume_mult"] for t in losers) / len(losers)
                print("\nLOSERS (avg entry metrics):")
                print(f"  RS_Score:       {avg_rs_lose:.4f}")
                print(f"  BB_Width_Pct:   {avg_bb_lose:.2f}")
                print(f"  Volume_Mult:    {avg_vol_lose:.2f}")

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
        self.asset_highs.clear()
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
        # Reset Pullback Entry state (V2.0 新增)
        self._pending_pullback_order_id = None
        self._pullback_order_expiry_ts = 0
        self._pullback_order_qty = None
        self._pullback_entry_metrics = None
        # Reset filter stats
        for key in self._filter_stats:
            self._filter_stats[key] = 0
        # Reset entry metrics
        self._entry_metrics.clear()
