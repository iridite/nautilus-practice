from decimal import Decimal
from typing import Optional

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


class DualThrustConfig(StrategyConfig):
    """
    Dual Thrust 策略配置参数
    """

    instrument_id: InstrumentId | str
    bar_type: BarType | str

    # 策略核心参数
    lookback_period: int = 4  # N: 回溯周期数
    k1: float = 0.5  # 上轨系数
    k2: float = 0.5  # 下轨系数

    # 风控与资金管理
    trade_size: float = 0.01  # 每次交易数量 (根据Instrument精度调整)
    qty_percent: Decimal = Decimal("0.1")  # 仓位比例 (如使用杠杆)
    leverage: Optional[int] = None
    use_trailing_stop: bool = False
    trailing_stop_pct: float = 0.02


class DualThrust(Strategy):
    """
    Dual Thrust 策略实现 for NautilusTrader

    逻辑:
    1. 计算前N个周期的 HH, HC, LC, LL
    2. Range = max(HH - LC, HC - LL)
    3. BuyLine = CurrentOpen + K1 * Range
    4. SellLine = CurrentOpen - K2 * Range
    """

    def __init__(self, config: DualThrustConfig):
        super().__init__(config)

        # 解析配置
        if isinstance(config.instrument_id, InstrumentId):
            self.instrument_id = config.instrument_id
        else:
            self.instrument_id = InstrumentId.from_str(config.instrument_id)

        if isinstance(config.bar_type, BarType):
            self.bar_type = config.bar_type
        else:
            self.bar_type = BarType.from_str(config.bar_type)

        # 状态变量
        self.instrument: Optional[Instrument] = None
        self.history_bars: list[Bar] = []  # 用于存储计算Range的历史K线

        self.current_range: Optional[Decimal] = None
        self.buy_line: Optional[Decimal] = None
        self.sell_line: Optional[Decimal] = None

    def on_start(self):
        """
        策略启动时调用
        """
        # 1. 获取 Instrument 对象
        self.instrument = self.cache.instrument(self.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument: {self.instrument_id}")
            self.stop()
            return

        # 2. 订阅行情数据
        self.subscribe_bars(self.bar_type)

        self.log.info(f"Dual Thrust Strategy started for {self.instrument_id}")
        self.log.info(
            f"Params: N={self.config.lookback_period}, K1={self.config.k1}, K2={self.config.k2}"
        )

    def on_bar(self, bar: Bar):
        """
        处理新的 Bar 数据
        """
        # 1. 维护历史数据窗口 (Rolling Window)
        self.history_bars.append(bar)

        required_len = self.config.lookback_period + 1

        # 保持窗口大小
        if len(self.history_bars) > required_len:
            self.history_bars.pop(0)

        # 2. 检查数据预热进度 (无历史数据时保持静默)
        if len(self.history_bars) < required_len:
            self.log.info(
                f"Warming up... history bars: {len(self.history_bars)}/{required_len}"
            )
            return

        # 3. 计算 Dual Thrust 轨道
        self._calculate_thresholds()

        # 4. 执行交易逻辑
        self._check_signals(bar)

    def _calculate_thresholds(self):
        """
        计算上下轨核心逻辑
        """
        # 基于过去 N 个已完成 Bar 计算 Range
        reference_bars = self.history_bars[-self.config.lookback_period - 1 : -1]

        if len(reference_bars) < self.config.lookback_period:
            return

        # 提取数据序列
        highs = [b.high for b in reference_bars]
        lows = [b.low for b in reference_bars]
        closes = [b.close for b in reference_bars]

        # 计算 HH, HC, LC, LL
        hh = max(highs)
        hc = max(closes)
        lc = min(closes)
        ll = min(lows)

        # 计算 Range
        rng = max(hh - lc, hc - ll)
        self.current_range = rng

        # 以当前刚闭合的 Bar 的 Open 作为基准点 (或者上一个 Bar 的 Close)
        # 这里使用当前 Bar 的 Open
        current_open = self.history_bars[-1].open

        # 计算轨道
        k1 = Decimal(str(self.config.k1))
        k2 = Decimal(str(self.config.k2))

        self.buy_line = current_open + (rng * k1)
        self.sell_line = current_open - (rng * k2)

    def recommend_leverage(self) -> Optional[int]:
        """
        策略可以重写此方法以提供推荐的杠杆倍数。
        优先级：recommend_leverage() > config.leverage
        """
        return None

    def _calc_order_qty(self, price: Decimal) -> Quantity:
        """
        根据权益、比例和杠杆计算下单数量
        """
        try:
            accounts = self.cache.accounts()
            if not accounts:
                return self.instrument.make_qty(self.config.trade_size)

            account = accounts[0]
            balance = account.balance(self.instrument.quote_currency)
            if not balance or balance.total <= 0:
                return self.instrument.make_qty(self.config.trade_size)

            # 杠杆确定
            # 优先级：策略推荐 > 配置设定 > 默认1
            rec_leverage = self.recommend_leverage()
            leverage = (
                rec_leverage if rec_leverage is not None else self.config.leverage
            )
            leverage = leverage if leverage is not None else 1

            # 交易所上限检查 (instrument.max_leverage)
            if (
                hasattr(self.instrument, "max_leverage")
                and self.instrument.max_leverage
            ):
                if leverage > self.instrument.max_leverage:
                    leverage = self.instrument.max_leverage

            # 计算名义价值 = 权益 * 比例 * 杠杆
            target_notional = balance.total * self.config.qty_percent * leverage
            raw_qty = target_notional / price
            return self.instrument.make_qty(raw_qty)
        except Exception:
            # 容错：返回配置的固定数量
            return self.instrument.make_qty(self.config.trade_size)

    def _check_signals(self, bar: Bar):
        """
        信号检查与订单执行
        """
        if self.buy_line is None or self.sell_line is None:
            return

        current_price = bar.close
        # 获取当前所有的持仓
        positions = self.cache.positions_open(instrument_id=self.instrument_id)

        # 使用计算后的杠杆仓位数量
        qty = self._calc_order_qty(current_price)
        if qty <= 0:
            return

        # --- 逻辑 1: 做多突破 ---
        if current_price > self.buy_line:
            # 如果有空仓，先平掉所有空仓
            has_short = any(p.is_short for p in positions)
            if has_short:
                self.log.info("Closing existing short positions before going long")
                self.close_all_positions(self.instrument_id)
                positions = [p for p in positions if not p.is_short]

            # 无多头仓位则开多
            has_long = any(p.is_long for p in positions)
            if not has_long:
                order = self.order_factory.market(
                    instrument_id=self.instrument_id,
                    order_side=OrderSide.BUY,
                    quantity=qty,
                )
                self.submit_order(order)
                self.log.info(
                    f"BREAKOUT BUY triggered at {current_price} > {self.buy_line}"
                )

        # --- 逻辑 2: 做空突破 ---
        elif current_price < self.sell_line:
            # 如果有多仓，先平掉所有多仓
            has_long = any(p.is_long for p in positions)
            if has_long:
                self.log.info("Closing existing long positions before going short")
                self.close_all_positions(self.instrument_id)
                positions = [p for p in positions if not p.is_long]

            # 无空头仓位则开空
            has_short = any(p.is_short for p in positions)
            if not has_short:
                order = self.order_factory.market(
                    instrument_id=self.instrument_id,
                    order_side=OrderSide.SELL,
                    quantity=qty,
                )
                self.submit_order(order)
                self.log.info(
                    f"BREAKOUT SELL triggered at {current_price} < {self.sell_line}"
                )

    def on_stop(self):
        self.close_all_positions(self.instrument_id)
        self.log.info("Dual Thrust Strategy stopped.")

    def on_reset(self):
        """
        策略重置时调用，清除内部状态
        """
        self.instrument = None
        self.history_bars.clear()
        self.current_range = None
        self.buy_line = None
        self.sell_line = None
