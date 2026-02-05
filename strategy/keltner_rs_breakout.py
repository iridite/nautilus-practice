"""
Strategy: Keltner RS Breakout (KRB)
Type: Medium-Frequency Trend Following
Core Logic:
  1. Entry: Close > EMA(20) + 2.25*ATR(20)
  2. Filter A (Market Regime): BTC > SMA(200) and BTC_ATR% < 3%
  3. Filter B (Macro): Close > SMA(200)
  4. Filter C (Alpha): Relative Strength (Symbol vs BTC) > 0
  5. Filter D (Momentum): Volume > 1.5 * SMA(Vol, 20)
  6. Sizing: Volatility Targeting (Base Risk 1.0%, Squeeze Risk 1.5%)
  7. Exit: Chandelier Exit (Highest - 2x ATR) + Time Stop (3 bars)

Two-Layer Filtering Mechanism:
  Layer 1 - Universe Selection:
    - Dynamically filters active coins based on trading volume
    - Updates periodically (Monthly/Weekly/Bi-weekly)
    - Ensures liquidity and data quality

  Layer 2 - Relative Strength (RS) Filtering:
    - Operates within the active Universe pool
    - Calculates weighted RS: 0.4 * RS(5d) + 0.6 * RS(20d)
    - Only trades coins with RS > 0 (outperforming BTC)
    - Ensures buying strong momentum coins in active pool

Note: This strategy implements the "Breathing Trend" philosophy using Static Keltner Channels
and dual-layer filtering (Universe → RS) to ensure trading reasonable targets.

Universe & RS Filtering Mechanism:
  This strategy implements a TWO-LAYER filtering system to ensure trading only strong assets:

  Layer 1 - Universe Pool Selection:
    - Dynamically selects active trading pairs based on historical turnover
    - Updates periodically (Monthly/Weekly/Bi-weekly configurable)
    - Filters out stablecoins and low-liquidity pairs
    - Prevents look-ahead bias: T period data generates T+1 period universe

  Layer 2 - Relative Strength (RS) Filtering:
    - Operates WITHIN the active universe pool
    - Calculates combined RS score: 0.4 * RS(5d) + 0.6 * RS(20d)
    - RS = (Symbol% - BTC%) where Symbol% and BTC% are percentage returns
    - Only enters positions when RS > 0 (symbol outperforms BTC)
    - Ensures buying the strongest assets within the active pool

  Result: Universe narrows the pool → RS selects the strongest within the pool
"""

import json
from collections import OrderedDict, deque
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

import numpy as np
from nautilus_trader.model import Price, Quantity
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId

from strategy.core.base import BaseStrategy, BaseStrategyConfig
from utils import get_project_root
from utils.custom_data import FundingRateData

TARGET_PRECISION = Decimal("0." + "0" * 16)


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
    stop_loss_atr_multiplier: float = 2.0  # 从 3.0 降至 2.0
    enable_time_stop: bool = True  # 启用时间止损
    time_stop_bars: int = 3  # 时间止损 K 线数
    time_stop_momentum_threshold: float = 0.01  # 动能确认阈值（1%）
    breakeven_multiplier: float = 1.0 #保本触发 atr 倍率
    deviation_threshold: float = 0.40  # 抛物线止盈乖离阈值（40%）

    # 过滤器参数
    volume_multiplier: float = 1.5
    rs_short_lookback_days: int = 5  # RS 短期回溯天数
    rs_long_lookback_days: int = 20  # RS 长期回溯天数
    rs_short_weight: float = 0.4  # RS 短期权重
    rs_long_weight: float = 0.6  # RS 长期权重
    squeeze_memory_days: int = 3

    # BTC 市场状态过滤器参数
    enable_btc_regime_filter: bool = True  # 是否启用 BTC 市场状态过滤器
    btc_regime_sma_period: int = 200  # BTC 趋势判定周期
    btc_regime_atr_period: int = 14  # BTC 波动率计算周期
    btc_max_atr_pct: float = 0.03  # BTC ATR 百分比阈值（3%）

    # Universe 参数
    universe_top_n: int | None = None  # Universe 规模（1, 5, 10, 25, 50, 100），None 表示不使用
    universe_freq: str = "ME"  # Universe 更新周期（ME=月度, W-MON=周度, 2W-MON=双周）

    # 其他参数
    min_stop_distance_pct: float = 0.005  # 最小止损距离百分比（0.5%）
    max_history_size: int = 100  # 历史数据最大保存数量


class KeltnerRSBreakoutStrategy(BaseStrategy):
    """
    Keltner RS Breakout 策略

    核心逻辑：
    1. Squeeze 状态判定：布林带收窄进 1.5x ATR 肯特纳通道
    2. 过滤器：BTC市场状态 + 趋势(>SMA200) + 放量(>1.5x均量) + RS(>BTC)
    3. 触发：突破 2.25x ATR 上轨
    4. 仓位：波动率倒数模型，Squeeze 加成
    5. 出场：Chandelier Exit (最高价 - 2x ATR) + 时间止损 (3根K线)
    """

    #TODO 设置一个全局的 Decimal 精度配置

    def __init__(self, config: KeltnerRSBreakoutConfig):
        super().__init__(config)

        # BTC 标的 ID
        self.btc_instrument_id = InstrumentId.from_str(config.btc_instrument_id)

        # 指标数据存储
        self.closes = deque(maxlen=max(config.ema_period, config.bb_period, config.sma_period) + 1)
        self.volumes = deque(maxlen=config.volume_period + 1)
        self.trs = deque(maxlen=config.atr_period)

        ## 指标值
        self.ema: float | None = None
        self.atr = None
        self.sma = None
        self.bb_upper = None
        self.bb_lower = None
        self.volume_sma = None

        # 价格历史（用于 RS 计算）- 使用 OrderedDict 保持插入顺序，优化清理效率
        self.price_history = OrderedDict()  # {timestamp: price}
        self.btc_price_history = OrderedDict()  # {timestamp: price}

        # BTC 市场状态指标
        self.btc_closes = deque(maxlen=max(config.btc_regime_sma_period, config.btc_regime_atr_period) + 1)
        self.btc_trs = deque(maxlen=config.btc_regime_atr_period)
        self.btc_sma = None
        self.btc_atr = None

        # Squeeze 状态历史
        self.squeeze_history = deque(maxlen=config.squeeze_memory_days)

        # 持仓跟踪
        self.entry_price: Decimal | None = None
        self.quantity: Decimal | None = None
        self.entry_bar_count = 0  # 开仓后经过的 K 线数
        self.highest_high = None
        # 风险控制
        self.breakeven_active = False # 默认情况下为否，直到代码满足条件并调整为正

        # 订单状态跟踪
        self._pending_entry_order = False

        # Universe 动态管理
        self.universe_data = {}  # {"2020-02": ["BTCUSDT", ...]}
        self.current_period = None  # 当前周期字符串
        self.active_symbols = set()  # 当前活跃币种集合（基础符号，如 BTCUSDT）
        self._load_universe()

    def _load_universe(self) -> None:
        """加载 Universe JSON 文件"""
        if self.config.universe_top_n is None:
            self.log.warning("未配置 universe_top_n，不使用 Universe 过滤")
            return

        universe_file = get_project_root() / "data" / "universe" / f"universe_{self.config.universe_top_n}_{self.config.universe_freq}.json"
        if not universe_file.exists():
            self.log.warning(f"Universe 文件不存在: {universe_file}")
            return

        try:
            with open(universe_file, "r") as f:
                raw_data = json.load(f)
                # 转换符号格式：BTCUSDT:USDT -> BTCUSDT
                for period, symbols in raw_data.items():
                    self.universe_data[period] = [s.split(":")[0] if ":" in s else s for s in symbols]
            self.log.info(f"成功加载 Universe 文件: {universe_file}, 共 {len(self.universe_data)} 个周期")
        except Exception as e:
            self.log.error(f"加载 Universe 文件失败: {e}")

    def _update_active_universe(self, timestamp: int) -> None:
        """根据时间戳更新活跃币种列表"""
        if not self.universe_data:
            return

        dt = datetime.fromtimestamp(timestamp / 1e9)

        # 根据 universe_freq 生成周期字符串
        if self.config.universe_freq == "ME":
            period_str = dt.strftime("%Y-%m")
        elif self.config.universe_freq == "W-MON":
            period_str = dt.strftime("%Y-W%W")
        elif self.config.universe_freq == "2W-MON":
            # 双周：计算周数并除以2
            week_num = int(dt.strftime("%W"))
            biweek_num = (week_num // 2) + 1
            period_str = f"{dt.year}-W{biweek_num:02d}"
        else:
            # 默认使用月度格式
            period_str = dt.strftime("%Y-%m")

        if period_str != self.current_period:
            old_period = self.current_period
            self.current_period = period_str

            if period_str in self.universe_data:
                old_symbols = self.active_symbols.copy()
                self.active_symbols = set(self.universe_data[period_str])

                if old_period is not None:
                    added = self.active_symbols - old_symbols
                    removed = old_symbols - self.active_symbols
                    self.log.info(
                        f"Universe 周期切换: {old_period} -> {period_str}, "
                        f"活跃币种: {len(self.active_symbols)}, "
                        f"新增: {len(added)}, 移除: {len(removed)}"
                    )
                else:
                    self.log.info(f"初始化 Universe 周期: {period_str}, 活跃币种: {len(self.active_symbols)}")
            else:
                self.log.warning(f"当前周期 {period_str} 不在 Universe 数据中")

    def _is_symbol_active(self) -> bool:
        """判断当前币种是否活跃"""
        if not self.universe_data:
            return True

        # 从 instrument.id 提取基础符号
        # 例如：BTCUSDT-PERP.BINANCE -> BTCUSDT
        instrument_str = str(self.instrument.id)
        base_symbol = instrument_str.split("-")[0].split(".")[0]

        return base_symbol in self.active_symbols

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
            btc_close = float(bar.close)
            self.btc_price_history[bar.ts_event] = btc_close

            # 更新 BTC 市场状态指标
            self.btc_closes.append(btc_close)
            if len(self.btc_closes) > 1:
                btc_high = float(bar.high)
                btc_low = float(bar.low)
                btc_tr = max(
                    btc_high - btc_low,
                    abs(btc_high - self.btc_closes[-2]),
                    abs(btc_low - self.btc_closes[-2])
                )
                self.btc_trs.append(btc_tr)

            self._update_btc_indicators()

            # 清理过期数据（OrderedDict 保证 FIFO 顺序，直接删除第一个元素）
            if len(self.btc_price_history) > self.config.max_history_size:
                self.btc_price_history.popitem(last=False)

            # BTC数据只更新，不触发交易逻辑
            return
        else:
            return

        # 1. 更新 Universe 活跃状态
        self._update_active_universe(bar.ts_event)

        # 2. Warmup 检查
        if self.sma is None:
            return

        # 计算并记录 Squeeze 状态
        is_squeezing = self._check_squeeze()
        self.squeeze_history.append(is_squeezing)

        close = float(bar.close)

        # 3. 持仓检查 - 持仓时只执行出场逻辑
        if self.portfolio.is_net_long(self.instrument.id):
            if self.highest_high is None:
                self.highest_high = float(bar.high)
            else:
                self.highest_high = max(self.highest_high, float(bar.high))

            # 增加 K 线计数
            self.entry_bar_count += 1

            self._handle_exit(bar)
            return

        # 无持仓时执行入场逻辑检查
        if self._pending_entry_order:
            return

        # 4. Universe 活跃状态检查：非活跃币种不开仓
        if not self._is_symbol_active():
            return

        # 5. BTC Market Regime 检查
        if self.config.enable_btc_regime_filter:
            if not self._check_btc_market_regime():
                return

        # 6. Funding Rate Guard
        funding_rate = self._get_funding_rate()
        if funding_rate is not None and funding_rate > 0.0005:
            return

        # 7. Regime 检查
        if close < self.sma:
            return

        # 7. RS 检查
        if not self._check_relative_strength():
            return

        # 8. Volume 检查
        volume = float(bar.volume)
        if self.volume_sma is None or volume < self.volume_sma * self.config.volume_multiplier:
            return

        # 9. Trigger 检查
        if self.ema is None or self.atr is None:
            return

        keltner_trigger_upper = self.ema + (self.config.keltner_trigger_multiplier * self.atr)
        if close <= keltner_trigger_upper:
            return

        # 10. 执行入场
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

    def _update_btc_indicators(self) -> None:
        """更新 BTC 市场状态指标"""
        # BTC SMA(200)
        if len(self.btc_closes) >= self.config.btc_regime_sma_period:
            self.btc_sma = sum(list(self.btc_closes)[-self.config.btc_regime_sma_period:]) / self.config.btc_regime_sma_period

        # BTC ATR(14) - Wilder's Smoothing
        if len(self.btc_trs) >= self.config.btc_regime_atr_period:
            if self.btc_atr is None:
                self.btc_atr = sum(list(self.btc_trs)[-self.config.btc_regime_atr_period:]) / self.config.btc_regime_atr_period
            else:
                alpha = 1.0 / self.config.btc_regime_atr_period
                self.btc_atr = alpha * self.btc_trs[-1] + (1 - alpha) * self.btc_atr



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

    def _check_btc_market_regime(self) -> bool:
        """检查 BTC 市场状态是否适合做多山寨币"""
        # Warmup 检查
        if self.btc_sma is None or self.btc_atr is None:
            return False

        # 获取最新 BTC 价格
        if not self.btc_closes:
            return False
        btc_close = self.btc_closes[-1]

        # 趋势检查：BTC 处于牛市结构
        if btc_close <= self.btc_sma:
            return False

        # 波动率检查：ATR 百分比未极端放大
        btc_atr_pct = self.btc_atr / btc_close
        if btc_atr_pct > self.config.btc_max_atr_pct:
            return False

        return True

    def _calculate_rs_score(self) -> float | None:
        """计算 RS 分数（长短结合）"""
        btc_bar_type_str = self.config.bar_type.replace(
            self.instrument.id.symbol.value,
            self.btc_instrument_id.symbol.value
        )
        btc_bar_type = BarType.from_str(btc_bar_type_str)
        btc_bar = self.cache.bar(btc_bar_type)

        if btc_bar is None:
            return None

        btc_close = float(btc_bar.close)
        if btc_bar.ts_event not in self.btc_price_history:
            self.btc_price_history[btc_bar.ts_event] = btc_close

        # 需要足够的历史数据（长期回溯天数 + 1）
        max_lookback = max(self.config.rs_short_lookback_days, self.config.rs_long_lookback_days)
        if len(self.price_history) < max_lookback + 1:
            return None
        if len(self.btc_price_history) < max_lookback + 1:
            return None

        common_timestamps = sorted(set(self.price_history.keys()) & set(self.btc_price_history.keys()))
        if len(common_timestamps) < max_lookback + 1:
            return None

        # 计算短期 RS
        short_ts = common_timestamps[-(self.config.rs_short_lookback_days + 1):]
        short_symbol_prices = [self.price_history[ts] for ts in short_ts]
        short_btc_prices = [self.btc_price_history[ts] for ts in short_ts]

        if short_symbol_prices[0] <= 0 or short_btc_prices[0] <= 0:
            return None

        short_symbol_perf = (short_symbol_prices[-1] / short_symbol_prices[0]) - 1
        short_btc_perf = (short_btc_prices[-1] / short_btc_prices[0]) - 1
        short_rs = short_symbol_perf - short_btc_perf

        # 计算长期 RS
        long_ts = common_timestamps[-(self.config.rs_long_lookback_days + 1):]
        long_symbol_prices = [self.price_history[ts] for ts in long_ts]
        long_btc_prices = [self.btc_price_history[ts] for ts in long_ts]

        if long_symbol_prices[0] <= 0 or long_btc_prices[0] <= 0:
            return None

        long_symbol_perf = (long_symbol_prices[-1] / long_symbol_prices[0]) - 1
        long_btc_perf = (long_btc_prices[-1] / long_btc_prices[0]) - 1
        long_rs = long_symbol_perf - long_btc_perf

        # 加权组合：0.4 * RS(5d) + 0.6 * RS(20d)
        combined_rs = self.config.rs_short_weight * short_rs + self.config.rs_long_weight * long_rs

        return combined_rs

    def _check_relative_strength(self) -> bool:
        """检查相对强弱（RS）- 短期强度过滤器"""
        rs_score = self._calculate_rs_score()
        return rs_score is not None and rs_score > 0

    def _handle_entry(self, bar: Bar, is_squeezing: bool, keltner_trigger_upper: float) -> None:
        """处理开仓逻辑（过滤器已在 on_bar 中检查）"""
        close = float(bar.close)

        # 检查持仓数量限制
        total_positions = len(self.cache.positions_open())
        if total_positions >= self.config.max_positions:
            return

        # 判断是否为高确信度设置
        high_conviction = is_squeezing or any(self.squeeze_history)

        # 计算仓位
        qty = self._calculate_position_size(bar, high_conviction)
        if not qty or qty <= 0:
            return

        # 下单
        order = self.order_factory.market( # 市价下单
            instrument_id=self.instrument.id,
            order_side=OrderSide.BUY,
            # 使用基类的仓位计算方法进行标准化
            quantity=self.instrument.make_qty(qty),
        )
        self.submit_order(order)
        self._pending_entry_order = True

        # 记录持仓信息
        self.entry_price = Decimal(close).quantize(TARGET_PRECISION, ROUND_HALF_UP)
        # 这里实际上应该是在确定 tick 的那一瞬间进行记录，
        # 但是我们这里既然做的是是中低频趋势跟踪策略，那么这个小差距也是可以接受的（1D bar timeframe）
        self.quantity = qty.quantize(TARGET_PRECISION, ROUND_HALF_UP)  # 记录仓位数量（转换为 Decimal）

        self.entry_bar_count = 0  # 重置 K 线计数
        self.highest_high = float(bar.high)

        conviction_type = "高确信度" if high_conviction else "普通"
        self.log.info(
            f"开仓做多 ({conviction_type}): "
            f"price={close:.2f}, trigger={keltner_trigger_upper:.2f}, "
            f"qty={qty}, squeeze={is_squeezing}"
        )

    def _calculate_position_size(self, bar: Bar, high_conviction: bool) -> Decimal:
        # AI 代码生成的这里返回 decimal，
        # 但是实际上返回的是 Quantity 类型，而且静态检查并不能发现这个问题
        """计算仓位大小"""
        # 获取账户权益
        account = self.portfolio.account(self.instrument.id.venue)
        if not account:
            return Decimal("0")
        equity = account.balance_total(self.instrument.quote_currency)
        if not equity or equity.as_decimal() <= 0:
            return Decimal("0")

        # 如果配置了 qty_percent，使用百分比模式
        if self.config.qty_percent is not None:
            qty_pct = Decimal(str(self.config.qty_percent))
            leverage = Decimal(str(self.config.leverage))
            price = bar.close.as_decimal()
            qty = (equity.as_decimal() * qty_pct * leverage) / price
            return self.instrument.make_qty(qty)

        # 否则使用 ATR 风险模式
        if self.atr is None:
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

        # 计算仓位：(权益 * 风险% * 杠杆) / 止损距离
        risk_amount = equity.as_decimal() * Decimal(str(risk_pct)) * Decimal(str(self.config.leverage))
        # risk_amount 可以存起来方便 breakeven 的计算
        qty: Decimal  = risk_amount / stop_distance

        # 检查数量是否小于最小要求（避免 make_qty 抛出异常）
        min_qty = Decimal(str(self.instrument.size_increment))
        if qty < min_qty:
            self.log.warning(
                f"计算的仓位数量过小: raw_qty={qty}, min_qty={min_qty}, "
                f"size_increment={self.instrument.size_increment}, size_precision={self.instrument.size_precision}"
            )
            return Decimal("0")
        return qty

    def _handle_exit(self, bar: Bar) -> None:
        """处理出场逻辑"""
        close = float(bar.close) # 当前 bar 的收盘价，可用于参考和指导下一步行动

        # 1. 时间止损检查（优先）
        if self.config.enable_time_stop and self.entry_bar_count >= self.config.time_stop_bars:
            # 检查动能：最高价是否突破成本区
            momentum_threshold = 1 + self.config.time_stop_momentum_threshold
            if self.highest_high < self.entry_price * momentum_threshold:
                self.close_all_positions(self.instrument.id)
                self.log.info(
                    f"时间止损平仓: bars={self.entry_bar_count}, "
                    f"highest={self.highest_high:.2f}, entry={self.entry_price:.2f}"
                )
                self._reset_position_tracking()
                return

        # 2. 跟踪止损检查 （Chandelier Exit）
        if self.atr is not None:
            trailing_stop = self.highest_high - (self.config.stop_loss_atr_multiplier * self.atr)
            if close < trailing_stop:
                self.close_all_positions(self.instrument.id)
                self.log.info(
                    f"Chandelier Exit 平仓: "
                    f"price={close:.2f}, stop={trailing_stop:.2f}, "
                    f"highest={self.highest_high:.2f}"
                )
                self._reset_position_tracking()
                return

        # 抛物线止盈
        # 乖离阈值计算
        if self.ema is not None:
            deviation_pct = (close - self.ema) / self.ema
            if deviation_pct >= self.config.deviation_threshold:  # 配置乖离阈值
                # 关于这个 “乖离” 阈值的设置，ai 针对不同的币种有着不同的推荐数值，后期可能需要进一步调研和优化
                self.close_all_positions(self.instrument.id)
                self.log.info(
                    f"抛物线止盈平仓: price={close:.2f}, ema={self.ema:.2f}, deviation={deviation_pct:.4f}"
                )
                self._reset_position_tracking()
                return



        # 3. 保本止损机制（Breakeven Stop）
        # 目标：当浮盈达到 1.0 * ATR 时，将止损位移动到开仓价 + 0.2%（覆盖手续费）
        # 这会将许多"小亏单"变成"平手单"，减少回撤，改善胜率和心态
        if self.entry_price is None:
            return
        # 注意在此之后的代码块都受到 self.entry_price 非 None 的保证和影响

        # 3.1 激活保本模式：
        # 当价格突破 entry_price + breakeven_multiplier * ATR
        # TODO: 还存在一种基于 initial_risk + risk 的计算方式，但这里我们使用 ATR 方式
        if self.atr is not None:
            breakeven_trigger_price = self.entry_price + Decimal(self.config.breakeven_multiplier * self.atr)
            if close > breakeven_trigger_price and not self.breakeven_active:
                self.breakeven_active = True
                self.log.info(
                    f"✅ 保本模式激活: price={close:.2f}, "
                    f"trigger={breakeven_trigger_price:.2f}, "
                    f"breakeven_stop={self.entry_price * Decimal("1.002"):.2f}"
                )

        # 3.2 执行保本止损：如果已激活且价格跌破保本价，立即市价平仓
        if self.breakeven_active:
            breakeven_stop_price = self.entry_price * Decimal("1.002")  # 开仓价 + 0.2% 缓冲（覆盖手续费）
            if close < breakeven_stop_price:
                self.close_all_positions(self.instrument.id)
                self.log.info(
                    f"🛡️ 保本止损平仓: price={close:.2f}, "
                    f"breakeven_stop={breakeven_stop_price:.2f}, "
                    f"entry={self.entry_price:.2f}"
                )
                self._reset_position_tracking() # 所有执行了即可清仓命令之后都需要重置持仓跟踪变量
                return

    def _reset_position_tracking(self) -> None:
        """重置持仓跟踪变量"""
        self.entry_price = None
        self.quantity = None
        self.entry_bar_count = 0
        self.highest_high = None
        self.breakeven_active = False

    def on_order_filled(self, event) -> None:
        """订单成交回调"""
        super().on_order_filled(event)
        self._pending_entry_order = False

    def on_order_rejected(self, event) -> None:
        """订单拒绝回调"""
        super().on_order_rejected(event)
        self._pending_entry_order = False
        self.log.error(f"订单被拒绝: {event.reason}")
