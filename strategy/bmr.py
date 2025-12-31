from decimal import Decimal

from nautilus_trader.common.enums import LogColor

# from operator import indexOf
from nautilus_trader.config import StrategyConfig
from nautilus_trader.indicators.momentum import RelativeStrengthIndex
from nautilus_trader.indicators.volatility import AverageTrueRange, BollingerBands
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.trading.strategy import Strategy


class BmrStrategyConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    # 15m 或者 1h bar

    qty: Decimal = Decimal("0.01")  # 每次交易数量
    qty_percentage: Decimal = Decimal("0.05")  # 每次交易数量百分比
    # TODO 下单数量不按张数来计算，而是使用资金百分比或USDT等方式计算
    rsi_period: int = 14
    bb_period: int = 20
    bb_dev: float = 2.0
    atr_period: int = 14


class BmrStrategy(Strategy):
    def __init__(self, config: BmrStrategyConfig):
        super().__init__(config)
        self.instrument_id: str = config.instrument_id

        # 1. 定义指标
        self.rsi = RelativeStrengthIndex(config.rsi_period)
        self.bb = BollingerBands(config.bb_period, config.bb_dev)
        self.atr = AverageTrueRange(config.atr_period)

        # if "15m" in config.bar_type or "1h" in config.bar_type:
        #     self.log.info(
        #         "BmrStrategy initialized with ACCEPTED bar type: " + config.bar_type
        #     )
        # else:
        #     self.log.warning(
        #         "BmrStrategy initialized with UNACCEPTED bar type: "
        #         + config.bar_type
        #         + ". Recommended to use 15m or 1h bars."
        #     )

    def calc_quantity(self, price: Decimal) -> Decimal:
        """
        计算下单数量
        支持：固定数量模式 OR 余额百分比模式
        """
        # 模式 A: 如果配置了固定数量，直接返回
        if self.config.qty > 0:
            return self.config.qty

        # 模式 B: 根据余额百分比计算
        # 1. 获取合约信息以确定计价货币 (Quote Currency, 如 USDT)
        instrument = self.cache.instrument(self.instrument_id)
        if not instrument:
            self.log.error(f"Cannot find instrument: {self.instrument_id}")
            return Decimal("0")

        # 2. 获取账户余额 (需要知道 Quote Currency，例如 USDT)
        # 注意：这里假设你只有一个账户。如果是实盘，通常会自动匹配。
        account_id = self.portfolio.account_id  # 或者使用 self.cache.accounts()[0].id
        account = self.cache.account(account_id)

        if not account:
            self.log.error("No account found, cannot calc quantity by percentage")
            return Decimal("0")

        # 获取可用余额 (Free Balance)
        balance = account.balance(instrument.quote_currency).free

        # 3. 计算名义价值 (Notional Value) = 余额 * 百分比
        notional_value = balance * self.config.qty_percentage

        if price == 0:
            return Decimal("0")

        # 4. 计算原始数量 = 名义价值 / 当前价格
        raw_qty = notional_value / price

        # 5. 【关键】修正数量精度 (Make Quantity Valid)
        # 这一步非常重要！比如算出来是 0.12345678，但交易所只接受 0.12，
        # instrument.make_qty_valid 会自动帮你处理最小下单量和步长。
        return instrument.make_qty_valid(raw_qty)

    def buy(self, qty: Decimal):
        """
        封装的买入逻辑
        """
        qty = self.calc_quantity(qty)

        # 数量为 0 或太小，不执行
        if qty <= 0:
            self.log.warning(f"Calculated BUY quantity is {qty}, skipping.")
            return

        # 创建订单
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=qty,
        )

        self.log.info(f"🚀 SUBMIT BUY: {qty} @ ~{qty}")
        self.submit_order(order)

    def sell(self, qty: Decimal):
        """
        封装的卖出逻辑
        """
        qty = self.calc_quantity(qty)

        if qty <= 0:
            self.log.warning(f"Calculated SELL quantity is {qty}, skipping.")
            return

        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.SELL,
            quantity=qty,
        )

        self.log.info(f"🚀 SUBMIT SELL: {qty} @ ~{qty}")
        self.submit_order(order)

    def on_start(self):
        # 2. 注册指标与数据流
        self.register_indicator_for_bars(self.config.bar_type, self.rsi)
        self.register_indicator_for_bars(self.config.bar_type, self.bb)
        self.register_indicator_for_bars(self.config.bar_type, self.atr)

        # 订阅行情数据
        self.subscribe_bars(self.config.bar_type)

    def on_bar(self, bar: Bar):
        # Check if indicators ready
        if not self.indicators_initialized():
            self.log.warning(  # 内置继承得来的 log 类内对象
                f"Waiting for indicators to warm up [{self.cache.bar_count(self.config.bar_type)}]",
                color=LogColor.YELLOW,
            )
            return  # Wait for indicators to warm up...
        # 确保指标已经计算出足够的数据
        if not self.rsi.initialized or not self.bb.initialized:
            self.log.warning(
                f"Waiting for indicators to warm up [{self.cache.bar_count(self.config.bar_type)}]",
                color=LogColor.YELLOW,
            )
            return

        # 3. 获取当前值
        rsi_val = self.rsi.value
        bb_upper = self.bb.upper
        bb_lower = self.bb.lower
        bb_mid = self.bb.middle
        price = bar.close

        # 4. 获取当前仓位 (状态管理!)
        # 1. 使用 positions (复数) 获取该币种的所有仓位列表
        positions_list = self.cache.positions(instrument_id=self.instrument_id)

        # 2. 取出第一个仓位（如果是 Netting 模式，列表里最多只有一个）
        # 对 对冲 模式做一下适配
        current_pos = positions_list[0] if positions_list else None

        # 3. 安全获取数量 (如果没有仓位，数量为 0)
        pos_qty = current_pos.quantity if current_pos else 0

        # --- 交易逻辑 ---

        # 场景 A: 没有仓位，寻找开仓机会
        if pos_qty == 0:
            # 开多条件：跌破下轨 + RSI超卖
            if price < bb_lower and rsi_val < 30:
                self.log.info(
                    f"Signal LONG: Price={price} < Lower={bb_lower}, RSI={rsi_val}"
                )
                self.submit_order(
                    self.order_factory.market(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.BUY,
                        quantity=self.config.qty,
                    )
                )

            # 开空条件：突破上轨 + RSI超买
            elif price > bb_upper and rsi_val > 70:
                self.log.info(
                    f"Signal SHORT: Price={price} > Upper={bb_upper}, RSI={rsi_val}"
                )
                self.submit_order(
                    self.order_factory.market(
                        instrument_id=self.instrument_id,
                        order_side=OrderSide.SELL,
                        quantity=self.config.qty,
                    )
                )

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
