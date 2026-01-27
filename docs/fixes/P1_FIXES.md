# P1 修复任务清单

**创建日期**: 2025-01-23
**优先级**: P1 - 重要修复
**状态**: 待修复

---

## 问题清单

### P1-001: 止盈目标逻辑问题

**严重程度**: 🟡 中
**位置**: `strategy/oi_divergence_strategy.py` `_get_tp_target()` (Lines 1133-1142)
**状态**: ⏳ 待修复

**问题描述**:
VWAP 作为止盈目标可能不合理，对于做空交易，止盈条件可能永远无法触发。

**当前代码**:
```python
def _get_tp_target(self) -> Optional[Decimal]:
    if self.config.tp_use_vwap:
        if self.vwap_sma.initialized:
            return Decimal(str(self.vwap_sma.value))  # ⚠️ 可能高于或低于当前价

    if self.midpoint is not None:
        return self.midpoint
    return None
```

**问题场景**:
| 交易方向 | 当前价格 | VWAP值 | 止盈条件 | 结果 |
|---------|---------|--------|---------|------|
| SHORT | 50,000 | 48,000 | price <= 48,000 | ✗ 价格需要跌到48才能止盈（反了！） |
| SHORT | 50,000 | 52,000 | price <= 52,000 | ✓ 价格需要涨到52才能止盈 |
| LONG | 50,000 | 48,000 | price >= 48,000 | ✓ 价格需要涨到48才能止盈 |
| LONG | 50,000 | 52,000 | price >= 52,000 | ✗ 价格需要涨到52才能止盈（VWAP更高更难达到） |

**修复方案**:
1. 使用固定止盈距离（如 2× ATR）
2. 或者使用相对当前价格的比例止盈
3. 或者基于阻力/支撑位设置止盈目标

---

### P1-002: 代码重复严重

**严重程度**: 🟡 中
**位置**: 
- `_execute_short_entry()` (Lines 941-1024)
- `_execute_long_entry()` (Lines 1026-1127)
**状态**: ⏳ 待修复

**问题描述**:
两个入场执行方法有约 80 行代码，结构几乎相同，仅订单方向相反。

**代码重复率**: ~70%

**重复代码示例**:
```python
# _execute_short_entry
positions = self.cache.positions_open(instrument_id=self.instrument_id)
if len(positions) >= self.config.max_positions:
    return

if self.config.use_atr_position_sizing and self.atr and self.atr.initialized:
    raw_qty = self._calculate_atr_adjusted_qty(current_price, OrderSide.SELL)
    qty = self.instrument.make_qty(raw_qty)
else:
    qty = self.calculate_order_qty(current_price)

if qty <= 0:
    return

self.expected_entry_price = current_price
order = self.order_factory.market(...)
self.submit_order_safe(order, reason=...)

# 🔥 Risk: 提交止损订单
self._submit_stop_loss_order(OrderSide.SELL, qty)

# 更新状态
self.entry_bar_count = 0
self.entry_price = current_price
self._strategy_state = StrategyState.POSITION_OPEN
```

```python
# _execute_long_entry (几乎完全相同)
positions = self.cache.positions_open(instrument_id=self.instrument_id)
if len(positions) >= self.config.max_positions:
    return

if self.config.use_atr_position_sizing and self.atr and self.atr.initialized:
    raw_qty = self._calculate_atr_adjusted_qty(current_price, OrderSide.BUY)
    qty = self.instrument.make_qty(raw_qty)
else:
    qty = self.calculate_order_qty(current_price)

if qty <= 0:
    return

self.expected_entry_price = current_price
order = self.order_factory.market(...)
self.submit_order_safe(order, reason=...)

# 🔥 Risk: 提交止损订单
self._submit_stop_loss_order(OrderSide.BUY, qty)

# 更新状态
self.entry_bar_count = 0
self.entry_price = current_price
self._strategy_state = StrategyState.POSITION_OPEN
```

**差异点**:
| 部分 | SHORT | LONG | 处理方式 |
|-----|-------|------|----------|
| max_positions 检查 | ✓ | ✓ | 相同 |
| 仓位计算 | `OrderSide.SELL` | `OrderSide.BUY` | 传入参数 |
| 订单创建 | `OrderSide.SELL` | `OrderSide.BUY` | 传入参数 |
| 止损订单 | `OrderSide.SELL` | `OrderSide.BUY` | 传入参数 |
| 日志输出 | SHORT 相关信息 | LONG 相关信息 | 格式化差异 |

**修复方案**:
1. 重构为通用的 `_execute_entry()` 方法
2. 通过参数控制方向和日志内容
3. 减少约 60 行重复代码

---

### P1-003: 资金费率过滤逻辑注释不足

**严重程度**: 🟢 低
**位置**: `_detect_short_signal()` 和 `_detect_long_signal()` (Lines 657-801)
**状态**: ⏳ 待修复

**问题描述**:
资金费率与市场情绪的关系没有详细注释，新开发者难以理解过滤逻辑。

**当前代码**:
```python
# 做空信号
if self.current_funding_rate_annual <= self.config.funding_rate_threshold_annual:
    # 做空允许的资金费率条件

# 做多信号
if self.current_funding_rate_annual >= -self.config.funding_rate_threshold_annual:
    # 做多允许的资金费率条件
```

**修复方案**:
添加详细注释解释资金费率与市场情绪的关系。

---

## 修复验证方法

```bash
# 运行回测验证修复
uv run python main.py backtest --skip-oi-data

# 运行单元测试
uv run python -m unittest tests.test_oi_divergence -v
```

---

## 修复记录

| 问题ID | 修复人 | 修复日期 | 验证结果 |
|--------|--------|----------|----------|
| P1-001 | - | - | ⏳ 待修复 |
| P1-002 | - | - | ⏳ 待修复 |
| P1-003 | - | - | ⏳ 待修复 |

---

## 修复后验证清单

- [ ] P1-001: 止盈目标逻辑正确
- [ ] P1-002: 代码重复减少 50% 以上
- [ ] P1-003: 资金费率注释添加
- [ ] 回测能正常执行
- [ ] 无新增错误日志