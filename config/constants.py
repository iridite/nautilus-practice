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
DEFAULT_KELTNER_MULTIPLIER = 2.25  # Keltner通道倍数
DEFAULT_VOLUME_MULTIPLIER = 1.5    # 成交量倍数

# 相对强度常量
RS_SHORT_PERIOD = 5            # 短期RS周期
RS_LONG_PERIOD = 20            # 长期RS周期
RS_SHORT_WEIGHT = 0.4          # 短期RS权重
RS_LONG_WEIGHT = 0.6           # 长期RS权重

# 市场状态常量
VOLATILITY_THRESHOLD = 0.03    # 波动率阈值 3%
MOMENTUM_THRESHOLD = 0.01      # 动能阈值 1%

# 精度常量
TARGET_PRECISION_DECIMALS = 16  # 目标精度小数位数
