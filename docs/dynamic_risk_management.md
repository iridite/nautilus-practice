# 动态风险管理 (Dynamic Risk Management)

## 概述

Prompt 3 实现了基于市场环境和近期交易表现的动态风险管理系统,旨在通过在不利环境下降低风险敞口来提高策略的生存能力。

## 核心逻辑

### 1. 交易历史追踪

策略现在会追踪最近 N 笔交易的盈亏情况:

```python
# 在 __init__ 中初始化
self.recent_trades: list[float] = []  # 存储最近 N 笔交易的 PnL

# 在 on_position_closed 中记录
def on_position_closed(self, event) -> None:
    pnl = float(position.realized_pnl.as_double())
    self.recent_trades.append(pnl)

    # 只保留最近 N 笔
    if len(self.recent_trades) > self.config.recent_trades_window:
        self.recent_trades.pop(0)
```

### 2. 动态风险计算

`get_dynamic_risk()` 方法根据以下规则调整风险:

#### 规则 1: 连败保护
- **触发条件**: 最近 3 笔交易全部亏损
- **风险调整**: 降至 1% (从默认的 5%)
- **目的**: 在连续亏损期间保护资金,避免雪崩式损失

```python
if len(self.recent_trades) >= 3:
    if all(pnl < 0 for pnl in self.recent_trades):
        return 0.01  # 1% 风险
```

#### 规则 2: 熊市降权
- **触发条件**: 市场状态为 BEAR (ADX > 20 且 CHOP < 61.8 且价格下跌)
- **风险调整**: 减半至 2.5% (5% × 0.5)
- **目的**: 在熊市环境下降低敞口,减少回撤

```python
if market_regime == "BEAR":
    return base_risk * 0.5  # 风险减半
```

#### 规则 3: 正常情况
- **默认风险**: 5% (base_risk_pct)
- **高信念交易**: 7.5% (high_conviction_risk_pct)

### 3. 仓位计算集成

动态风险被集成到 `_calculate_position_size` 和 `_calculate_short_position_size` 方法中:

```python
# 修改前
risk_pct = Decimal(str(
    self.config.high_conviction_risk_pct if high_conviction
    else self.config.base_risk_pct
))

# 修改后
if high_conviction:
    risk_pct = Decimal(str(self.config.high_conviction_risk_pct))
else:
    dynamic_risk = self.get_dynamic_risk()  # 动态计算
    risk_pct = Decimal(str(dynamic_risk))
```

## 配置参数

在 `config/strategies/keltner_rs_breakout.yaml` 中添加了以下参数:

```yaml
# 动态风险管理参数
enable_dynamic_risk: true              # 是否启用动态风险管理
losing_streak_risk_pct: 0.01          # 连败时的风险 (1%)
bear_market_risk_multiplier: 0.5      # 熊市风险倍数 (减半)
recent_trades_window: 3                # 追踪最近 N 笔交易
```

## 预期效果

### 1. 连败保护
- **场景**: 策略连续 3 笔交易亏损
- **效果**: 下一笔交易风险从 5% 降至 1%
- **结果**: 即使继续亏损,损失也被限制在很小的范围内

### 2. 熊市保护
- **场景**: 市场进入熊市状态 (BEAR)
- **效果**: 所有交易风险减半 (5% → 2.5%)
- **结果**: 在不利环境下减少资金暴露,提高生存率

### 3. 组合效应
- **场景**: 熊市 + 连败
- **效果**: 风险降至 1% (连败保护优先级更高)
- **结果**: 极端不利环境下的最大保护

## 实现细节

### 代码修改

1. **配置类** (`KeltnerRSBreakoutConfig`):
   - 添加 4 个新参数

2. **策略初始化** (`__init__`):
   - 添加 `recent_trades` 列表

3. **新增方法**:
   - `on_position_closed()`: 记录交易结果
   - `get_dynamic_risk()`: 计算动态风险

4. **修改方法**:
   - `_calculate_position_size()`: 使用动态风险
   - `_calculate_short_position_size()`: 使用动态风险

### 日志输出

系统会输出详细的日志信息:

```
[Dynamic Risk] Trade closed: PnL=+15.23, Recent 3 trades: [+15.23, -5.12, +8.45]
[Dynamic Risk] Losing streak detected! Recent 3 trades all negative. Risk reduced to 1.0%
[Dynamic Risk] BEAR market detected. Risk reduced: 5.0% → 2.5%
```

## 测试验证

### 单元测试
- 测试连败检测逻辑
- 测试熊市检测逻辑
- 测试风险计算正确性

### 回测验证
- 对比启用/禁用动态风险管理的回测结果
- 验证在熊市期间风险是否正确降低
- 验证连败��间风险是否正确降低

## 注意事项

1. **高信念交易不受影响**:
   - 高信念交易仍使用固定的 7.5% 风险
   - 只有普通交易才应用动态风险调整

2. **连败窗口大小**:
   - 默认为 3 笔交易
   - 可根据策略特性调整 (2-5 笔较合理)

3. **熊市判断依赖市场状态机**:
   - 需要 ADX 和 CHOP 指标正确工作
   - 确保市场状态机参数已优化

4. **禁用选项**:
   - 可通过 `enable_dynamic_risk: false` 禁用
   - 禁用后恢复为固定风险模式

## 与其他功能的协同

### 与市场状态机 (Prompt 1) 的协同
- 市场状态机提供 BULL/BEAR/CHOPPY 分类
- 动态风险管理根据状态调整风险
- CHOPPY 市场已被过滤,不会进入交易

### 与做空模块 (Prompt 2) 的协同
- 做空交易同样受动态风险管理影响
- 熊市中做空风险也会减半
- 连败保护对多空交易一视同仁

## 未来改进方向

1. **更细粒度的风险调整**:
   - 根据连败程度渐进式降低风险
   - 例如: 2 连败 → 3%, 3 连败 → 1%

2. **盈利加速**:
   - 连续盈利时适度增加风险
   - 例如: 3 连胜 → 6% (需谨慎)

3. **波动率自适应**:
   - 根据市场波动率动态调整风险
   - 高波动 → 降低风险, 低波动 → 提高风险

4. **回撤控制**:
   - 当账户回撤超过阈值时降低风险
   - 例如: 回撤 > 10% → 风险减半

## 总结

动态风险管理通过在不利环境下 (熊市、连败) 极度压低风险敞口,显著提高了策略的生存能力,是实现"熊市不亏"目标的关键机制。
