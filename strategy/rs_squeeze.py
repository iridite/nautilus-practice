import json
import os
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal
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
from nautilus_trader.model.position import Position

from strategy.base import BaseStrategy, BaseStrategyConfig


class RSSqueezeConfig(BaseStrategyConfig):
    """
    RS-Squeeze 策略配置参数
    """

    bar_type: str = ""
    benchmark_id: str = "BTCUSDT.BINANCE"

    # Universe 参数
    universe_filepath: Optional[str] = None

    # 指标参数
    bb_period: int = 20
    bb_std: float = 2.0
    kc_period_ema: int = 20
    kc_period_atr: int = 20
    kc_mult: float = 1.5
    atr_period: int = 20
    ema_fast_period: int = 20
    ema_slow_period: int = 200

    # RS 参数
    rs_lookback: int = 24  # 1H K线，24周期即 24h
    rs_threshold: float = 1.05

    # 风控与仓位参数
    risk_per_trade: float = 0.03  # 每笔交易风险比例 (3%)
    breakeven_mult: float = 2.5  # 价格达到 1.5*ATR 利润时移动止损
    breakeven_offset: float = 0.002  # 移动到 Entry + 0.2%
    stop_loss_mult: float = 2.0  # 初始止损 ATR 倍数

    # 新增过滤与限制参数
    max_concurrent_positions: int = 3
    cooldown_period_hours: int = 24
    squeeze_threshold_mult: float = 0.9
    btc_ema_period: int = 200


class RSSqueezeStrategy(BaseStrategy):
    """
    RS-Squeeze 策略实现 (NautilusTrader)

    策略逻辑:
    1. 订阅资产与基准 (BTC) 的 1H Bar 数据。
    2. 计算指标: Bollinger Bands, Keltner Channels, ATR, EMA20, EMA200。
    3. 相对强弱 (RS): (Asset_Ret / BTC_Ret) > 1.02。
    4. Squeeze 条件: Bollinger Width < Keltner Width。
    5. 做多入场: RS 走强且处于 Squeeze 状态，且价格在 EMA200 之上，突破前 2 根 Bar 最高价。
    6. 动态 Universe 过滤: 只有在当前月份属于合法 Universe 池时才允许开新仓。
    7. 仓位管理: 基于 3% 账户风险计算下单量。
    8. 止损管理: 初始 1.5*ATR 止损，获利 1.5*ATR 后移至保本(Entry + 0.2%)。
    9. 趋势离场: 收盘跌破 EMA20。
    """

    def __init__(self, config: RSSqueezeConfig):
        super().__init__(config)
        # print(f"config: {self.config}")
        # 不太理解，应该是在执行完父类的 __init__ 方法后，`self.config` 已经被初始化了。
        # 因此，这里可以使用 `self.config` 来获取配置信息。

        # 解析标识符
        self.instrument_id = (
            InstrumentId.from_str(config.instrument_id)
            if isinstance(config.instrument_id, str)
            else config.instrument_id
        )
        self.benchmark_id = (
            InstrumentId.from_str(config.benchmark_id)
            if isinstance(config.benchmark_id, str)
            else config.benchmark_id
        )
        self.bar_type = (
            BarType.from_str(config.bar_type)
            if isinstance(config.bar_type, str)
            else config.bar_type
        )

        # 初始化指标
        self.bb = BollingerBands(config.bb_period, config.bb_std)
        self.kc = KeltnerChannel(config.kc_period_ema, config.kc_mult)
        self.atr = AverageTrueRange(config.atr_period)
        self.ema_fast = ExponentialMovingAverage(config.ema_fast_period)
        self.ema_slow = ExponentialMovingAverage(config.ema_slow_period)
        self.btc_ema_4h = ExponentialMovingAverage(config.btc_ema_period)

        # 状态变量与历史缓冲区
        self.asset_closes = deque(maxlen=config.rs_lookback + 1)
        self.benchmark_closes = deque(maxlen=config.rs_lookback + 1)
        self.asset_highs = deque(maxlen=2)

        self._is_squeeze = False
        self._entry_price: Optional[Decimal] = None
        self._breakeven_triggered = False
        self._last_exit_time: int = 0

        # Universe 配置
        self._universe_config: Dict[str, Set[str]] = {}
        self._current_month: str = ""
        self._is_in_universe: bool = False
        self._load_universe()

        # 日志节流
        self._last_warmup_log = 0

    def _load_universe(self):
        """
        加载 Universe 配置文件
        """
        file_path = self.config.universe_filepath
        if file_path:
            try:
                with open(file_path, "r") as f:
                    raw_data = json.load(f)
                    # 预处理为 Set 以提高检索效率
                    self._universe_config = {k: set(v) for k, v in raw_data.items()}
                self.log.info(f"Loaded universe config from {file_path}")
            except Exception as e:
                self.log.error(f"Error loading universe config: {e}")
        else:
            self.log.error(f"Universe file not found: {self.config.universe_filepath}")

    def on_start(self):
        """
        策略启动逻辑
        """
        super().on_start()

        if self.instrument is None:
            self.instrument = self.cache.instrument(self.instrument_id)
            if self.instrument is None:
                self.log.error(f"Could not find instrument: {self.instrument_id}")
                self.stop()
                return

        # 订阅行情
        self.subscribe_bars(self.bar_type)
        # 订阅基准品种 1H 数据
        benchmark_bar_type = BarType(self.benchmark_id, self.bar_type.spec)
        self.subscribe_bars(benchmark_bar_type)

        # 订阅基准品种 4H 数据 (用于大盘过滤)
        # 构造 4H spec，保留原始数据的价格类型 (MIDPOINT/LAST等)
        spec_str = str(self.bar_type.spec)
        spec_parts = spec_str.split("-")
        if len(spec_parts) >= 3:
            btc_4h_spec_str = f"4-HOUR-{spec_parts[2]}"
        else:
            btc_4h_spec_str = "4-HOUR-MIDPOINT"
        self.btc_4h_bar_type = BarType(
            self.benchmark_id, BarSpecification.from_str(btc_4h_spec_str)
        )
        self.subscribe_bars(self.btc_4h_bar_type)

        self.log.info(f"RS-Squeeze Strategy started for {self.instrument_id}")
        self.log.info(
            f"Benchmark: {self.benchmark_id}, Risk: {self.config.risk_per_trade:.1%}"
        )

    def on_bar(self, bar: Bar):
        """
        处理逐根 Bar 逻辑
        """
        # 调用基类逻辑 (BaseStrategy 中可能包含自动化风控)
        super().on_bar(bar)

        # A. 更新基准品种 (BTC) 数据
        if bar.bar_type == self.btc_4h_bar_type:
            self.btc_ema_4h.handle_bar(bar)
            return

        if bar.bar_type.instrument_id == self.benchmark_id:
            # 仅使用与交易周期相同的 Bar 更新 RS 基准
            if bar.bar_type.spec == self.bar_type.spec:
                self.benchmark_closes.append(Decimal(str(bar.close)))
            return

        # B. 更新交易品种数据
        if bar.bar_type.instrument_id == self.instrument_id:
            self.asset_closes.append(Decimal(str(bar.close)))

            # 更新指标
            self.bb.handle_bar(bar)
            self.kc.handle_bar(bar)
            self.atr.handle_bar(bar)
            self.ema_fast.handle_bar(bar)
            self.ema_slow.handle_bar(bar)

            # 检查系统热身
            if not self._is_warmed_up():
                total_bars = len(self.cache.bars(self.bar_type))
                if total_bars // 100 > self._last_warmup_log:
                    self._last_warmup_log = total_bars // 100
                    self.log.info(
                        f"Warming up indicators... Asset Hist: {len(self.asset_closes)}/{self.config.rs_lookback + 1}"
                    )
                return

            # --- Universe 时效性检查 ---
            self._update_universe_status(bar.ts_event)

            # 检查仓位
            positions = self.cache.positions_open(instrument_id=self.instrument_id)

            if positions:
                # 如果有持仓，无论是否在 Universe 内，都必须允许该仓位继续运行（直到触发止损或 EMA20）
                self._manage_exit_and_trailing(bar, positions[0])
            elif self._is_in_universe:
                # 只有在 Universe 内才允许计算 Squeeze 信号及开新仓
                self._update_squeeze_state()
                self._check_entry_signal(bar)

            # 存储 High 用于下一根 Bar 的突破判定
            self.asset_highs.append(Decimal(str(bar.high)))

    def _update_universe_status(self, ts_event: int):
        """
        更新当前时间戳对应的 Universe 状态
        """
        if not self._universe_config:
            self._is_in_universe = True
            return

        # 获取月份 key (YYYY-MM)
        dt = datetime.fromtimestamp(ts_event / 1e9, tz=timezone.utc)
        month_str = dt.strftime("%Y-%m")

        # 仅在月份变化时更新检索
        if month_str != self._current_month:
            self._current_month = month_str
            month_universe = self._universe_config.get(month_str, set())

            # 兼容多种 Symbol 格式
            # 1. 基础/报价货币组合 (e.g. SOLUSDT)
            # 2. 带冒号格式 (e.g. SOLUSDT:USDT)
            # 3. 原始 Symbol (e.g. SOL-USDT-SWAP)
            # 4. 完整 ID (e.g. SOL-USDT-SWAP.OKX)
            base = self.instrument.base_currency.code
            quote = self.instrument.quote_currency.code
            simple_pair = f"{base}{quote}"
            colon_pair = f"{simple_pair}:{quote}"
            symbol = self.instrument_id.symbol
            full_id = str(self.instrument_id)

            self._is_in_universe = (
                simple_pair in month_universe
                or colon_pair in month_universe
                or symbol in month_universe
                or full_id in month_universe
            )

            if self._is_in_universe:
                self.log.debug(f"{self.instrument_id} is in Universe for {month_str}")

    def _is_warmed_up(self) -> bool:
        """
        指标与数据窗口热身判定
        """
        return (
            self.ema_slow.initialized
            and self.bb.initialized
            and self.kc.initialized
            and self.btc_ema_4h.initialized
            and len(self.asset_closes) > self.config.rs_lookback
            and len(self.benchmark_closes) > self.config.rs_lookback
        )

    def _update_squeeze_state(self):
        """
        计算 Squeeze 状态: BB_Width < KC_Width
        """
        # 获取指标值，兼容不同版本的 Nautilus (可能是 float 或 Indicator 对象)
        bb_upper = getattr(self.bb.upper, "value", self.bb.upper)
        bb_lower = getattr(self.bb.lower, "value", self.bb.lower)
        kc_upper = getattr(self.kc.upper, "value", self.kc.upper)
        kc_lower = getattr(self.kc.lower, "value", self.kc.lower)

        bb_width = Decimal(str(bb_upper - bb_lower))
        kc_width = Decimal(str(kc_upper - kc_lower))

        was_squeeze = self._is_squeeze
        # 优化 Squeeze 触发质量: BB_width < (KC_width * 0.9)
        self._is_squeeze = bb_width < (
            kc_width * Decimal(str(self.config.squeeze_threshold_mult))
        )

        if self._is_squeeze and not was_squeeze:
            self.log.info(
                f"Squeeze Entered: BB_Width({bb_width:.4f}) < KC_Width({kc_width:.4f})"
            )
        elif not self._is_squeeze and was_squeeze:
            self.log.info(
                f"Squeeze Exited: BB_Width({bb_width:.4f}) >= KC_Width({kc_width:.4f})"
            )

    def _calculate_rs(self) -> Decimal:
        """
        计算 Relative Strength (RS)
        RS = (Asset_Close / Asset_Close_24h) / (BTC_Close / BTC_Close_24h)
        """
        asset_ret = self.asset_closes[-1] / self.asset_closes[0]
        bench_ret = self.benchmark_closes[-1] / self.benchmark_closes[0]
        return asset_ret / bench_ret

    def _check_entry_signal(self, bar: Bar):
        """
        检查入场信号
        """
        if len(self.asset_highs) < 2:
            return

        current_price = Decimal(str(bar.close))
        rs_value = self._calculate_rs()
        ema_slow_val = Decimal(str(self.ema_slow.value))
        breakout_level = max(self.asset_highs)

        # 核心判定逻辑 (Long Only)
        rs_condition = rs_value > Decimal(str(self.config.rs_threshold))
        trend_condition = current_price > ema_slow_val
        breakout_condition = current_price > breakout_level

        if rs_condition and self._is_squeeze and trend_condition and breakout_condition:
            # 1. 大盘趋势硬过滤: BTC 4H EMA200
            btc_bar = self.cache.bar_last(self.btc_4h_bar_type)
            if btc_bar:
                btc_price = Decimal(str(btc_bar.close))
                btc_ema = Decimal(str(self.btc_ema_4h.value))
                if btc_price < btc_ema:
                    self.log.info("Signal skipped: Bear market filter active.")
                    return

            # 2. 限制并发头寸 (Max 3)
            if len(self.cache.positions_open()) >= self.config.max_concurrent_positions:
                return

            # 3. 止损冷却期检查 (24 小时)
            cooldown_ns = self.config.cooldown_period_hours * 3_600 * 1_000_000_000
            if bar.ts_event < self._last_exit_time + cooldown_ns:
                return

            self.log.info(
                f"ENTRY SIGNAL: RS={rs_value:.4f}, Squeeze={self._is_squeeze}, "
                f"Price({current_price:.2f}) > EMA200({ema_slow_val:.2f}), "
                f"Breakout > {breakout_level:.2f}"
            )

            # --- 仓位计算 (Risk Management) ---
            atr_val = Decimal(str(self.atr.value))
            sl_dist = atr_val * Decimal(str(self.config.stop_loss_mult))

            if sl_dist <= 0:
                return

            # 获取账户余额 (优先取 quote currency 账户)
            accounts = self.cache.accounts()
            if not accounts:
                return
            account = next(
                (a for a in accounts if a.balance(self.instrument.quote_currency)),
                accounts[0],
            )
            balance = account.balance(self.instrument.quote_currency).total.as_decimal()
            risk_amount = balance * Decimal(str(self.config.risk_per_trade))

            # Quantity = Risk_Amount / (Entry_Price - Initial_SL)
            # 此处 Entry_Price - Initial_SL = sl_dist
            raw_qty = risk_amount / sl_dist
            try:
                qty = self.instrument.make_qty(raw_qty)
            except ValueError as e:
                self.log.warning(f"Quantity calculation error: {e}")
                return

            if qty > 0:
                # 市价买入
                order = self.order_factory.market(
                    instrument_id=self.instrument_id,
                    order_side=OrderSide.BUY,
                    quantity=qty,
                )
                self.submit_order_safe(order, reason="RS-Squeeze Long Entry")

                # 设置初始止损 (Stop Market)
                sl_price = current_price - sl_dist
                try:
                    trigger_price = self.instrument.make_price(sl_price)
                except ValueError as e:
                    self.log.warning(f"Price calculation error for initial SL: {e}")
                    return

                sl_order = self.order_factory.stop_market(
                    instrument_id=self.instrument_id,
                    order_side=OrderSide.SELL,
                    quantity=qty,
                    trigger_price=trigger_price,
                    time_in_force=TimeInForce.GTC,
                )
                self.submit_order_safe(sl_order, reason=f"Initial SL @ {trigger_price}")

                # 记录状态
                self._entry_price = current_price
                self._breakeven_triggered = False

    def _manage_exit_and_trailing(self, bar: Bar, position):
        """
        持仓管理: 移动止损与趋势离场
        """
        current_price = Decimal(str(bar.close))
        ema_fast_val = Decimal(str(self.ema_fast.value))
        atr_val = Decimal(str(self.atr.value))

        # 1. 趋势出场: 价格跌破 EMA20
        if current_price < ema_fast_val:
            self.log.info(
                f"EXIT SIGNAL: Price({current_price:.2f}) < EMA20({ema_fast_val:.2f})"
            )
            self.close_all_positions(self.instrument_id)
            self.cancel_all_orders(self.instrument_id)
            return

        # 2. 移动止损 (Trailing to Breakeven+)
        if not self._breakeven_triggered and self._entry_price:
            gain_target = atr_val * Decimal(str(self.config.breakeven_mult))
            if current_price >= self._entry_price + gain_target:
                # 止损移至 Entry + 0.2%
                be_price = self._entry_price * (
                    1 + Decimal(str(self.config.breakeven_offset))
                )
                try:
                    trigger_price = self.instrument.make_price(be_price)
                except ValueError as e:
                    self.log.warning(f"Price calculation error for breakeven SL: {e}")
                    return

                self.log.info(
                    f"TRAILING SL: Reached Entry + 1.5*ATR. Moving SL to {trigger_price} (BE+0.2%)"
                )

                # 取消所有待成交订单 (主要是旧的 SL) 并重新下达
                self.cancel_all_orders(self.instrument_id)

                sl_order = self.order_factory.stop_market(
                    instrument_id=self.instrument_id,
                    order_side=OrderSide.SELL,
                    quantity=position.quantity,
                    trigger_price=trigger_price,
                    time_in_force=TimeInForce.GTC,
                )
                self.submit_order_safe(
                    sl_order, reason=f"Breakeven SL Move @ {trigger_price}"
                )
                self._breakeven_triggered = True

    def on_position_closed(self, position: Position):
        """
        当仓位关闭时，记录退出时间以触发冷却期
        """
        super().on_position_closed(position)
        # 记录最后一次离场时间，用于同一个 instrument 的冷却期判定
        self._last_exit_time = self.clock.utc_now()
        self.log.info(
            f"Position closed for {position.instrument_id}, cooldown started."
        )

    def on_stop(self):
        """
        策略停止清理
        """
        self.cancel_all_orders(self.instrument_id)
        self.close_all_positions(self.instrument_id)
        self.log.info("RS-Squeeze Strategy stopped.")

    def on_reset(self):
        """
        策略重置
        """
        super().on_reset()
        self.bb.reset()
        self.kc.reset()
        self.atr.reset()
        self.ema_fast.reset()
        self.ema_slow.reset()
        self.asset_closes.clear()
        self.benchmark_closes.clear()
        self.asset_highs.clear()
        self._entry_price = None
        self._breakeven_triggered = False
        self._last_warmup_log = 0
        self._current_month = ""
        self._is_in_universe = False
        self._last_exit_time = 0
