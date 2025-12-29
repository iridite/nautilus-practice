from decimal import Decimal
from operator import indexOf

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.trading.strategy import Strategy
# from nautilus_trader.indicators.averages import  # 均线
from nautilus_trader.indicators.volatility import AverageTrueRange
from nautilus_trader.indicators.volatility import BollingerBands
from nautilus_trader.indicators.momentum import RelativeStrengthIndex

class BmrStrategyConfig(StrategyConfig, frozen=True):
    instrument_id: str
    bar_type: str
    # 15m 或者 1h bar

    qty: Decimal = Decimal("0.01")  # 每次交易数量
    # TODO 下单数量不按张数来计算，而是使用资金百分比或USDT等方式计算
    rsi_period: int = 14
    bb_period: int = 20
    bb_dev: float = 2.0
    atr_period: int = 14

class BmrStrategy(Strategy):
    def __init__(self, config: BmrStrategyConfig):
        super().__init__(config)
        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        
        # 1. 定义指标
        self.rsi = RelativeStrengthIndex(config.rsi_period)
        self.bb = BollingerBands(config.bb_period, config.bb_dev)
        self.atr = AverageTrueRange(config.atr_period)

        if "15m" in config.bar_type or "1h" in config.bar_type:
            self.log.info("BmrStrategy initialized with ACCEPTED bar type: " + config.bar_type)
        else:
            self.log.warning("BmrStrategy initialized with UNACCEPTED bar type: " + config.bar_type + ". Recommended to use 15m or 1h bars.")
        
    def on_start(self):
        # 2. 注册指标与数据流
        self.register_indicator_for_bars(self.config.bar_type, self.rsi)
        self.register_indicator_for_bars(self.config.bar_type, self.bb)
        
        # 订阅行情数据
        self.subscribe_bars(self.config.bar_type)

    def on_bar(self, bar: Bar):
        # 确保指标已经计算出足够的数据
        if not self.rsi.initialized or not self.bb.initialized:
            return

        # 3. 获取当前值
        rsi_val = self.rsi.value
        bb_upper = self.bb.upper
        bb_lower = self.bb.lower
        bb_mid = self.bb.middle
        price = bar.close

        # 4. 获取当前仓位 (状态管理!)
        current_pos = self.cache.position(self.instrument_id)
        pos_qty = current_pos.quantity if current_pos else 0

        # --- 交易逻辑 ---

        # 场景 A: 没有仓位，寻找开仓机会
        if pos_qty == 0:
            # 开多条件：跌破下轨 + RSI超卖
            if price < bb_lower and rsi_val < 30:
                self.log.info(f"Signal LONG: Price={price} < Lower={bb_lower}, RSI={rsi_val}")
                self.submit_order(self.order_factory.market(
                    instrument_id=self.instrument_id,
                    order_side=OrderSide.BUY,
                    quantity=self.config.qty
                ))

            # 开空条件：突破上轨 + RSI超买
            elif price > bb_upper and rsi_val > 70:
                self.log.info(f"Signal SHORT: Price={price} > Upper={bb_upper}, RSI={rsi_val}")
                self.submit_order(self.order_factory.market(
                    instrument_id=self.instrument_id,
                    order_side=OrderSide.SELL,
                    quantity=self.config.qty
                ))

        # 场景 B: 持有做多仓位，寻找平仓机会
        elif pos_qty > 0:
            # 回归中轨平仓
            if price >= bb_mid:
                self.log.info("Exit LONG: Hit Middle Band")
                self.close_position(self.instrument_id)

        # 场景 C: 持有做空仓位，寻找平仓机会
        elif pos_qty < 0:
            # 回归中轨平仓
            if price <= bb_mid:
                self.log.info("Exit SHORT: Hit Middle Band")
                self.close_position(self.instrument_id)

    def on_stop(self):
        # 策略停止时，清理仓位 (可选)
        self.close_all_positions(self.instrument_id)