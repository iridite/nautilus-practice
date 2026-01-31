"""
DK_Alpha_Trend 策略 (Dynamic Keltner Alpha Trend)

中低频趋势跟踪策略，结合动态肯特纳通道突破、相对强弱选币和 TTM Squeeze 波动率状态。
适用于加密货币市场的日线交易。
"""

from collections import deque
from decimal import Decimal

from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId

from strategy.core.base import BaseStrategy, BaseStrategyConfig


class DKAlphaTrendConfig(BaseStrategyConfig):
    """DK_Alpha_Trend 策略配置"""

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


class DKAlphaTrendStrategy(BaseStrategy):
    """
    DK_Alpha_Trend 策略

    核心逻辑：
    1. Squeeze 状态判定：布林带收窄进 1.5x ATR 肯特纳通道
    2. 过滤器：趋势(>SMA200) + 放量(>1.5x均量) + RS(>BTC)
    3. 触发：突破 2.25x ATR 上轨
    4. 仓位：波动率倒数模型，Squeeze 加成
    5. 出场：Chandelier Exit (最高价 - 3x ATR)
    """

    def __init__(self, config: DKAlphaTrendConfig):
        super().__init__(config)

        # BTC 标的 ID
        self.btc_instrument_id = InstrumentId.from_str(config.btc_instrument_id)

        # 指标数据存储
        self.closes = deque(maxlen=max(config.ema_period, config.bb_period, config.sma_period) + 1)
        self.highs = deque(maxlen=config.atr_period + 1)
        self.lows = deque(maxlen=config.atr_period + 1)
        self.volumes = deque(maxlen=config.volume_period + 1)
        self.trs = deque(maxlen=config.atr_period)

        # 指标值
        self.ema = None
        self.atr = None
        self.sma = None
        self.bb_upper = None
        self.bb_lower = None
        self.volume_sma = None

        # 价格历史（用于 RS 计算）- 使用字典存储时间戳对齐的数据
        self.price_history = {}  # {timestamp: price}
        self.btc_price_history = {}  # {timestamp: price}
        self.common_timestamps = []  # 有序的共同时间戳列表（性能优化）

        # Squeeze 状态历史
        self.squeeze_history = deque(maxlen=config.squeeze_memory_days)

        # 持仓跟踪
        self.entry_price = None
        self.highest_high = None

        # 时间戳跟踪和数据同步
        self.last_bar_ts = 0
        self.last_btc_bar_ts = 0
        self._bar_updated = False
        self._btc_bar_updated = False
        self.DATA_SYNC_TOLERANCE_NS = 60 * 1_000_000_000  # 60秒容差

        # 订单状态跟踪
        self._pending_entry_order = False

        # BTC数据超时跟踪
        self._bars_since_btc_update = 0
        self.MAX_BTC_DELAY_BARS = 5

        # 历史数据大小限制
        self.MAX_HISTORY_SIZE = 100

    def on_start(self) -> None:
        """策略启动时初始化"""
        super().on_start()

        self.log.info(
            f"DK_Alpha_Trend 启动: "
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
            self.highs.append(high)
            self.lows.append(low)
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
            self.last_bar_ts = bar.ts_event
            self._bar_updated = True

            # 更新共同时间戳列表（性能优化）
            if bar.ts_event in self.btc_price_history and bar.ts_event not in self.common_timestamps:
                self.common_timestamps.append(bar.ts_event)

            # 清理过期数据
            if len(self.price_history) > self.MAX_HISTORY_SIZE:
                oldest_ts = min(self.price_history.keys())
                del self.price_history[oldest_ts]
                # 同步清理共同时间戳列表
                if oldest_ts in self.common_timestamps:
                    self.common_timestamps.remove(oldest_ts)

        elif bar.bar_type.instrument_id == self.btc_instrument_id:
            # BTC数据
            self.btc_price_history[bar.ts_event] = float(bar.close)
            self.last_btc_bar_ts = bar.ts_event
            self._btc_bar_updated = True
            self._bars_since_btc_update = 0

            # 更新共同时间戳列表（性能优化）
            if bar.ts_event in self.price_history and bar.ts_event not in self.common_timestamps:
                self.common_timestamps.append(bar.ts_event)

            # 清理过期数据
            if len(self.btc_price_history) > self.MAX_HISTORY_SIZE:
                oldest_ts = min(self.btc_price_history.keys())
                del self.btc_price_history[oldest_ts]
                # 同步清理共同时间戳列表
                if oldest_ts in self.common_timestamps:
                    self.common_timestamps.remove(oldest_ts)
        else:
            return

        # 只有两个标的都更新且数据同步时才处理
        if not self._btc_bar_updated:
            self._bars_since_btc_update += 1
            if self._bars_since_btc_update > self.MAX_BTC_DELAY_BARS:
                self.log.error(
                    f"BTC数据超过{self.MAX_BTC_DELAY_BARS}根bar未更新，"
                    f"当前延迟: {self._bars_since_btc_update} bars"
                )
            return

        if not (self._bar_updated and self._btc_bar_updated):
            return

        if not self._check_data_sync():
            return

        # 等待 SMA200 预热完成
        if self.sma is None:
            return

        # 重置更新标记
        self._bar_updated = False
        self._btc_bar_updated = False

        # 计算 Squeeze 状态
        is_squeezing = self._check_squeeze()
        self.squeeze_history.append(is_squeezing)

        # 检查是否有持仓
        if self.portfolio.is_net_long(self.instrument.id):
            # 更新最高价（Chandelier Exit需要）
            if self.highest_high is None:
                self.highest_high = float(bar.high)
            else:
                self.highest_high = max(self.highest_high, float(bar.high))

            self._handle_exit(bar)
        elif not self._pending_entry_order:
            self._handle_entry(bar, is_squeezing)

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

        # ATR (简单平均)
        if len(self.trs) >= self.config.atr_period:
            self.atr = sum(list(self.trs)[-self.config.atr_period:]) / self.config.atr_period

        # ATR (Wilder's Smoothing) - 注释掉，保留以供参考
        # if len(self.trs) >= self.config.atr_period:
        #     if self.atr is None:
        #         # 初始化：使用简单平均
        #         self.atr = sum(list(self.trs)[-self.config.atr_period:]) / self.config.atr_period
        #     else:
        #         # Wilder's Smoothing: α = 1/period
        #         alpha = 1.0 / self.config.atr_period
        #         self.atr = alpha * self.trs[-1] + (1 - alpha) * self.atr

        # SMA
        if len(self.closes) >= self.config.sma_period:
            self.sma = sum(list(self.closes)[-self.config.sma_period:]) / self.config.sma_period

        # Bollinger Bands
        if len(self.closes) >= self.config.bb_period:
            bb_closes = list(self.closes)[-self.config.bb_period:]
            bb_mean = sum(bb_closes) / self.config.bb_period
            variance = sum((x - bb_mean) ** 2 for x in bb_closes) / self.config.bb_period
            bb_std = variance ** 0.5
            self.bb_upper = bb_mean + self.config.bb_std * bb_std
            self.bb_lower = bb_mean - self.config.bb_std * bb_std

        # Volume SMA
        if len(self.volumes) >= self.config.volume_period:
            self.volume_sma = sum(list(self.volumes)[-self.config.volume_period:]) / self.config.volume_period

    def _check_data_sync(self) -> bool:
        """检查主标的和BTC数据是否时间同步"""
        if self.last_bar_ts == 0 or self.last_btc_bar_ts == 0:
            return False

        time_diff = abs(self.last_bar_ts - self.last_btc_bar_ts)
        is_synced = time_diff <= self.DATA_SYNC_TOLERANCE_NS

        if not is_synced:
            self.log.warning(
                f"数据时间不同步: 主标的={self.last_bar_ts}, "
                f"BTC={self.last_btc_bar_ts}, 差异={time_diff / 1_000_000_000:.1f}秒"
            )

        return is_synced

    def _check_squeeze(self) -> bool:
        """检查是否处于 Squeeze 状态"""
        if self.bb_upper is None or self.bb_lower is None or self.ema is None or self.atr is None:
            return False

        # 计算 Keltner Base 通道
        keltner_upper = self.ema + (self.config.keltner_base_multiplier * self.atr)
        keltner_lower = self.ema - (self.config.keltner_base_multiplier * self.atr)

        # Squeeze: 布林带完全在 Keltner 通道内
        return self.bb_upper < keltner_upper and self.bb_lower > keltner_lower

    def _check_filters(self, bar: Bar) -> bool:
        """检查所有过滤器条件"""
        close = float(bar.close)
        volume = float(bar.volume)

        # 1. 趋势过滤：价格在 SMA200 上方
        if self.sma is None or close <= self.sma:
            return False

        # 2. 成交量过滤：放量确认
        if self.volume_sma is None or volume <= self.volume_sma * self.config.volume_multiplier:
            return False

        # 3. Alpha 过滤：相对强弱
        if not self._check_relative_strength():
            return False

        return True

    def _check_relative_strength(self) -> bool:
        """检查相对强弱（RS）"""
        # 需要足够的历史数据
        if len(self.price_history) < self.config.rs_lookback_days + 1:
            return False
        if len(self.btc_price_history) < self.config.rs_lookback_days + 1:
            return False

        # 使用预维护的共同时间戳列表（性能优化：避免每次排序和集合操作）
        if len(self.common_timestamps) < self.config.rs_lookback_days + 1:
            return False

        # 使用最近的对齐数据计算涨幅
        recent_ts = self.common_timestamps[-(self.config.rs_lookback_days + 1):]
        symbol_prices = [self.price_history[ts] for ts in recent_ts]
        btc_prices = [self.btc_price_history[ts] for ts in recent_ts]

        # 防止除零
        if symbol_prices[0] <= 0 or btc_prices[0] <= 0:
            self.log.warning(f"RS计算数据异常: symbol[0]={symbol_prices[0]}, btc[0]={btc_prices[0]}")
            return False

        symbol_perf = (symbol_prices[-1] / symbol_prices[0]) - 1
        btc_perf = (btc_prices[-1] / btc_prices[0]) - 1

        return symbol_perf > btc_perf

    def _handle_entry(self, bar: Bar, is_squeezing: bool) -> None:
        """处理开仓逻辑"""
        close = float(bar.close)

        # 检查过滤器
        if not self._check_filters(bar):
            return

        # 计算触发线
        if self.ema is None or self.atr is None:
            return

        keltner_trigger_upper = self.ema + (self.config.keltner_trigger_multiplier * self.atr)

        # 检查突破
        if close <= keltner_trigger_upper:
            return

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
        min_stop_distance = bar.close.as_decimal() * Decimal("0.005")
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
