"""
Dual Thrust 突破策略

经典的日内突破策略，基于前N天的价格范围计算动态通道。
"""

from decimal import Decimal

from nautilus_trader.model.data import Bar, BarType

from strategy.base import BaseStrategy, BaseStrategyConfig


class DualThrustConfig(BaseStrategyConfig):
    """Dual Thrust 策略配置"""

    instrument_id: str = ""
    bar_type: str = ""
    lookback_period: int = 4
    k1: float = 0.5
    k2: float = 0.5


class DualThrustStrategy(BaseStrategy):
    """
    Dual Thrust 突破策略

    计算逻辑：
    - Range = Max(HH - LC, HC - LL)
    - 上轨 = Open + k1 * Range
    - 下轨 = Open - k2 * Range
    """

    def __init__(self, config: DualThrustConfig):
        super().__init__(config)
        self.lookback_period = config.lookback_period
        self.k1 = config.k1
        self.k2 = config.k2

        self.highs = []
        self.lows = []
        self.closes = []

        self.upper_band = None
        self.lower_band = None
        self.position_opened = False

    def on_start(self):
        super().on_start()
        self.log.info(f"DualThrust 启动: lookback={self.lookback_period}, k1={self.k1}, k2={self.k2}")
        self.subscribe_bars(BarType.from_str(self.config.bar_type))

    def on_bar(self, bar: Bar):
        current_price = float(bar.close)

        self.highs.append(float(bar.high))
        self.lows.append(float(bar.low))
        self.closes.append(float(bar.close))

        if len(self.highs) <= self.lookback_period:
            return

        if len(self.highs) > self.lookback_period + 1:
            self.highs.pop(0)
            self.lows.pop(0)
            self.closes.pop(0)

        lookback_highs = self.highs[:-1]
        lookback_lows = self.lows[:-1]
        lookback_closes = self.closes[:-1]

        hh = max(lookback_highs)
        ll = min(lookback_lows)
        hc = max(lookback_closes)
        lc = min(lookback_closes)

        range_value = max(hh - lc, hc - ll)

        open_price = float(bar.open)
        self.upper_band = open_price + self.k1 * range_value
        self.lower_band = open_price - self.k2 * range_value

        self.log.debug(f"Bar {bar.ts_event}: price={current_price:.1f}, upper={self.upper_band:.1f}, lower={self.lower_band:.1f}, range={range_value:.1f}")

        if not self.position_opened:
            if current_price > self.upper_band:
                qty = self.calculate_order_qty(bar.close)
                if qty and qty > 0:
                    self.buy(qty)
                    self.position_opened = True
                    self.log.info(f"突破上轨做多: price={current_price:.2f}, upper={self.upper_band:.2f}")

            elif current_price < self.lower_band:
                qty = self.calculate_order_qty(bar.close)
                if qty and qty > 0:
                    self.sell(qty)
                    self.position_opened = True
                    self.log.info(f"突破下轨做空: price={current_price:.2f}, lower={self.lower_band:.2f}")

        else:
            if self.portfolio.is_net_long(bar.instrument_id):
                if current_price < self.lower_band:
                    self.close_all_positions(bar.instrument_id)
                    self.position_opened = False
                    self.log.info(f"多头止损: price={current_price:.2f}")

            elif self.portfolio.is_net_short(bar.instrument_id):
                if current_price > self.upper_band:
                    self.close_all_positions(bar.instrument_id)
                    self.position_opened = False
                    self.log.info(f"空头止损: price={current_price:.2f}")
