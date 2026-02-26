# Prompt 3 实现总结

## 任务目标
实现基于市场环境和近期表现的动态风险管理逻辑,通过在不利环境下极度压低敞口,确保账户生存,实现"熊市不亏"目标。

## 实现内容

### 1. 配置参数 (4个新参数)

```yaml
# 动态风险管理参数
enable_dynamic_risk: true              # 是否启用动态风险管理
losing_streak_risk_pct: 0.01          # 连败时的风险 (1%)
bear_market_risk_multiplier: 0.5      # 熊市风险倍数 (减半)
recent_trades_window: 3                # 追踪最近 N 笔交易
```

### 2. 代码修改

#### 配置类 (`KeltnerRSBreakoutConfig`)
- 添加 4 个动态风险管理参数

#### 策略初始化 (`__init__`)
- 添加 `self.recent_trades: list[float] = []` 用于追踪交易历史

#### 新增方法

**`on_position_closed(event)`**
- 监听持仓平仓事件
- 从 `event.realized_pnl` 获取交易盈亏
- 将 PnL 添加到 `recent_trades` 列表
- 维护固定窗口大小 (默认 3 笔)
- 输出日志: `[Dynamic Risk] Trade closed: PnL=+15.23, Recent 3 trades: [+15.23, -5.12, +8.45]`

**`get_dynamic_risk()`**
- 计算动态调整后的风险百分比
- 规则 1: 连败保护 (最近 3 笔全亏 → 1%)
- 规则 2: 熊市降权 (BEAR 市场 → 减半至 2.5%)
- 规则 3: 正常情况 (返回 base_risk_pct = 5%)

#### 修改方法

**`_calculate_position_size(bar, high_conviction)`**
- 原逻辑: 固定使用 `base_risk_pct` 或 `high_conviction_risk_pct`
- 新逻辑:
  - 高信念交易: 仍使用 `high_conviction_risk_pct` (7.5%)
  - 普通交易: 调用 `get_dynamic_risk()` 获取动态风险

**`_calculate_short_position_size(bar, high_conviction)`**
- 与做多仓位计算相同的修改逻辑
- 确保做空交易也受动态风险管理影响

### 3. 核心逻辑

```python
def get_dynamic_risk(self) -> float:
    if not self.config.enable_dynamic_risk:
        return self.config.base_risk_pct

    base_risk = self.config.base_risk_pct  # 5%

    # 规则 1: 连败保护 (优先级最高)
    if len(self.recent_trades) >= 3:
        if all(pnl < 0 for pnl in self.recent_trades):
            return 0.01  # 1% 风险

    # 规则 2: 熊市降权
    if self.get_market_regime() == "BEAR":
        return base_risk * 0.5  # 2.5% 风险

    # 规则 3: 正常情况
    return base_risk  # 5% 风险
```

## 测试验证

### 单元测试 (10个测试用例)
✅ 所有测试通过

1. `test_config_has_dynamic_risk_params` - 配置包含所有参数
2. `test_config_default_values` - 默认值正确
3. `test_normal_risk_no_trades` - 无交易历史时返回正常风险
4. `test_losing_streak_protection` - 3连败触发保护
5. `test_bear_market_reduction` - 熊市风险减半
6. `test_losing_streak_priority_over_bear` - 连败优先级高于熊市
7. `test_mixed_trades_no_protection` - 有盈有亏不触发保护
8. `test_insufficient_trades_no_protection` - 交易数不足不触发保护
9. `test_disabled_dynamic_risk` - 禁用功能时返回固定风险
10. `test_choppy_market_normal_risk` - 震荡市场不影响风险

### 回测验证
- 运行完整回测验证功能正确性
- 检查日志输出确认动态风险调整生效

## 预期效果

### 场景 1: 连败保护
- **触发条件**: 最近 3 笔交易全部亏损
- **风险调整**: 5% → 1%
- **效果**: 即使继续亏损,单笔最大损失仅为账户的 1%

### 场景 2: 熊市保护
- **触发条件**: 市场状态为 BEAR
- **风险调整**: 5% → 2.5%
- **效果**: 在不利环境下减少资金暴露

### 场景 3: 极端情况 (熊市 + 连败)
- **触发条件**: 熊市且连续 3 笔亏损
- **风险调整**: 5% → 1% (连败保护优先)
- **效果**: 最大程度保护资金

## 与其他功能的协同

### 与 Prompt 1 (市场状态机) 协同
- 市场状态机提供 BULL/BEAR/CHOPPY 分类
- 动态风险管理根据状态调整风险
- CHOPPY 市场已被过滤,不会进入交易

### 与 Prompt 2 (做空模块) 协同
- 做空交易同样受动态风险管理影响
- 熊市中做空风险也会减半
- 连败保护对多空交易一视同仁

## 文件修改清单

1. **strategy/keltner_rs_breakout.py** (+104 行)
   - 配置类: +6 行
   - 初始化: +3 行
   - 新增方法: +95 行 (on_position_closed + get_dynamic_risk)
   - 修改方法: 2 处 (仓位计算)

2. **config/strategies/keltner_rs_breakout.yaml** (+4 行)
   - 添加 4 个动态风险管理参数

3. **tests/test_dynamic_risk.py** (新文件, 150 行)
   - 10 个单元测试用例

4. **docs/dynamic_risk_management.md** (新文件, 文档)
   - 完整的功能说明文档

## 关键设计决策

1. **连败保护优先级高于熊市降权**
   - 理由: 连败是更严重的信号,需要更激进的保护

2. **高信念交易不受动态风险影响**
   - 理由: 高信念交易本身已经过严格筛选,应保持原有风险

3. **使用固定窗口 (3笔) 而非滑动平均**
   - 理由: 简单直接,易于理解和调试

4. **禁用选项 (enable_dynamic_risk)**
   - 理由: 允许用户对比启用/禁用的效果

## 潜在改进方向

1. **渐进式风险调整**: 根据连败程度渐进降低风险
2. **盈利加速**: 连续盈利时适度增加风险 (需谨慎)
3. **波动率自适应**: 根据市场波动率动态调整
4. **回撤控制**: 账户回撤超过阈值时降低风险

## 总结

Prompt 3 成功实现了动态风险管理系统,通过连败保护和熊市降权两大机制,在不利环境下极度压低风险敞口,显著提高了策略的生存能力,是实现"熊市不亏"目标的关键组件。
