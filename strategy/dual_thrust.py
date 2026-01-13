from decimal import Decimal
from typing import Optional

from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId

from strategy.base import BaseStrategy, BaseStrategyConfig


class DualThrustConfig(BaseStrategyConfig):
    """
    Dual Thrust 策略配置参数
    继承自 BaseStrategyConfig，自动获得 trade_size, qty_percent, leverage 等通用参数
    """

    # instrument_id is inherited from BaseStrategyConfig

    bar_type: BarType | str = ""

    # 策略核心参数
    lookback_period: int = 4  # N: 回溯周期数
    k1: float = 0.5  # 上轨系数
    k2: float = 0.5  # 下轨系数

    # 其他风控
    use_trailing_stop: bool = False
    trailing_stop_pct: float = 0.02


class DualThrust(BaseStrategy):
    """
    Dual Thrust 策略实现 for NautilusTrader
    继承 BaseStrategy 以复用下单量计算与安全下单逻辑。

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
        # self.instrument 由 BaseStrategy.on_start() 统一初始化
        self.history_bars: list[Bar] = []  # 用于存储计算Range的历史K线

        self.current_range: Optional[Decimal] = None
        self.buy_line: Optional[Decimal] = None
        self.sell_line: Optional[Decimal] = None

    def on_start(self):
        """
        策略启动时调用
        """
        # 1. 调用父类 on_start 初始化 instrument
        super().on_start()

        # 确保 instrument 加载成功
        if self.instrument is None:
            # 尝试通过 instrument_id 再次获取 (防止父类只用了 config 里的 str)
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

    def _check_signals(self, bar: Bar):
        """
        信号检查与订单执行
        """
        if self.buy_line is None or self.sell_line is None:
            return

        current_price = bar.close
        # 获取当前所有的持仓
        positions = self.cache.positions_open(instrument_id=self.instrument_id)

        # 使用 BaseStrategy 统一提供的计算逻辑
        qty = self.calculate_order_qty(current_price)
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
                # 使用 BaseStrategy 的安全下单方法，自带日志和检查
                self.submit_order_safe(
                    order,
                    reason=f"Breakout ({current_price} > BuyLine {self.buy_line})",
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
                self.submit_order_safe(
                    order,
                    reason=f"Breakout ({current_price} < SellLine {self.sell_line})",
                )

    def on_stop(self):
        self.close_all_positions(self.instrument_id)
        self.log.info("Dual Thrust Strategy stopped.")

    def on_reset(self):
        """
        策略重置时调用，清除内部状态
        """
        super().on_reset()  # Reset BaseStrategy (instrument=None)
        self.history_bars.clear()
        self.current_range = None
        self.buy_line = None
        self.sell_line = None
