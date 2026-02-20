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
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

import numpy as np
from nautilus_trader.indicators import RelativeStrengthIndex
from nautilus_trader.model.data import Bar, BarType, CustomData, DataType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId

from strategy.core.base import BaseStrategy, BaseStrategyConfig
from utils import get_project_root
from utils.custom_data import FundingRateData
from config.constants import (
    DEFAULT_EMA_PERIOD,
    DEFAULT_SMA_PERIOD,
    DEFAULT_ATR_PERIOD_LONG,
    DEFAULT_BB_PERIOD,
    DEFAULT_BB_STD,
    DEFAULT_RSI_PERIOD,
    DEFAULT_KELTNER_BASE_MULTIPLIER,
    DEFAULT_KELTNER_TRIGGER_MULTIPLIER,
    DEFAULT_VOLUME_MULTIPLIER,
    RS_SHORT_PERIOD,
    RS_LONG_PERIOD,
    RS_SHORT_WEIGHT,
    RS_LONG_WEIGHT,
    RS_THRESHOLD,
    BASE_RISK_PCT,
    HIGH_CONVICTION_RISK_PCT,
    STOP_LOSS_ATR_MULTIPLIER,
    BREAKEVEN_MULTIPLIER,
    MIN_STOP_DISTANCE_PCT,
    TIME_STOP_BARS,
    MOMENTUM_THRESHOLD,
    DEVIATION_THRESHOLD,
    MAX_UPPER_WICK_RATIO,
    BTC_REGIME_SMA_PERIOD,
    BTC_REGIME_ATR_PERIOD,
    VOLATILITY_THRESHOLD,
    FUNDING_RATE_WARNING_ANNUAL,
    FUNDING_RATE_DANGER_ANNUAL,
    BTC_DOMINANCE_CHANGE_THRESHOLD,
    BTC_DOMINANCE_LOOKBACK_DAYS,
    EUPHORIA_REDUCE_POSITION_PCT,
    SQUEEZE_MEMORY_DAYS,
    EMA_ALPHA_NUMERATOR,
    EMA_ALPHA_DENOMINATOR_OFFSET,
    ATR_ALPHA_NUMERATOR,
    MAX_HISTORY_SIZE,
    TARGET_PRECISION_DECIMALS,
)

TARGET_PRECISION = Decimal("0." + "0" * TARGET_PRECISION_DECIMALS)


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
    ema_period: int = DEFAULT_EMA_PERIOD
    atr_period: int = DEFAULT_ATR_PERIOD_LONG
    sma_period: int = DEFAULT_SMA_PERIOD
    rsi_period: int = DEFAULT_RSI_PERIOD
    bb_period: int = DEFAULT_BB_PERIOD
    bb_std: float = DEFAULT_BB_STD
    volume_period: int = DEFAULT_ATR_PERIOD_LONG

    # 通道参数
    keltner_base_multiplier: float = DEFAULT_KELTNER_BASE_MULTIPLIER
    keltner_trigger_multiplier: float = DEFAULT_KELTNER_TRIGGER_MULTIPLIER

    # 风控参数
    base_risk_pct: float = BASE_RISK_PCT
    high_conviction_risk_pct: float = HIGH_CONVICTION_RISK_PCT
    stop_loss_atr_multiplier: float = STOP_LOSS_ATR_MULTIPLIER
    enable_time_stop: bool = True  # 启用时间止损
    time_stop_bars: int = TIME_STOP_BARS  # 时间止损 K 线数
    time_stop_momentum_threshold: float = MOMENTUM_THRESHOLD  # 动能确认阈值（1%）
    breakeven_multiplier: float = BREAKEVEN_MULTIPLIER #保本触发 atr 倍率
    deviation_threshold: float = DEVIATION_THRESHOLD  # 抛物线止盈乖离阈值（40%）
    enable_rsi_stop_loss: bool = False # 启用 RSI 超买止损
    # 暂且不启用，由于抛物线止盈和 RSI 止盈功能上有重复倾向
    max_upper_wick_ratio: float = MAX_UPPER_WICK_RATIO  # K 线最大上影线比例（30%）

    # 过滤器参数
    volume_multiplier: float = DEFAULT_VOLUME_MULTIPLIER
    rs_short_lookback_days: int = RS_SHORT_PERIOD  # RS 短期回溯天数
    rs_long_lookback_days: int = RS_LONG_PERIOD  # RS 长期回溯天数
    rs_short_weight: float = RS_SHORT_WEIGHT  # RS 短期权重
    rs_long_weight: float = RS_LONG_WEIGHT  # RS 长期权重
    squeeze_memory_days: int = SQUEEZE_MEMORY_DAYS

    # BTC 市场状态过滤器参数
    enable_btc_regime_filter: bool = True  # 是否启用 BTC 市场状态过滤器
    btc_regime_sma_period: int = BTC_REGIME_SMA_PERIOD  # BTC 趋势判定周期
    btc_regime_atr_period: int = BTC_REGIME_ATR_PERIOD  # BTC 波动率计算周期
    btc_max_atr_pct: float = VOLATILITY_THRESHOLD  # BTC ATR 百分比阈值（3%）

    # 市场狂热度过滤器参数（基于 Funding Rate 和 BTC Dominance）
    enable_euphoria_filter: bool = True  # 是否启用市场狂热度过滤器
    funding_rate_warning_annual: float = FUNDING_RATE_WARNING_ANNUAL  # 资金费率警告阈值（年化%，停止开仓）
    funding_rate_danger_annual: float = FUNDING_RATE_DANGER_ANNUAL  # 资金费率危险阈值（年化%，开始清仓）
    enable_btc_dominance_filter: bool = False  # 是否启用 BTC Dominance 过滤器（需要额外数据源）
    btc_dominance_change_threshold: float = BTC_DOMINANCE_CHANGE_THRESHOLD  # BTC Dominance 变化阈值（%）
    btc_dominance_lookback_days: int = BTC_DOMINANCE_LOOKBACK_DAYS  # BTC Dominance 回溯天数
    euphoria_reduce_position_pct: float = EUPHORIA_REDUCE_POSITION_PCT  # 狂热状态下减仓比例（50%）

    # Universe 参数
    universe_top_n: int | None = None  # Universe 规模（1, 5, 10, 25, 50, 100），None 表示不使用
    universe_freq: str = "ME"  # Universe 更新周期（ME=月度, W-MON=周度, 2W-MON=双周）

    # 其他参数
    min_stop_distance_pct: float = MIN_STOP_DISTANCE_PCT  # 最小止损距离百分比（0.5%）
    max_history_size: int = MAX_HISTORY_SIZE  # 历史数据最大保存数量


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

    # Note: 全局 Decimal 精度已在 config/constants.py 中定义为 TARGET_PRECISION_DECIMALS

    def __init__(self, config: KeltnerRSBreakoutConfig):
        super().__init__(config)

        # BTC 标的 ID
        self.btc_instrument_id = InstrumentId.from_str(config.btc_instrument_id)

        # Technical Analysis Indicators
        ## 指标数据存储
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
        self.rsi: float | None = None

        ## TA instances
        self.rsi_indicator = RelativeStrengthIndex(period=config.rsi_period)

        # 价格历史（用于 RS 计算）- 使用 OrderedDict 保持插入顺序，优化清理效率
        self.price_history = OrderedDict()  # {timestamp: price}
        self.btc_price_history = OrderedDict()  # {timestamp: price}

        # BTC 市场状态指标
        self.btc_closes = deque(maxlen=max(config.btc_regime_sma_period, config.btc_regime_atr_period) + 1)
        self.btc_trs = deque(maxlen=config.btc_regime_atr_period)
        self.btc_sma = None
        self.btc_atr = None

        # 市场狂热度监控
        self.current_funding_rate: float | None = None  # 当前资金费率
        self.funding_rate_annual: float | None = None  # 年化资金费率
        self.market_euphoria_level: str = "NORMAL"  # 市场狂热度等级：NORMAL, WARNING, DANGER
        self.euphoria_reduced: bool = False  # 是否已执行狂热减仓（防止重复触发）
        self.btc_dominance_history = deque(maxlen=config.btc_dominance_lookback_days)  # BTC 市占率历史

        # Squeeze 状态历史
        self.squeeze_history = deque(maxlen=config.squeeze_memory_days)

        # 持仓跟踪
        self.entry_price: Decimal | None = None
        self.quantity: Decimal | None = None
        self.entry_bar_count = 0  # 开仓后经过的 K 线数
        self.highest_high = None
        # 风险控制
        ## status variables
        self.breakeven_active = False # 默认情况下为否，直到代码满足条件并调整为正
        self.rsi_watcher = False # RSI 超买观察者，在 rsi 大于阈值之后开始监控价格

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

    def _get_period_string(self, dt: datetime) -> str:
        """根据universe_freq生成周期字符串"""
        if self.config.universe_freq == "ME":
            return dt.strftime("%Y-%m")
        elif self.config.universe_freq == "W-MON":
            return dt.strftime("%Y-W%W")
        elif self.config.universe_freq == "2W-MON":
            week_num = int(dt.strftime("%W"))
            biweek_num = (week_num // 2) + 1
            return f"{dt.year}-W{biweek_num:02d}"
        else:
            return dt.strftime("%Y-%m")

    def _log_universe_change(self, old_period: str | None, period_str: str, old_symbols: set, new_symbols: set):
        """记录Universe周期变化"""
        if old_period is not None:
            added = new_symbols - old_symbols
            removed = old_symbols - new_symbols
            self.log.info(
                f"Universe 周期切换: {old_period} -> {period_str}, "
                f"活跃币种: {len(new_symbols)}, "
                f"新增: {len(added)}, 移除: {len(removed)}"
            )
        else:
            self.log.info(f"初始化 Universe 周期: {period_str}, 活跃币种: {len(new_symbols)}")

    def _update_active_symbols(self, period_str: str) -> bool:
        """更新活跃币种列表，返回是否成功"""
        if period_str not in self.universe_data:
            self.log.warning(f"当前周期 {period_str} 不在 Universe 数据中")
            return False
        
        old_symbols = self.active_symbols.copy()
        self.active_symbols = set(self.universe_data[period_str])
        self._log_universe_change(self.current_period, period_str, old_symbols, self.active_symbols)
        return True

    def _update_active_universe(self, timestamp: int) -> None:
        """根据时间戳更新活跃币种列表"""
        if not self.universe_data:
            return

        dt = datetime.fromtimestamp(timestamp / 1e9)
        period_str = self._get_period_string(dt)

        if period_str != self.current_period:
            old_period = self.current_period
            self.current_period = period_str
            self._update_active_symbols(period_str)

    def _is_symbol_active(self) -> bool:
        """判断当前币种是否活跃"""
        if not self.universe_data:
            return True

        # 从 instrument.id 提取基础符号，优先使用工具函数以覆盖多种格式。
        # parse_instrument_id 返回的 symbol 形式为 'BASE-USDT'，需要去掉连字符以匹配 Universe 中的 'BASEUSDT' 格式。
        try:
            from utils.instrument_helpers import parse_instrument_id

            symbol, _, _ = parse_instrument_id(str(self.instrument.id))
            base_symbol = symbol.replace("-", "") if symbol else ""
        except Exception:
            # 兼容回退：保留原有简单解析逻辑
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

        # indicators initialization can be done here if needed
        self.rsi_indicator.update_raw(0.0)  # 初始化 RSI 指标

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

        # 订阅 Funding Rate 数据（如果启用市场狂热度过滤器）
        if self.config.enable_euphoria_filter:
            funding_data_type = DataType(FundingRateData, metadata={"instrument_id": self.instrument.id})
            self.subscribe_data(funding_data_type)
            self.log.info(f"已订阅 Funding Rate 数据: {self.instrument.id}")

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

        # 取消订阅 Funding Rate 数据
        if self.config.enable_euphoria_filter:
            funding_data_type = DataType(FundingRateData, metadata={"instrument_id": self.instrument.id})
            self.unsubscribe_data(funding_data_type)

    def on_data(self, data: CustomData) -> None:
        """处理自定义数据（如 Funding Rate）"""
        if isinstance(data, FundingRateData):
            self._handle_funding_rate(data)

    def _handle_funding_rate(self, data: FundingRateData) -> None:
        """处理 Funding Rate 数据并更新市场狂热度等级"""
        self.current_funding_rate = float(data.funding_rate)
        self.funding_rate_annual = float(data.funding_rate_annual)

        # 更新市场狂热度等级（只监控正资金费率，负费率表示空头支付多头，不是狂热信号）
        old_level = self.market_euphoria_level
        if self.funding_rate_annual >= self.config.funding_rate_danger_annual:
            self.market_euphoria_level = "DANGER"
        elif self.funding_rate_annual >= self.config.funding_rate_warning_annual:
            self.market_euphoria_level = "WARNING"
        else:
            self.market_euphoria_level = "NORMAL"
            # 恢复正常状态时重置减仓标志
            self.euphoria_reduced = False

        # 记录等级变化
        if old_level != self.market_euphoria_level:
            self.log.warning(
                f"市场狂热度等级变化: {old_level} -> {self.market_euphoria_level}, "
                f"Funding Rate: {self.current_funding_rate:.4%}, "
                f"年化: {self.funding_rate_annual:.2f}%"
            )

        # 如果进入危险状态且有持仓，且尚未减仓，触发减仓逻辑
        if (self.market_euphoria_level == "DANGER" and
            self.quantity is not None and
            not self.euphoria_reduced):
            self._handle_euphoria_reduce_position()


    def _process_main_instrument_bar(self, bar: Bar) -> None:
        """处理主标的Bar数据"""
        close = float(bar.close)
        high = float(bar.high)
        low = float(bar.low)
        volume = float(bar.volume)

        self.closes.append(close)
        self.volumes.append(volume)

        if len(self.closes) > 1:
            tr = max(
                high - low,
                abs(high - self.closes[-2]),
                abs(low - self.closes[-2])
            )
            self.trs.append(tr)

        if self.config.enable_rsi_stop_loss:
            self.rsi_indicator.handle_bar(bar)
            self.rsi = self.rsi_indicator.value

        self._update_indicators()
        self.price_history[bar.ts_event] = close

        if len(self.price_history) > self.config.max_history_size:
            self.price_history.popitem(last=False)

    def _process_btc_bar(self, bar: Bar) -> None:
        """处理BTC Bar数据"""
        btc_close = float(bar.close)
        self.btc_price_history[bar.ts_event] = btc_close
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

        if len(self.btc_price_history) > self.config.max_history_size:
            self.btc_price_history.popitem(last=False)

    def _handle_position_management(self, bar: Bar) -> None:
        """处理持仓管理"""
        if self.highest_high is None:
            self.highest_high = float(bar.high)
        else:
            self.highest_high = max(self.highest_high, float(bar.high))
        
        self.entry_bar_count += 1
        self._handle_exit(bar)

    def _check_basic_entry_conditions(self) -> bool:
        """检查基本入场条件"""
        if self._pending_entry_order:
            return False
        
        if not self._is_symbol_active():
            return False
        
        return True

    def _check_market_filters(self) -> bool:
        """检查市场过滤条件"""
        if self.config.enable_btc_regime_filter:
            if not self._check_btc_market_regime():
                return False
        
        if self.config.enable_euphoria_filter:
            if self.market_euphoria_level in ("DANGER", "WARNING"):
                return False
        
        return True

    def _check_price_and_strength(self, close: float) -> bool:
        """检查价格和相对强度"""
        if close < self.sma:
            return False
        
        if not self._check_relative_strength():
            return False
        
        return True

    def _check_volume_condition(self, bar: Bar) -> bool:
        """检查成交量条件"""
        volume = float(bar.volume)
        if self.volume_sma is None or volume < self.volume_sma * self.config.volume_multiplier:
            return False
        return True

    def _check_keltner_breakout(self, close: float) -> bool:
        """检查Keltner通道突破"""
        if self.ema is None or self.atr is None:
            return False
        
        keltner_trigger_upper = self.ema + (self.config.keltner_trigger_multiplier * self.atr)
        if close <= keltner_trigger_upper:
            return False
        
        return True

    def _check_wick_ratio(self, bar: Bar) -> bool:
        """检查上影线比例"""
        body_size = float(bar.high) - float(bar.low)
        upper_wick = float(bar.high) - float(bar.close)
        if body_size > 0:
            upper_wick_ratio = upper_wick / body_size
            if upper_wick_ratio > self.config.max_upper_wick_ratio:
                return False
        return True

    def _check_entry_conditions(self, bar: Bar, close: float) -> bool:
        """检查入场条件"""
        if not self._check_basic_entry_conditions():
            return False
        
        if not self._check_market_filters():
            return False
        
        if not self._check_price_and_strength(close):
            return False
        
        if not self._check_volume_condition(bar):
            return False
        
        if not self._check_keltner_breakout(close):
            return False
        
        if not self._check_wick_ratio(bar):
            return False
        
        return True


    def on_bar(self, bar: Bar) -> None:
        """处理 Bar 数据"""
        if bar.bar_type.instrument_id == self.instrument.id:
            self._process_main_instrument_bar(bar)
        elif bar.bar_type.instrument_id == self.btc_instrument_id:
            self._process_btc_bar(bar)
            return
        else:
            return

        self._update_active_universe(bar.ts_event)

        if self.sma is None:
            return

        is_squeezing = self._check_squeeze()
        self.squeeze_history.append(is_squeezing)
        close = float(bar.close)

        if self.portfolio.is_net_long(self.instrument.id):
            self._handle_position_management(bar)
            return

        if self._check_entry_conditions(bar, close):
            keltner_trigger_upper = self.ema + (self.config.keltner_trigger_multiplier * self.atr)
            self._handle_entry(bar, is_squeezing, keltner_trigger_upper)


    def _update_ema(self):
        """更新EMA指标"""
        if len(self.closes) < self.config.ema_period:
            return
        
        if self.ema is None:
            self.ema = sum(list(self.closes)[-self.config.ema_period:]) / self.config.ema_period
        else:
            alpha = EMA_ALPHA_NUMERATOR / (self.config.ema_period + EMA_ALPHA_DENOMINATOR_OFFSET)
            self.ema = alpha * self.closes[-1] + (1 - alpha) * self.ema

    def _update_atr(self):
        """更新ATR指标 (Wilder's Smoothing / RMA)"""
        if len(self.trs) < self.config.atr_period:
            return
        
        if self.atr is None:
            self.atr = sum(list(self.trs)[-self.config.atr_period:]) / self.config.atr_period
        else:
            alpha = ATR_ALPHA_NUMERATOR / self.config.atr_period
            self.atr = alpha * self.trs[-1] + (1 - alpha) * self.atr

    def _update_sma(self):
        """更新SMA指标"""
        if len(self.closes) >= self.config.sma_period:
            self.sma = sum(list(self.closes)[-self.config.sma_period:]) / self.config.sma_period

    def _update_bollinger_bands(self):
        """更新Bollinger Bands指标"""
        if len(self.closes) >= self.config.bb_period:
            bb_closes = np.array(list(self.closes)[-self.config.bb_period:])
            bb_mean = bb_closes.mean()
            bb_std = bb_closes.std()
            self.bb_upper = bb_mean + self.config.bb_std * bb_std
            self.bb_lower = bb_mean - self.config.bb_std * bb_std

    def _update_volume_sma(self):
        """更新Volume SMA指标"""
        if len(self.volumes) >= self.config.volume_period:
            self.volume_sma = sum(list(self.volumes)[-self.config.volume_period:]) / self.config.volume_period

    def _update_indicators(self) -> None:
        """更新所有指标"""
        self._update_ema()
        self._update_atr()
        self._update_sma()
        self._update_bollinger_bands()
        self._update_volume_sma()

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

    def _get_btc_bar_and_update_history(self) -> tuple[Bar | None, float | None]:
        """获取BTC bar并更新历史价格"""
        btc_bar_type_str = self.config.bar_type.replace(
            self.instrument.id.symbol.value,
            self.btc_instrument_id.symbol.value
        )
        btc_bar_type = BarType.from_str(btc_bar_type_str)
        btc_bar = self.cache.bar(btc_bar_type)

        if btc_bar is None:
            return None, None

        btc_close = float(btc_bar.close)
        if btc_bar.ts_event not in self.btc_price_history:
            self.btc_price_history[btc_bar.ts_event] = btc_close

        return btc_bar, btc_close

    def _validate_rs_data_availability(self, max_lookback: int) -> list | None:
        """验证RS计算所需的数据是否充足"""
        if len(self.price_history) < max_lookback + 1:
            return None
        if len(self.btc_price_history) < max_lookback + 1:
            return None

        common_timestamps = sorted(set(self.price_history.keys()) & set(self.btc_price_history.keys()))
        if len(common_timestamps) < max_lookback + 1:
            return None

        return common_timestamps

    def _calculate_period_rs(self, common_timestamps: list, lookback_days: int) -> float | None:
        """计算指定周期的RS值"""
        period_ts = common_timestamps[-(lookback_days + 1):]
        symbol_prices = [self.price_history[ts] for ts in period_ts]
        btc_prices = [self.btc_price_history[ts] for ts in period_ts]

        if symbol_prices[0] <= 0 or btc_prices[0] <= 0:
            return None

        symbol_perf = (symbol_prices[-1] / symbol_prices[0]) - 1
        btc_perf = (btc_prices[-1] / btc_prices[0]) - 1
        return symbol_perf - btc_perf

    def _calculate_rs_score(self) -> float | None:
        """计算 RS 分数（长短结合）"""
        # 获取BTC数据并更新历史
        btc_bar, btc_close = self._get_btc_bar_and_update_history()
        if btc_bar is None:
            return None

        # 验证数据充足性
        max_lookback = max(self.config.rs_short_lookback_days, self.config.rs_long_lookback_days)
        common_timestamps = self._validate_rs_data_availability(max_lookback)
        if common_timestamps is None:
            return None

        # 计算短期和长期RS
        short_rs = self._calculate_period_rs(common_timestamps, self.config.rs_short_lookback_days)
        if short_rs is None:
            return None

        long_rs = self._calculate_period_rs(common_timestamps, self.config.rs_long_lookback_days)
        if long_rs is None:
            return None

        # 加权组合：0.4 * RS(5d) + 0.6 * RS(20d)
        combined_rs = self.config.rs_short_weight * short_rs + self.config.rs_long_weight * long_rs
        return combined_rs

    def _check_relative_strength(self) -> bool:
        """检查相对强弱（RS）- 短期强度过滤器"""
        rs_score = self._calculate_rs_score()
        return rs_score is not None and rs_score > RS_THRESHOLD

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
        self.euphoria_reduced = False  # 重置狂热减仓标志

        conviction_type = "高确信度" if high_conviction else "普通"
        self.log.info(
            f"开仓做多 ({conviction_type}): "
            f"price={close:.2f}, trigger={keltner_trigger_upper:.2f}, "
            f"qty={qty}, squeeze={is_squeezing}"
        )

    def _get_account_equity(self) -> Decimal | None:
        """获取账户权益"""
        account = self.portfolio.account(self.instrument.id.venue)
        if not account:
            return None
        equity = account.balance_total(self.instrument.quote_currency)
        if not equity or equity.as_decimal() <= 0:
            return None
        return equity.as_decimal()

    def _calculate_qty_by_percent(self, equity: Decimal, bar: Bar) -> Decimal:
        """使用百分比模式计算仓位"""
        qty_pct = Decimal(str(self.config.qty_percent))
        leverage = Decimal(str(self.config.leverage))
        price = bar.close.as_decimal()
        qty = (equity * qty_pct * leverage) / price
        return self.instrument.make_qty(qty)

    def _get_risk_percent(self, high_conviction: bool) -> Decimal:
        """获取风险百分比"""
        return Decimal(str(
            self.config.high_conviction_risk_pct if high_conviction
            else self.config.base_risk_pct
        ))

    def _calculate_stop_distance(self, bar: Bar) -> Decimal:
        """计算止损距离"""
        stop_distance = Decimal(str(self.config.stop_loss_atr_multiplier)) * Decimal(str(self.atr))
        min_stop_distance = bar.close.as_decimal() * Decimal(str(self.config.min_stop_distance_pct))
        
        if stop_distance < min_stop_distance:
            self.log.warning(f"ATR过小({self.atr:.6f})，使用最小止损距离{min_stop_distance}")
            return min_stop_distance
        
        return stop_distance

    def _calculate_qty_by_atr(self, equity: Decimal, stop_distance: Decimal, high_conviction: bool) -> Decimal:
        """使用ATR风险模式计算仓位"""
        risk_pct = self._get_risk_percent(high_conviction)
        risk_amount = equity * risk_pct * Decimal(str(self.config.leverage))
        qty = risk_amount / stop_distance
        
        min_qty = Decimal(str(self.instrument.size_increment))
        if qty < min_qty:
            self.log.warning(
                f"计算的仓位数量过小: raw_qty={qty}, min_qty={min_qty}, "
                f"size_increment={self.instrument.size_increment}, size_precision={self.instrument.size_precision}"
            )
            return Decimal("0")
        
        return qty

    def _calculate_position_size(self, bar: Bar, high_conviction: bool) -> Decimal:
        # AI 代码生成的这里返回 decimal，
        # 但是实际上返回的是 Quantity 类型，而且静态检查并不能发现这个问题
        """计算仓位大小"""
        equity = self._get_account_equity()
        if equity is None:
            return Decimal("0")

        if self.config.qty_percent is not None:
            return self._calculate_qty_by_percent(equity, bar)

        if self.atr is None:
            return Decimal("0")

        stop_distance = self._calculate_stop_distance(bar)
        return self._calculate_qty_by_atr(equity, stop_distance, high_conviction)

    def _handle_euphoria_reduce_position(self) -> None:
        """处理市场狂热状态下的减仓逻辑"""
        if self.quantity is None or self.entry_price is None:
            return

        # 计算减仓数量（减仓配置比例的仓位）
        reduce_quantity = (self.quantity * Decimal(str(self.config.euphoria_reduce_position_pct))).quantize(
            TARGET_PRECISION, ROUND_DOWN
        )

        if reduce_quantity <= 0:
            return

        # 执行减仓
        self.log.warning(
            f"🔥 市场狂热减仓: 当前仓位={self.quantity}, "
            f"减仓数量={reduce_quantity}, 减仓比例={self.config.euphoria_reduce_position_pct:.0%}, "
            f"Funding Rate 年化={self.funding_rate_annual:.2f}%"
        )

        # 提交市价卖单（NautilusTrader 会自动更新持仓状态）
        order = self.order_factory.market(
            instrument_id=self.instrument.id,
            order_side=OrderSide.SELL,
            quantity=reduce_quantity,
        )
        self.submit_order(order)

        # 标记已执行减仓，防止重复触发
        self.euphoria_reduced = True

def _check_time_stop(self, bar: Bar) -> bool:
    """检查时间止损"""
    if not self.config.enable_time_stop or self.entry_bar_count < self.config.time_stop_bars:
        return False
    
    momentum_threshold = 1 + self.config.time_stop_momentum_threshold
    if self.highest_high < self.entry_price * momentum_threshold:
        self.close_all_positions(self.instrument.id)
        self.log.info(
            f"时间止损平仓: bars={self.entry_bar_count}, "
            f"highest={self.highest_high:.2f}, entry={self.entry_price:.2f}"
        )
        self._reset_position_tracking()
        return True
    return False


def _check_chandelier_exit(self, close: float) -> bool:
    """检查Chandelier Exit跟踪止损"""
    if self.atr is None:
        return False
    
    trailing_stop = self.highest_high - (self.config.stop_loss_atr_multiplier * self.atr)
    if close < trailing_stop:
        self.close_all_positions(self.instrument.id)
        self.log.info(
            f"Chandelier Exit 平仓: "
            f"price={close:.2f}, stop={trailing_stop:.2f}, "
            f"highest={self.highest_high:.2f}"
        )
        self._reset_position_tracking()
        return True
    return False


def _check_parabolic_profit(self, close: float) -> bool:
    """检查抛物线止盈"""
    if self.ema is None:
        return False
    
    deviation_pct = (close - self.ema) / self.ema
    if deviation_pct >= self.config.deviation_threshold:
        self.close_all_positions(self.instrument.id)
        self.log.info(
            f"抛物线止盈平仓: price={close:.2f}, ema={self.ema:.2f}, deviation={deviation_pct:.4f}"
        )
        self._reset_position_tracking()
        return True
    return False


def _check_rsi_overbought(self, close: float) -> bool:
    """检查RSI超买止盈"""
    if self.rsi is None or not self.config.enable_rsi_stop_loss:
        return False
    
    if self.rsi > 85 and self.rsi_watcher is False:
        self.rsi_watcher = True
    elif self.rsi_watcher and self.rsi <= 85:
        self.close_all_positions(self.instrument.id)
        self.log.info(
            f"RSI 超买右侧平仓: price={close:.2f}, rsi={self.rsi:.2f}"
        )
        self._reset_position_tracking()
        self.rsi_watcher = False
        return True
    return False


def _update_breakeven_status(self, close: float) -> None:
    """更新保本模式状态"""
    if self.atr is None or self.breakeven_active:
        return
    
    breakeven_trigger_price = self.entry_price + Decimal(self.config.breakeven_multiplier * self.atr)
    if close > breakeven_trigger_price:
        self.breakeven_active = True
        self.log.info(
            f"✅ 保本模式激活: price={close:.2f}, "
            f"trigger={breakeven_trigger_price:.2f}, "
            f"breakeven_stop={self.entry_price * Decimal('1.002'):.2f}"
        )


def _check_breakeven_stop(self, close: float) -> bool:
    """检查保本止损"""
    if not self.breakeven_active:
        return False
    
    breakeven_stop_price = self.entry_price * Decimal("1.002")
    if close < breakeven_stop_price:
        self.close_all_positions(self.instrument.id)
        self.log.info(
            f"🛡️ 保本止损平仓: price={close:.2f}, "
            f"breakeven_stop={breakeven_stop_price:.2f}, "
            f"entry={self.entry_price:.2f}"
        )
        self._reset_position_tracking()
        return True
    return False


def _handle_exit(self, bar: Bar) -> None:
    """处理出场逻辑"""
    close = float(bar.close)
    
    # 1. 时间止损检查（优先）
    if self._check_time_stop(bar):
        return
    
    # 2. 跟踪止损检查（Chandelier Exit）
    if self._check_chandelier_exit(close):
        return
    
    # 3. 抛物线止盈
    if self._check_parabolic_profit(close):
        return
    
    # 4. RSI超买止盈
    if self._check_rsi_overbought(close):
        return
    
    # 5. 保本止损机制
    if self.entry_price is None:
        return
    
    self._update_breakeven_status(close)
    
    if self._check_breakeven_stop(close):
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
