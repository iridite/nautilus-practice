from decimal import Decimal
from nautilus_trader.common.enums import LogColor
from enum import Enum
# from operator import indexOf
from nautilus_trader.config import StrategyConfig
from nautilus_trader.indicators.momentum import RelativeStrengthIndex
from nautilus_trader.indicators.volatility import AverageTrueRange, BollingerBands
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.trading.strategy import Strategy

class SizeType(str, Enum):
    FIXED_QTY = "FIXED_QTY"       # 固定数量 (比如 0.1 BTC)
    FIXED_NOTIONAL = "FIXED_NOTIONAL" # 固定金额 (比如 1000 U)
    PCT_EQUITY = "PCT_EQUITY"     # 权益百分比 (比如 50% 仓位)


class BmrStrategyConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    # 15m 或者 1h bar
    size_type: SizeType = SizeType.FIXED_QTY
    size_value: Decimal = Decimal("0.01")  # 每次交易数量或金额
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


    def calculate_order_qty(self, price: Decimal, direction: OrderSide) -> Decimal:
        """
        根据配置模式计算下单数量
        """
        # 1. 查找 Instrument
        instrument = self.cache.instrument(self.instrument_id)
        if not instrument:
            self.log.error(f"Cannot find instrument: {self.instrument_id}")
            return Decimal("0")

        # 2. 修复：正确获取 Account 对象
        # 不再通过 self.portfolio.account_id 获取，而是直接查 Cache
        accounts = self.cache.accounts()
        if not accounts:
            self.log.error("No accounts found in cache.")
            return Decimal("0")
        
        # 取第一个账户 (通常就是我们要用的那个)
        account = accounts[0]

        # 3. 获取权益 (Equity)
        # 注意：这里我们使用 quote_currency (例如 USDT) 的余额
        # 在回测中，确保你的 start_balance 是以 USDT 注入的
        balance = account.balance(instrument.quote_currency)
        if not balance:
             self.log.error(f"No balance found for {instrument.quote_currency}")
             return Decimal("0")
             
        # 使用 total (包含未结盈亏) 还是 free (可用余额) 取决于你的风控偏好
        # 这里使用 total (总权益) 来计算仓位占比是比较标准的做法
        equity = balance.total

        target_qty = Decimal("0")

        # --- 分支逻辑 (保持不变) ---
        if self.config.size_type == SizeType.FIXED_QTY:
            target_qty = self.config.size_value

        elif self.config.size_type == SizeType.FIXED_NOTIONAL:
            if price > 0:
                target_qty = self.config.size_value / price

        elif self.config.size_type == SizeType.PCT_EQUITY:
            # 模式: 权益百分比
            target_notional = equity * self.config.size_value
            if price > 0:
                target_qty = target_notional / price

        # --- 精度修正 (保持不变) ---
        try:
            valid_qty = instrument.make_qty(target_qty)
        except AttributeError:
            # 备用方案：如果 make_qty 也不存在，可能是旧版本，尝试 round_quantity
            # 或者手动处理 (不推荐，但为了防止报错)
            self.log.warning("Method 'make_qty' not found, using raw quantity.")
            valid_qty = target_qty
        
        if valid_qty < instrument.min_quantity:
            # 只有数量大于 0 时才报 warning，避免日志刷屏
            if valid_qty > 0:
                self.log.warning(f"Qty {valid_qty} < min {instrument.min_quantity}")
            return Decimal("0")
            
        return valid_qty

    def buy(self, qty: Decimal):
        """
        封装的买入逻辑
        """
        qty = self.calculate_order_qty(price=qty, direction=OrderSide.BUY)

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
        qty = self.calculate_order_qty(price=qty, direction=OrderSide.SELL)

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
                self.buy(self.config.size_value)

            # 开空条件：突破上轨 + RSI超买
            elif price > bb_upper and rsi_val > 70:
                self.log.info(
                    f"Signal SHORT: Price={price} > Upper={bb_upper}, RSI={rsi_val}"
                )
                self.sell(self.config.size_value)

        # 场景 B: 持有做多仓位，寻找平仓机会
        elif pos_qty > 0:
            # 回归中轨平仓
            if price >= bb_mid:
                self.log.info("Exit LONG: Hit Middle Band")
                self.close_position(current_pos)

        # 场景 C: 持有做空仓位，寻找平仓机会
        elif pos_qty < 0:
            # 回归中轨平仓
            if price <= bb_mid:
                self.log.info("Exit SHORT: Hit Middle Band")
                self.close_position(current_pos)

    def on_stop(self):
        # 策略停止时，清理仓位 (可选)
        self.close_all_positions(self.instrument_id)
