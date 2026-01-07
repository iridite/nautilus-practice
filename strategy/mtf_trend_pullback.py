from decimal import Decimal
from typing import Optional

# --- 1. 用户指定的 Nightly 版本 Imports ---
from nautilus_trader.config import StrategyConfig
from nautilus_trader.indicators.averages import ExponentialMovingAverage as ema
from nautilus_trader.indicators.momentum import RelativeStrengthIndex as rsi
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity

# --- 补充必要的类型引用 (保持严谨性) ---
from nautilus_trader.model.position import Position
from nautilus_trader.trading.strategy import Strategy


class MtfTrendPullbackConfig(StrategyConfig):
    instrument_id: str

    # --- 时间框架配置 (输入字符串) ---
    trend_bar_type: str  # e.g. "ETHUSDT.BINANCE-1-HOUR-LAST-EXTERNAL"
    trade_bar_type: str  # e.g. "ETHUSDT.BINANCE-5-MINUTE-LAST-EXTERNAL"

    # --- 参数配置 ---
    ema_period: int = 50
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70

    # --- 资金管理 ---
    qty_percent: Decimal = Decimal("0.1")
    stop_loss_pct: Decimal = Decimal("0.02")


class MtfTrendPullbackStrategy(Strategy):
    def __init__(self, config: MtfTrendPullbackConfig):
        super().__init__(config)

        # 2. 【严谨】预处理 ID 和 BarType 对象，避免在热路径重复解析
        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        self.trend_bar_type = BarType.from_str(config.trend_bar_type)
        self.trade_bar_type = BarType.from_str(config.trade_bar_type)

        # 3. 【适配 Nightly】使用别名 ema 和 rsi 进行实例化
        self.ema_trend = ema(config.ema_period)
        self.rsi_entry = rsi(config.rsi_period)

        # 状态缓存
        self.current_trend: int = 0  # 1: Bull, -1: Bear, 0: Neutral

    def on_start(self):
        """
        初始化：注册指标与订阅数据
        """
        # 4. 注册指标 (传入 BarType 对象)
        self.register_indicator_for_bars(self.trend_bar_type, self.ema_trend)
        self.register_indicator_for_bars(self.trade_bar_type, self.rsi_entry)

        # 订阅数据
        self.subscribe_bars(self.trend_bar_type)
        self.subscribe_bars(self.trade_bar_type)

        self.log.info(f"Strategy Started on {self.instrument_id}")
        self.log.info(
            f"Trend Layer: {self.trend_bar_type}, Trade Layer: {self.trade_bar_type}"
        )

    def on_bar(self, bar: Bar):
        """
        核心逻辑：根据 Bar 的类型对象进行匹配
        """
        # 5. 【严谨】比较 BarType 对象 (Identity check usually faster/safer than string)
        if bar.bar_type == self.trend_bar_type:
            self._update_trend_state(bar)

        elif bar.bar_type == self.trade_bar_type:
            self._check_entry_signal(bar)

    def _update_trend_state(self, bar: Bar):
        """
        [1H] 更新趋势状态
        """
        if not self.ema_trend.initialized:
            return

        ema_val = self.ema_trend.value

        if bar.close > ema_val:
            self.current_trend = 1
        elif bar.close < ema_val:
            self.current_trend = -1

    def _check_entry_signal(self, bar: Bar):
        """
        [5m] 检查交易信号
        """
        if not self.rsi_entry.initialized:
            return

        # 6. 获取仓位 (兼容 Netting 模式)
        positions = self.cache.positions(instrument_id=self.instrument_id)
        current_pos = positions[0] if positions else None

        # 如果有仓位，先检查退出逻辑
        if current_pos and current_pos.quantity != 0:
            self._check_exit(bar, current_pos)
            return

        rsi_val = self.rsi_entry.value
        signal = 0

        # 逻辑：顺势回调
        if self.current_trend == 1 and rsi_val < self.config.rsi_oversold:
            signal = 1  # Long
        elif self.current_trend == -1 and rsi_val > self.config.rsi_overbought:
            signal = -1  # Short

        if signal != 0:
            # AI 过滤接口
            if self._ask_ai_filter(bar, signal):
                self._execute_trade(signal, bar.close)

    def _ask_ai_filter(self, bar: Bar, signal: int) -> bool:
        """
        AI 过滤预留接口
        """
        return True

    def _check_exit(self, bar: Bar, position: Position):
        """
        风控检查
        """
        entry_price = position.avg_px_open
        pnl_pct = Decimal("0")

        if position.quantity > 0:
            pnl_pct = (bar.close - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - bar.close) / entry_price

        # 7. 硬止损触发
        if pnl_pct < -self.config.stop_loss_pct:
            self.log.warning(f"🛑 Stop Loss Triggered: {pnl_pct:.2%}")
            self.close_position(position)

    def _execute_trade(self, direction: int, price: Price):
        """
        执行交易
        """
        qty = self.calc_order_qty(price)
        if qty <= 0:
            return

        side = OrderSide.BUY if direction == 1 else OrderSide.SELL

        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=side,
            quantity=qty,
            time_in_force=TimeInForce.IOC,  # 市价单建议用 IOC
        )
        self.submit_order(order)
        self.log.info(
            f"🚀 SUBMIT {'BUY' if direction == 1 else 'SELL'} {qty} @ {price}"
        )

    def calc_order_qty(self, price: Price) -> Quantity:
        """
        计算下单数量 (基于权益百分比)
        """
        # 8. 【严谨】通过 Cache 获取账户，兼容 Portfolio 无 account_id 属性的情况
        accounts = self.cache.accounts()
        if not accounts:
            self.log.error("No accounts found in cache")
            return Quantity.from_int(0)

        account = accounts[0]
        instrument = self.cache.instrument(self.instrument_id)

        if not instrument:
            self.log.error(f"Instrument {self.instrument_id} not found in cache")
            return Quantity.from_int(0)

        # 获取计价货币余额
        balance = account.balance(instrument.quote_currency)
        if not balance:
            # 尝试获取 Base Currency 余额 (如果是反向合约)? 这里默认假设是 USDT 本位
            return Quantity.from_int(0)

        equity = balance.total
        target_notional = equity * self.config.qty_percent

        if price == 0:
            return Quantity.from_int(0)

        raw_qty = target_notional / price

        # 9. 精度修正
        try:
            return instrument.make_qty(raw_qty)
        except AttributeError:
            # Nightly 版本中 make_qty 应该是存在的，如果报错说明 instrument 对象未正确加载
            self.log.error("Instrument does not support 'make_qty'")
            return Quantity.from_int(0)
