from decimal import Decimal
from typing import Optional

from nautilus_trader.config import StrategyConfig

# 指标导入
from nautilus_trader.indicators.averages import ExponentialMovingAverage as ema
from nautilus_trader.indicators.momentum import RelativeStrengthIndex as rsi
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.trading.strategy import Strategy


class MtfTrendPullbackConfig(StrategyConfig):
    instrument_id: str

    # --- 时间框架配置 ---
    # 司令部：趋势周期 (例如 1-HOUR)
    trend_bar_type: str
    # 特种兵：交易周期 (例如 5-MINUTE)
    trade_bar_type: str

    # --- 参数配置 ---
    ema_period: int = 50  # 趋势判断均线
    rsi_period: int = 14  # 入场判断指标
    rsi_oversold: int = 30  # 超卖阈值 (做多)
    rsi_overbought: int = 70  # 超买阈值 (做空)

    # --- 资金管理 ---
    qty_percent: Decimal = Decimal("0.1")  # 每次使用 10% 的资金
    stop_loss_pct: Decimal = Decimal("0.02")  # 2% 硬止损


class MtfTrendPullbackStrategy(Strategy):
    def __init__(self, config: MtfTrendPullbackConfig):
        super().__init__(config)
        self.instrument_id = InstrumentId.from_str(config.instrument_id)

        # 1. 定义指标 (注意：这里要区分是给哪个周期用的)
        self.ema_trend = EMA(config.ema_period)  # 给 1H 用的
        self.rsi_entry = RSI(config.rsi_period)  # 给 5m 用的

        # 状态缓存
        self.current_trend: int = 0  # 1: Bull, -1: Bear, 0: Neutral

    def on_start(self):
        """
        初始化：订阅两套数据流
        """
        # 将指标绑定到特定的 BarType，这样 Nautilus 会自动帮我们更新计算
        self.register_indicator_for_bars(self.config.trend_bar_type, self.ema_trend)
        self.register_indicator_for_bars(self.config.trade_bar_type, self.rsi_entry)

        # 订阅数据
        self.subscribe_bars(self.config.trend_bar_type)
        self.subscribe_bars(self.config.trade_bar_type)

        self.log.info(
            f"Strategy Started. Trend: {self.config.trend_bar_type}, Trade: {self.config.trade_bar_type}"
        )

    def on_bar(self, bar: Bar):
        """
        核心逻辑：根据 Bar 的类型分流处理
        """

        # --- 分流逻辑 A: 司令部 (1H) 更新大趋势 ---
        if bar.bar_type == self.config.trend_bar_type:
            self._update_trend_state(bar)
            return

        # --- 分流逻辑 B: 特种兵 (5m) 寻找入场点 ---
        elif bar.bar_type == self.config.trade_bar_type:
            self._check_entry_signal(bar)

    def _update_trend_state(self, bar: Bar):
        """
        根据大周期 K 线更新趋势状态
        """
        if not self.ema_trend.initialized:
            return

        ema_value = self.ema_trend.value

        if bar.close > ema_value:
            self.current_trend = 1  # 牛市
        elif bar.close < ema_value:
            self.current_trend = -1  # 熊市

        # 可选：打印趋势变化日志
        # self.log.info(f"Trend Update: {self.current_trend} (Price: {bar.close}, EMA: {ema_value:.2f})")

    def _check_entry_signal(self, bar: Bar):
        """
        根据小周期 K 线判断是否开仓
        """
        # 1. 基础检查：指标是否准备好，是否已有仓位
        if not self.rsi_entry.initialized:
            return

        current_pos = self.cache.position(self.instrument_id)
        if current_pos and current_pos.quantity != 0:
            self._check_exit(bar, current_pos)  # 如果有仓位，去检查止损/止盈
            return

        # 2. 获取数据
        rsi = self.rsi_entry.value

        # 3. 核心策略逻辑
        signal = 0

        # 场景 A: 大趋势看涨 + 小周期超卖 (回调)
        if self.current_trend == 1 and rsi < self.config.rsi_oversold:
            signal = 1

        # 场景 B: 大趋势看跌 + 小周期超买 (反弹)
        elif self.current_trend == -1 and rsi > self.config.rsi_overbought:
            signal = -1

        # 4. 【AI 接口预留】
        # 如果逻辑触发了，这里不急着下单，而是问 AI
        if signal != 0:
            if self._ask_ai_filter(bar, signal):
                self._execute_trade(signal, bar.close)

    def _ask_ai_filter(self, bar: Bar, signal: int) -> bool:
        """
        将来在这里接入 LightGBM / XGBoost
        现在先默认返回 True
        """
        # TODO:
        # 1. feature_vector = [self.rsi_entry.value, self.current_trend, volatility...]
        # 2. prob = self.model.predict(feature_vector)
        # 3. return prob > 0.6
        return True

    def _check_exit(self, bar: Bar, position):
        """
        简单的止损检查 (止盈可以根据你的喜好加)
        """
        entry_price = position.avg_px_open
        pnl_pct = 0

        if position.quantity > 0:  # 多单
            pnl_pct = (bar.close - entry_price) / entry_price
        else:  # 空单
            pnl_pct = (entry_price - bar.close) / entry_price

        # 触发硬止损
        if pnl_pct < -self.config.stop_loss_pct:
            self.log.warning(f"🛑 Stop Loss Triggered! PnL: {pnl_pct:.2%}")
            self.close_position(position)

    def _execute_trade(self, direction: int, price: Price):
        """
        执行下单，包含资金管理计算
        """
        side = OrderSide.BUY if direction == 1 else OrderSide.SELL

        # 计算数量 (使用我们之前完善的逻辑)
        qty = self.calc_order_qty(price)

        if qty > 0:
            order = self.order_factory.market(
                instrument_id=self.instrument_id, order_side=side, quantity=qty
            )
            self.submit_order(order)
            self.log.info(
                f"🚀 {'BUY' if direction == 1 else 'SELL'} Executed @ {price}"
            )

    def calc_order_qty(self, price: Price) -> Quantity:
        """
        基于账户权益百分比计算下单量
        """
        account = self.cache.account(self.portfolio.account_id)
        if not account:
            return Quantity.from_int(0)

        # 获取总权益
        equity = account.balance(
            self.cache.instrument(self.instrument_id).quote_currency
        ).total

        # 计算目标名义价值
        target_notional = equity * self.config.qty_percent

        if price == 0:
            return Quantity.from_int(0)

        # 转换为数量并修正精度
        raw_qty = target_notional / price
        return self.cache.instrument(self.instrument_id).make_qty(raw_qty)
