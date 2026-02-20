"""
Dual Thrust 突破策略 - 重构版本

经典的日内突破策略，基于前N天的价格范围计算动态通道。

使用模块化组件：
- DualThrustIndicator: 计算动态通道
- DualThrustSignalGenerator: 生成交易信号
"""

from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide

from strategy.core.base import BaseStrategy, BaseStrategyConfig
from strategy.common.indicators import DualThrustIndicator
from strategy.common.signals import DualThrustSignalGenerator


class DualThrustConfig(BaseStrategyConfig):
    """Dual Thrust 策略配置"""

    # 简化配置字段（推荐使用）
    symbol: str = ""
    timeframe: str = ""
    price_type: str = "LAST"
    origination: str = "EXTERNAL"

    # 完整配置字段（向后兼容，自动从简化字段生成）
    instrument_id: str = ""
    bar_type: str = ""

    lookback_period: int = 4
    k1: float = 0.5
    k2: float = 0.5


class DualThrustStrategyRefactored(BaseStrategy):
    """
    Dual Thrust 突破策略 - 重构版本

    使用模块化组件实现，代码更简洁清晰。

    计算逻辑：
    - Range = Max(HH - LC, HC - LL)
    - 上轨 = Open + k1 * Range
    - 下轨 = Open - k2 * Range
    """

    def __init__(self, config: DualThrustConfig):
        super().__init__(config)

        # 使用模块化组件
        self.indicator = DualThrustIndicator(
            lookback_period=config.lookback_period,
            k1=config.k1,
            k2=config.k2,
        )

        self.signals = DualThrustSignalGenerator()

        # 持仓状态
        self.position_opened = False

    def on_start(self):
        super().on_start()
        self.log.info(
            f"DualThrust 启动 (重构版本): "
            f"lookback={self.config.lookback_period}, "
            f"k1={self.config.k1}, k2={self.config.k2}"
        )
        self.subscribe_bars(BarType.from_str(self.config.bar_type))

    def on_bar(self, bar: Bar):
        """处理 Bar 数据"""
        current_price = float(bar.close)
        open_price = float(bar.open)

        # 更新指标
        self.indicator.update(
            high=float(bar.high),
            low=float(bar.low),
            close=current_price,
            open_price=open_price,
        )

        # 等待指标准备好
        if not self.indicator.is_ready():
            return

        # 获取通道
        upper_band, lower_band = self.indicator.get_bands()

        # 调试日志
        self.log.debug(
            f"Bar {bar.ts_event}: price={current_price:.1f}, "
            f"upper={upper_band:.1f}, lower={lower_band:.1f}, "
            f"range={self.indicator.get_range():.1f}"
        )

        # 无持仓时检查入场信号
        if not self.position_opened:
            self._check_entry(bar, current_price, upper_band, lower_band)
        else:
            # 有持仓时检查出场信号
            self._check_exit(current_price, upper_band, lower_band)

    def _check_entry(
        self,
        bar: Bar,
        current_price: float,
        upper_band: float | None,
        lower_band: float | None,
    ):
        """检查入场信号"""
        # 检查做多信号
        if self.signals.check_long_entry(current_price, upper_band):
            self._open_long(bar, current_price, upper_band)

        # 检查做空信号
        elif self.signals.check_short_entry(current_price, lower_band):
            self._open_short(bar, current_price, lower_band)

    def _open_long(self, bar: Bar, current_price: float, upper_band: float | None):
        """开多仓"""
        qty = self.calculate_order_qty(bar.close)
        if qty and qty > 0:
            order = self.order_factory.market(
                instrument_id=self.instrument.id,
                order_side=OrderSide.BUY,
                quantity=qty,
            )
            self.submit_order(order)
            self.position_opened = True
            self.log.info(
                f"突破上轨做多: price={current_price:.2f}, upper={upper_band:.2f}"
            )

    def _open_short(self, bar: Bar, current_price: float, lower_band: float | None):
        """开空仓"""
        qty = self.calculate_order_qty(bar.close)
        if qty and qty > 0:
            order = self.order_factory.market(
                instrument_id=self.instrument.id,
                order_side=OrderSide.SELL,
                quantity=qty,
            )
            self.submit_order(order)
            self.position_opened = True
            self.log.info(
                f"突破下轨做空: price={current_price:.2f}, lower={lower_band:.2f}"
            )

    def _check_exit(
        self,
        current_price: float,
        upper_band: float | None,
        lower_band: float | None,
    ):
        """检查出场信号"""
        # 检查多头止损
        if self.portfolio.is_net_long(self.instrument.id):
            if self.signals.check_long_exit(current_price, lower_band):
                self.close_all_positions(self.instrument.id)
                self.position_opened = False
                self.log.info(f"多头止损: price={current_price:.2f}")

        # 检查空头止损
        elif self.portfolio.is_net_short(self.instrument.id):
            if self.signals.check_short_exit(current_price, upper_band):
                self.close_all_positions(self.instrument.id)
                self.position_opened = False
                self.log.info(f"空头止损: price={current_price:.2f}")
