# 魔法数字重构指南

## 已识别的魔法数字

### 高优先级（核心逻辑）

1. **策略参数**
   - 文件: `strategy/core/base.py`, `strategy/keltner_rs_breakout.py`
   - 示例: 
     - `atr_period: int = 14` → `atr_period: int = DEFAULT_ATR_PERIOD`
     - `max_position_risk_pct: float = 0.02` → `max_position_risk_pct: float = DEFAULT_RISK_PER_TRADE`
     - `EMA(20)` → `EMA(DEFAULT_EMA_PERIOD)`
     - `SMA(200)` → `SMA(DEFAULT_SMA_PERIOD)`
   
2. **时间周期**
   - 文件: `strategy/archived/kalman_pairs.py`
   - 示例: 
     - `60 * 1_000_000_000` → `SECONDS_PER_MINUTE * NANOSECONDS_PER_SECOND`

3. **风险参数**
   - 文件: `strategy/core/base.py`
   - 示例: 
     - `qty_percent: Optional[Decimal | float] = None  # e.g., 0.1` → 使用 `MAX_POSITION_SIZE`
     - `stop_loss_pct: float = 0.015` → 使用 `DEFAULT_STOP_LOSS`

4. **相对强度权重**
   - 文件: `strategy/keltner_rs_breakout.py`
   - 示例:
     - `0.4 * RS(5d) + 0.6 * RS(20d)` → `RS_SHORT_WEIGHT * RS(RS_SHORT_PERIOD) + RS_LONG_WEIGHT * RS(RS_LONG_PERIOD)`

### 中优先级（配置相关）

1. **技术指标参数**
   - 文件: `strategy/keltner_rs_breakout.py`
   - 示例: 
     - `2.25*ATR(20)` → `DEFAULT_KELTNER_MULTIPLIER * ATR(DEFAULT_LOOKBACK_PERIOD)`
     - `Volume > 1.5 * SMA(Vol, 20)` → `Volume > DEFAULT_VOLUME_MULTIPLIER * SMA(Vol, DEFAULT_LOOKBACK_PERIOD)`

2. **市场状态阈值**
   - 文件: `strategy/keltner_rs_breakout.py`
   - 示例:
     - `BTC_ATR% < 3%` → `BTC_ATR% < VOLATILITY_THRESHOLD`
     - `time_stop_momentum_threshold: float = 0.01` → `time_stop_momentum_threshold: float = MOMENTUM_THRESHOLD`

3. **交易金额**
   - 文件: `strategy/archived/kalman_pairs.py`
   - 示例:
     - `max_notional_per_trade: float = 10000.0` → 应该从配置文件读取

### 低优先级（辅助功能）

1. **日志格式**
   - 文件: `strategy/core/base.py`
   - 示例: `'=' * 60` → 可以保持，这是格式化字符串

2. **精度设置**
   - 文件: `strategy/keltner_rs_breakout.py`
   - 示例: `TARGET_PRECISION = Decimal("0." + "0" * 16)` → `TARGET_PRECISION = Decimal("0." + "0" * TARGET_PRECISION_DECIMALS)`

## 重构步骤

### 1. 导入常量

```python
from config.constants import (
    SECONDS_PER_MINUTE,
    NANOSECONDS_PER_SECOND,
    DEFAULT_LOOKBACK_PERIOD,
    DEFAULT_ATR_PERIOD,
    DEFAULT_RISK_PER_TRADE,
    MAX_POSITION_SIZE,
    DEFAULT_STOP_LOSS,
    DEFAULT_EMA_PERIOD,
    DEFAULT_SMA_PERIOD,
    DEFAULT_KELTNER_MULTIPLIER,
    DEFAULT_VOLUME_MULTIPLIER,
    RS_SHORT_PERIOD,
    RS_LONG_PERIOD,
    RS_SHORT_WEIGHT,
    RS_LONG_WEIGHT,
    VOLATILITY_THRESHOLD,
    MOMENTUM_THRESHOLD,
    TRADING_DAYS_PER_YEAR,
)
```

### 2. 替换魔法数字

#### 示例 1: strategy/core/base.py

```python
# Before
atr_period: int = 14
max_position_risk_pct: float = 0.02

# After
from config.constants import DEFAULT_ATR_PERIOD, DEFAULT_RISK_PER_TRADE

atr_period: int = DEFAULT_ATR_PERIOD
max_position_risk_pct: float = DEFAULT_RISK_PER_TRADE
```

#### 示例 2: strategy/keltner_rs_breakout.py

```python
# Before
# Entry: Close > EMA(20) + 2.25*ATR(20)
# Filter A: BTC_ATR% < 3%
# Filter D: Volume > 1.5 * SMA(Vol, 20)

# After
from config.constants import (
    DEFAULT_EMA_PERIOD,
    DEFAULT_LOOKBACK_PERIOD,
    DEFAULT_KELTNER_MULTIPLIER,
    DEFAULT_VOLUME_MULTIPLIER,
    VOLATILITY_THRESHOLD,
)

# Entry: Close > EMA(DEFAULT_EMA_PERIOD) + DEFAULT_KELTNER_MULTIPLIER*ATR(DEFAULT_LOOKBACK_PERIOD)
# Filter A: BTC_ATR% < VOLATILITY_THRESHOLD
# Filter D: Volume > DEFAULT_VOLUME_MULTIPLIER * SMA(Vol, DEFAULT_LOOKBACK_PERIOD)
```

#### 示例 3: 相对强度计算

```python
# Before
weighted_rs = 0.4 * rs_5d + 0.6 * rs_20d

# After
from config.constants import RS_SHORT_WEIGHT, RS_LONG_WEIGHT

weighted_rs = RS_SHORT_WEIGHT * rs_5d + RS_LONG_WEIGHT * rs_20d
```

### 3. 添加注释

```python
# 使用默认EMA周期（20根K线）
ema = calculate_ema(data, period=DEFAULT_EMA_PERIOD)

# 使用默认Keltner通道倍数（2.25倍ATR）
upper_band = ema + DEFAULT_KELTNER_MULTIPLIER * atr
```

## 自动化重构脚本

```bash
# 查找并替换常见魔法数字
# ⚠️ 注意: 需要人工审查每个替换

# 示例: 替换ATR周期
find . -name "*.py" -type f -not -path "./.venv/*" -exec sed -i 's/atr_period: int = 14/atr_period: int = DEFAULT_ATR_PERIOD/g' {} \;

# 示例: 替换风险百分比
find . -name "*.py" -type f -not -path "./.venv/*" -exec sed -i 's/max_position_risk_pct: float = 0\.02/max_position_risk_pct: float = DEFAULT_RISK_PER_TRADE/g' {} \;
```

## 验证清单

- [ ] 所有策略参数使用常量
- [ ] 所有时间相关数字使用常量
- [ ] 所有风险参数使用常量
- [ ] 所有技术指标参数使用常量
- [ ] 所有相对强度权重使用常量
- [ ] 所有市场状态阈值使用常量
- [ ] 测试通过
- [ ] 代码审查完成

## 优先级建议

1. **立即重构**: 风险管理参数（`DEFAULT_RISK_PER_TRADE`, `MAX_POSITION_SIZE`, `DEFAULT_STOP_LOSS`）
2. **本周重构**: 技术指标参数（`DEFAULT_ATR_PERIOD`, `DEFAULT_EMA_PERIOD`, `DEFAULT_SMA_PERIOD`）
3. **本月重构**: 相对强度权重和市场状态阈值
4. **长期优化**: 日志格式和辅助功能

## 注意事项

- 重构前先运行测试套件，确保所有测试通过
- 每次重构后重新运行测试，确保行为一致
- 对于策略参数，考虑是否应该从配置文件读取而不是硬编码常量
- 保持向后兼容性，特别是对于已有的策略实例
