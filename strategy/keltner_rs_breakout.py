"""
Strategy: Keltner RS Breakout (KRB)
Type: Medium-Frequency Trend Following
Core Logic:
  1. Entry: Close > EMA(20) + 2.25*ATR(20)
  2. Filter A (Macro): Close > SMA(200)
  3. Filter B (Alpha): Relative Strength (Symbol vs BTC) > 0
  4. Filter C (Momentum): Volume > 1.5 * SMA(Vol, 20)
  5. Sizing: Volatility Targeting (Base Risk 1.0%, Squeeze Risk 1.5%)
Note: This strategy implements the "Breathing Trend" philosophy using Static Keltner Channels and RS filtering.
"""

from collections import OrderedDict, deque
from decimal import Decimal

import numpy as np
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId

from strategy.core.base import BaseStrategy, BaseStrategyConfig
from utils.custom_data import FundingRateData


class KeltnerRSBreakoutConfig(BaseStrategyConfig):
    """Keltner RS Breakout 策略配置"""

    # 简化配置字段（推荐使用）
    symbol: str = ""
    timeframe: str = ""
    price_type: str = "LAST"
    origination: str = "EXTERNAL"
    btc_symbol: str = "BTCUSDT"

    # 完整配置字段（向后兼容，自动从简化字段生成）
    instrument_id: str = ""
    bar_type: str = ""
    btc_instrument_id: str = ""

    # 指标参数
    ema_period: int = 20
    atr_period: int = 20
    sma_period: int = 200
    bb_period: int = 20
    bb_std: float = 2.0
    volume_period: int = 20

    # 通道参数
    keltner_base_multiplier: float = 1.5
    keltner_trigger_multiplier: float = 2.25

    # 风控参数
    base_risk_pct: float = 0.01
    high_conviction_risk_pct: float = 0.015
    stop_loss_atr_multiplier: float = 3.0

    # 过滤器参数
    volume_multiplier: float = 1.5
    rs_lookback_days: int = 5
    squeeze_memory_days: int = 3

    # 其他参数
    min_stop_distance_pct: float = 0.005  # 最小止损距离百分比（0.5%）
    max_history_size: int = 100  # 历史数据最大保存数量


class KeltnerRSBreakoutStrategy(BaseStrategy):
    """
    Keltner RS Breakout 策略

    核心逻辑：
    1. Squeeze 状态判定：布林带收窄进 1.5x ATR 肯特纳通道
    2. 过滤器：趋势(>SMA200) + 放量(>1.5x均量) + RS(>BTC)
    3. 触发：突破 2.25x ATR 上轨
    4. 仓位：波动率倒数模型，Squeeze 加成
    5. 出场：Chandelier Exit (最高价 - 3x ATR)
    """

    def __init__(self, config: KeltnerRSBreakoutConfig):
        super().__init__(config)

        # BTC 标的 ID
        self.btc_instrument_id = InstrumentId.from_str(config.btc_instrument_id)

        # 指标数据存储
        self.closes = deque(maxlen=max(config.ema_period, config.bb_period, config.sma_period) + 1)
        self.volumes = deque(maxlen=config.volume_period + 1)
        self.trs = deque(maxlen=config.atr_period)

        # 指标值
        self.ema = None
        self.atr = None
        self.sma = None
        self.bb_upper = None
        self.bb_lower = None
        self.volume_sma = None

        # 价格历史（用于 RS 计算）- 使用 OrderedDict 保持插入顺序，优化清理效率
        self.price_history = OrderedDict()  # {timestamp: price}
        self.btc_price_history = OrderedDict()  # {timestamp: price}

        # Squeeze 状态历史
        self.squeeze_history = deque(maxlen=config.squeeze_memory_days)

        # 持仓跟踪
        self.entry_price = None
        self.highest_high = None

        # 订单状态跟踪
        self._pending_entry_order = False

    def on_start(self) -> None:
        """策略启动时初始化"""
        super().on_start()

        self.log.info(
            f"Keltner RS Breakout 启动: "
            f"EMA={self.config.ema_period}, ATR={self.config.atr_period}, "
            f"SMA={self.config.sma_period}, BTC={self.config.btc_instrument_id}"
        )

        # 订阅 Bar 数据
        bar_type = BarType.from_str(self.config.bar_type)
        self.subscribe_bars(bar_type)

        # 订阅 BTC Bar 数据（如果不是同一标的）
        if self.instrument.id != self.btc_instrument_id:
            btc_bar_type_str = self.config.bar_type.replace(
                self.instrument.id.symbol.value,
                self.btc_instrument_id.symbol.value
            )
            btc_bar_type = BarType.from_str(btc_bar_type_str)
            self.subscribe_bars(btc_bar_type)

    def on_stop(self) -> None:
        """策略停止时清理资源"""
        # 取消订阅 Bar 数据
        bar_type = BarType.from_str(self.config.bar_type)
        self.unsubscribe_bars(bar_type)

        # 取消订阅 BTC Bar 数据（如果不是同一标的）
        if self.instrument.id != self.btc_instrument_id:
            btc_bar_type_str = self.config.bar_type.replace(
                self.instrument.id.symbol.value,
                self.btc_instrument_id.symbol.value
            )
            btc_bar_type = BarType.from_str(btc_bar_type_str)
            self.unsubscribe_bars(btc_bar_type)

    def on_bar(self, bar: Bar) -> None:
        """处理 Bar 数据"""
        # 更新价格缓存并标记更新状态
        if bar.bar_type.instrument_id == self.instrument.id:
            # 主标的数据
            close = float(bar.close)
            high = float(bar.high)
            low = float(bar.low)
            volume = float(bar.volume)

            self.closes.append(close)
            self.volumes.append(volume)

            # 计算 TR
            if len(self.closes) > 1:
                tr = max(
                    high - low,
                    abs(high - self.closes[-2]),
                    abs(low - self.closes[-2])
                )
                self.trs.append(tr)

            # 更新指标
            self._update_indicators()

            # 存储价格历史（带时间戳）
            self.price_history[bar.ts_event] = close

            # 清理过期数据（OrderedDict 保证 FIFO 顺序，直接删除第一个元素）
            if len(self.price_history) > self.config.max_history_size:
                self.price_history.popitem(last=False)

        elif bar.bar_type.instrument_id == self.btc_instrument_id:
            # BTC数据
            self.btc_price_history[bar.ts_event] = float(bar.close)

            # 清理过期数据（OrderedDict 保证 FIFO 顺序，直接删除第一个元素）
            if len(self.btc_price_history) > self.config.max_history_size:
                self.btc_price_history.popitem(last=False)

            # BTC数据只更新，不触发交易逻辑
            return
        else:
            return

        # 1. Warmup 检查
        if self.sma is None:
            return

        # 计算并记录 Squeeze 状态（独立于交易过滤器）
        #
        # 重要修复说明（2026-02-01）：
        # 此修复将 Squeeze 计算从过滤器检查后移至 Warmup 检查后立即执行。
        #
        # 修复前：Squeeze 只在通过所有过滤器后才计算，导致历史数据不完整
        # 修复后：每个交易日都记录 Squeeze 状态，确保 any(self.squeeze_history) 判断准确
        #
        # 影响：此修复提高了高确信度交易的识别准确性，可能导致：
        # - 更多交易被识别为高确信度（使用 1.5% 风险 vs 1.0%）
        # - 仓位增加约 50%，回测收益可能提升约 5%
        # - 这是符合策略设计意图的正向修复，不是过拟合
        is_squeezing = self._check_squeeze()
        self.squeeze_history.append(is_squeezing)

        close = float(bar.close)

        # 2. 持仓检查 - 持仓时只执行出场逻辑（不受 Funding Rate 影响）
        if self.portfolio.is_net_long(self.instrument.id):
            if self.highest_high is None:
                self.highest_high = float(bar.high)
            else:
                self.highest_high = max(self.highest_high, float(bar.high))
            self._handle_exit(bar)
            return

        # 无持仓时执行入场逻辑检查
        if self._pending_entry_order:
            return

        # 3. Funding Rate Guard：资金费率过高时拒绝开仓
        funding_rate = self._get_funding_rate()
        if funding_rate is not None and funding_rate > 0.0005:
            return

        # 4. Regime 检查：价格必须在 SMA200 上方（上升趋势）
        if close < self.sma:
            return

        # 5. RS 检查
        if not self._check_relative_strength():
            return

        # 6. Volume 检查
        volume = float(bar.volume)
        if self.volume_sma is None or volume < self.volume_sma * self.config.volume_multiplier:
            return

        # 7. Trigger 检查
        if self.ema is None or self.atr is None:
            return

        keltner_trigger_upper = self.ema + (self.config.keltner_trigger_multiplier * self.atr)
        if close <= keltner_trigger_upper:
            return

        # 8. 执行入场
        self._handle_entry(bar, is_squeezing, keltner_trigger_upper)

    def _update_indicators(self) -> None:
        """更新所有指标"""
        # EMA
        if len(self.closes) >= self.config.ema_period:
            if self.ema is None:
                # 初始化：使用 SMA
                self.ema = sum(list(self.closes)[-self.config.ema_period:]) / self.config.ema_period
            else:
                # 递归计算
                alpha = 2.0 / (self.config.ema_period + 1)
                self.ema = alpha * self.closes[-1] + (1 - alpha) * self.ema

        # ATR (Wilder's Smoothing / RMA)
        if len(self.trs) >= self.config.atr_period:
            if self.atr is None:
                # 初始化：使用简单平均
                self.atr = sum(list(self.trs)[-self.config.atr_period:]) / self.config.atr_period
            else:
                # Wilder's Smoothing: α = 1/period
                alpha = 1.0 / self.config.atr_period
                self.atr = alpha * self.trs[-1] + (1 - alpha) * self.atr

        # SMA
        if len(self.closes) >= self.config.sma_period:
            self.sma = sum(list(self.closes)[-self.config.sma_period:]) / self.config.sma_period

        # Bollinger Bands (优化：使用 NumPy 向量化计算)
        if len(self.closes) >= self.config.bb_period:
            bb_closes = np.array(list(self.closes)[-self.config.bb_period:])
            bb_mean = bb_closes.mean()
            bb_std = bb_closes.std()
            self.bb_upper = bb_mean + self.config.bb_std * bb_std
            self.bb_lower = bb_mean - self.config.bb_std * bb_std

        # Volume SMA
        if len(self.volumes) >= self.config.volume_period:
            self.volume_sma = sum(list(self.volumes)[-self.config.volume_period:]) / self.config.volume_period



    def _get_funding_rate(self) -> float | None:
        """获取当前 Funding Rate"""
        try:
            funding_data = self.cache.get_custom_data(FundingRateData, self.instrument.id)
            if funding_data:
                return float(funding_data.funding_rate)
        except Exception as e:
            self.log.debug(f"无法获取 Funding Rate 数据: {e}")
        return None

    def _check_squeeze(self) -> bool:
        """检查是否处于 Squeeze 状态"""
        if self.bb_upper is None or self.bb_lower is None or self.ema is None or self.atr is None:
            return False

        # 计算 Keltner Base 通道
        keltner_upper = self.ema + (self.config.keltner_base_multiplier * self.atr)
        keltner_lower = self.ema - (self.config.keltner_base_multiplier * self.atr)

        # Squeeze: 布林带完全在 Keltner 通道内
        return self.bb_upper < keltner_upper and self.bb_lower > keltner_lower

    def _check_relative_strength(self) -> bool:
        """检查相对强弱（RS）"""
        # 主动从缓存获取 BTC 最新数据
        btc_bar_type_str = self.config.bar_type.replace(
            self.instrument.id.symbol.value,
            self.btc_instrument_id.symbol.value
        )
        btc_bar_type = BarType.from_str(btc_bar_type_str)
        btc_bar = self.cache.bar(btc_bar_type)

        # None 检查
        if btc_bar is None:
            self.log.debug("无法获取 BTC 数据")
            return False

        # 更新 BTC 价格历史（确保最新数据）
        btc_close = float(btc_bar.close)
        if btc_bar.ts_event not in self.btc_price_history:
            self.btc_price_history[btc_bar.ts_event] = btc_close

        # 需要足够的历史数据
        if len(self.price_history) < self.config.rs_lookback_days + 1:
            return False
        if len(self.btc_price_history) < self.config.rs_lookback_days + 1:
            return False

        # 动态计算共同时间戳（替代维护列表）
        common_timestamps = sorted(set(self.price_history.keys()) & set(self.btc_price_history.keys()))
        if len(common_timestamps) < self.config.rs_lookback_days + 1:
            return False

        # 使用最近的对齐数据计算涨幅
        recent_ts = common_timestamps[-(self.config.rs_lookback_days + 1):]
        symbol_prices = [self.price_history[ts] for ts in recent_ts]
        btc_prices = [self.btc_price_history[ts] for ts in recent_ts]

        # 防止除零
        if symbol_prices[0] <= 0 or btc_prices[0] <= 0:
            self.log.warning(f"RS计算数据异常: symbol[0]={symbol_prices[0]}, btc[0]={btc_prices[0]}")
            return False

        symbol_perf = (symbol_prices[-1] / symbol_prices[0]) - 1
        btc_perf = (btc_prices[-1] / btc_prices[0]) - 1

        return symbol_perf > btc_perf

    def _handle_entry(self, bar: Bar, is_squeezing: bool, keltner_trigger_upper: float) -> None:
        """处理开仓逻辑（过滤器已在 on_bar 中检查）"""
        close = float(bar.close)

        # 判断是否为高确信度设置
        high_conviction = is_squeezing or any(self.squeeze_history)

        # 计算仓位
        qty = self._calculate_position_size(bar, high_conviction)
        if not qty or qty <= 0:
            return

        # 下单
        order = self.order_factory.market(
            instrument_id=self.instrument.id,
            order_side=OrderSide.BUY,
            quantity=qty,
        )
        self.submit_order(order)
        self._pending_entry_order = True

        # 记录持仓信息
        self.entry_price = close
        self.highest_high = float(bar.high)

        conviction_type = "高确信度" if high_conviction else "普通"
        self.log.info(
            f"开仓做多 ({conviction_type}): "
            f"price={close:.2f}, trigger={keltner_trigger_upper:.2f}, "
            f"qty={qty}, squeeze={is_squeezing}"
        )

    def _calculate_position_size(self, bar: Bar, high_conviction: bool) -> Decimal:
        """计算仓位大小"""
        if self.atr is None:
            return Decimal("0")

        # 获取账户权益
        account = self.portfolio.account(self.instrument.id.venue)
        if not account:
            return Decimal("0")
        equity = account.balance_total(self.instrument.quote_currency)
        if not equity or equity.as_decimal() <= 0:
            return Decimal("0")

        # 确定风险百分比
        risk_pct = (
            self.config.high_conviction_risk_pct if high_conviction
            else self.config.base_risk_pct
        )

        # 计算止损距离（统一使用Decimal）
        stop_distance = Decimal(str(self.config.stop_loss_atr_multiplier)) * Decimal(str(self.atr))

        # 防止ATR过小导致仓位过大
        min_stop_distance = bar.close.as_decimal() * Decimal(str(self.config.min_stop_distance_pct))
        if stop_distance < min_stop_distance:
            self.log.warning(f"ATR过小({self.atr:.6f})，使用最小止损距离{min_stop_distance}")
            stop_distance = min_stop_distance

        # 计算仓位：(权益 * 风险%) / 止损距离
        risk_amount = equity.as_decimal() * Decimal(str(risk_pct))
        qty = risk_amount / stop_distance

        # 使用基类的仓位计算方法进行标准化
        return self.instrument.make_qty(qty)

    def _handle_exit(self, bar: Bar) -> None:
        """处理出场逻辑"""
        close = float(bar.close)

        # 计算 Chandelier Exit 止损线（highest_high已在on_bar中更新）
        if self.atr is None:
            return

        trailing_stop = self.highest_high - (self.config.stop_loss_atr_multiplier * self.atr)

        # 检查是否触发止损
        if close < trailing_stop:
            self.close_all_positions(self.instrument.id)
            self.log.info(
                f"Chandelier Exit 平仓: "
                f"price={close:.2f}, stop={trailing_stop:.2f}, "
                f"highest={self.highest_high:.2f}"
            )

            # 重置持仓信息
            self.entry_price = None
            self.highest_high = None

    def on_order_filled(self, event) -> None:
        """订单成交回调"""
        super().on_order_filled(event)
        self._pending_entry_order = False

    def on_order_rejected(self, event) -> None:
        """订单拒绝回调"""
        super().on_order_rejected(event)
        self._pending_entry_order = False
        self.log.error(f"订单被拒绝: {event.reason}")
