from collections import deque
from decimal import Decimal
from typing import Optional

from nautilus_trader.indicators import (
    AverageTrueRange,
    BollingerBands,
    ExponentialMovingAverage,
    KeltnerChannel,
)
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId

from strategy.base import BaseStrategy, BaseStrategyConfig


class RSSqueezeConfig(BaseStrategyConfig):
    """
    RS-Squeeze 策略配置参数
    """

    bar_type: str = ""
    benchmark_id: str = "BTCUSDT.BINANCE"

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
    rs_threshold: float = 1.02

    # 风控与仓位参数
    risk_per_trade: float = 0.03  # 每笔交易风险比例 (3%)
    breakeven_mult: float = 1.5  # 价格达到 1.5*ATR 利润时移动止损
    breakeven_offset: float = 0.002  # 移动到 Entry + 0.2%
    stop_loss_mult: float = 1.5  # 初始止损 ATR 倍数


class RSSqueezeStrategy(BaseStrategy):
    """
    RS-Squeeze 策略实现 (NautilusTrader)

    策略逻辑:
    1. 订阅资产与基准 (BTC) 的 1H Bar 数据。
    2. 计算指标: Bollinger Bands, Keltner Channels, ATR, EMA20, EMA200。
    3. 相对强弱 (RS): (Asset_Ret / BTC_Ret) > 1.02。
    4. Squeeze 条件: Bollinger Width < Keltner Width。
    5. 做多入场: RS 走强且处于 Squeeze 状态，且价格在 EMA200 之上，突破前 2 根 Bar 最高价。
    6. 仓位管理: 基于 3% 账户风险计算下单量。
    7. 止损管理: 初始 1.5*ATR 止损，获利 1.5*ATR 后移至保本(Entry + 0.2%)。
    8. 趋势离场: 收盘跌破 EMA20。
    """

    def __init__(self, config: RSSqueezeConfig):
        super().__init__(config)

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

        # 状态变量与历史缓冲区
        self.asset_closes = deque(maxlen=config.rs_lookback + 1)
        self.benchmark_closes = deque(maxlen=config.rs_lookback + 1)
        self.asset_highs = deque(maxlen=2)

        self._is_squeeze = False
        self._entry_price: Optional[Decimal] = None
        self._breakeven_triggered = False

        # 日志节流
        self._last_warmup_log = 0

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
        if bar.instrument_id == self.benchmark_id:
            self.benchmark_closes.append(Decimal(str(bar.close)))
            return

        # B. 更新交易品种数据
        if bar.instrument_id == self.instrument_id:
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

            # 更新 Squeeze 状态
            self._update_squeeze_state()

            # 检查仓位
            position = self.cache.position_open(self.instrument_id)

            if position:
                self._manage_exit_and_trailing(bar, position)
            else:
                self._check_entry_signal(bar)

            # 存储 High 用于下一根 Bar 的突破判定
            self.asset_highs.append(Decimal(str(bar.high)))

    def _is_warmed_up(self) -> bool:
        """
        指标与数据窗口热身判定
        """
        return (
            self.ema_slow.initialized
            and self.bb.initialized
            and self.kc.initialized
            and len(self.asset_closes) > self.config.rs_lookback
            and len(self.benchmark_closes) > self.config.rs_lookback
        )

    def _update_squeeze_state(self):
        """
        计算 Squeeze 状态: BB_Width < KC_Width
        """
        bb_width = Decimal(str(self.bb.upper.value - self.bb.lower.value))
        kc_width = Decimal(str(self.kc.upper.value - self.kc.lower.value))

        was_squeeze = self._is_squeeze
        self._is_squeeze = bb_width < kc_width

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
            qty = self.instrument.make_qty(raw_qty)

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
                trigger_price = self.instrument.make_price(sl_price)
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
                trigger_price = self.instrument.make_price(be_price)

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
