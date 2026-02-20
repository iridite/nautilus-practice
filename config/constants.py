"""
项目常量配置
用于替代代码中的魔法数字
"""

# 时间相关常量（秒）
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
SECONDS_PER_DAY = 86400
MILLISECONDS_PER_SECOND = 1000
NANOSECONDS_PER_SECOND = 1_000_000_000

# 数据相关常量
DEFAULT_LOOKBACK_PERIOD = 20  # K线回看周期
DEFAULT_WARMUP_PERIOD = 100   # 策略预热周期
MAX_BARS_TO_LOAD = 10000      # 最大加载K线数
TRADING_DAYS_PER_YEAR = 252   # 年化交易日

# 风险管理常量
DEFAULT_RISK_PER_TRADE = 0.02  # 单笔风险 2%
MAX_POSITION_SIZE = 0.1        # 最大仓位 10%
DEFAULT_STOP_LOSS = 0.02       # 默认止损 2%
DEFAULT_ATR_PERIOD = 14        # ATR计算周期
DEFAULT_ATR_MULTIPLIER = 2.0   # ATR止损倍数

# 回测相关常量
DEFAULT_COMMISSION = 0.0002    # 默认手续费 0.02%
DEFAULT_SLIPPAGE = 0.0001      # 默认滑点 0.01%

# API 相关常量
API_TIMEOUT = 30               # API 超时时间（秒）
MAX_RETRIES = 3                # 最大重试次数
RETRY_DELAY = 5                # 重试延迟（秒）

# 数据验证常量
MIN_PRICE = 0.0001             # 最小价格
MAX_PRICE = 1000000            # 最大价格
MIN_VOLUME = 0                 # 最小成交量

# 日志相关常量
LOG_ROTATION_SIZE = 100 * 1024 * 1024  # 100MB
LOG_RETENTION_DAYS = 7         # 日志保留天数

# 技术指标常量
DEFAULT_EMA_PERIOD = 20        # EMA默认周期
DEFAULT_SMA_PERIOD = 200       # SMA默认周期（长期趋势）
DEFAULT_ATR_PERIOD_LONG = 20   # ATR长周期（用于Keltner通道）
DEFAULT_BB_PERIOD = 20         # 布林带周期
DEFAULT_BB_STD = 2.0           # 布林带标准差倍数
DEFAULT_RSI_PERIOD = 14        # RSI周期

# Keltner通道常量
DEFAULT_KELTNER_BASE_MULTIPLIER = 1.5    # Keltner基础通道倍数（Squeeze判定）
DEFAULT_KELTNER_TRIGGER_MULTIPLIER = 2.25  # Keltner触发通道倍数（入场信号）
DEFAULT_VOLUME_MULTIPLIER = 1.5          # 成交量倍数（放量过滤）

# 相对强度常量
RS_SHORT_PERIOD = 5            # 短期RS周期（天）
RS_LONG_PERIOD = 20            # 长期RS周期（天）
RS_SHORT_WEIGHT = 0.4          # 短期RS权重
RS_LONG_WEIGHT = 0.6           # 长期RS权重
RS_THRESHOLD = 0.0             # RS阈值（>0表示强于BTC）

# 风险管理常量（策略特定）
BASE_RISK_PCT = 0.01           # 基础风险百分比 1%
HIGH_CONVICTION_RISK_PCT = 0.015  # 高确信度风险百分比 1.5%
STOP_LOSS_ATR_MULTIPLIER = 2.0    # 止损ATR倍数
BREAKEVEN_MULTIPLIER = 1.0        # 保本触发ATR倍率
MIN_STOP_DISTANCE_PCT = 0.005     # 最小止损距离 0.5%

# 出场管理常量
TIME_STOP_BARS = 3             # 时间止损K线数
MOMENTUM_THRESHOLD = 0.01      # 动能确认阈值 1%
DEVIATION_THRESHOLD = 0.40     # 抛物线止盈乖离阈值 40%
MAX_UPPER_WICK_RATIO = 0.3     # K线最大上影线比例 30%

# BTC市场状态过滤器常量
BTC_REGIME_SMA_PERIOD = 200    # BTC趋势判定周期
BTC_REGIME_ATR_PERIOD = 14     # BTC波动率计算周期
VOLATILITY_THRESHOLD = 0.03    # BTC ATR百分比阈值 3%

# 市场狂热度过滤器常量
FUNDING_RATE_WARNING_ANNUAL = 100.0   # 资金费率警告阈值（年化%）
FUNDING_RATE_DANGER_ANNUAL = 200.0    # 资金费率危险阈值（年化%）
BTC_DOMINANCE_CHANGE_THRESHOLD = 5.0  # BTC Dominance变化阈值 5%
BTC_DOMINANCE_LOOKBACK_DAYS = 7       # BTC Dominance回溯天数
EUPHORIA_REDUCE_POSITION_PCT = 0.5    # 狂热状态减仓比例 50%

# Squeeze记忆常量
SQUEEZE_MEMORY_DAYS = 3        # Squeeze状态记忆天数

# EMA计算常量
EMA_ALPHA_NUMERATOR = 2.0      # EMA平滑系数分子
EMA_ALPHA_DENOMINATOR_OFFSET = 1  # EMA平滑系数分母偏移

# ATR计算常量（Wilder's Smoothing）
ATR_ALPHA_NUMERATOR = 1.0      # ATR平滑系数分子

# 历史数据常量
MAX_HISTORY_SIZE = 100         # 历史数据最大保存数量

# 精度常量
TARGET_PRECISION_DECIMALS = 16  # 目标精度小数位数
