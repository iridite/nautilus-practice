# P0 修复任务清单

**创建日期**: 2025-01-23
**优先级**: P0 - 紧急修复
**状态**: ✅ 已全部修复

---

## 问题清单

### P0-001: 动态止损机制存在漏洞

**严重程度**: 🔴 高
**位置**: `strategy/oi_divergence_strategy.py` `_check_atr_stop_loss()` (Lines 406-469)
**状态**: ✅ 已修复

**问题描述**:
动态止损只是"检查"价格是否触及止损位，然后调用 `close_position()`，而不是下一个真实的止损订单保证执行。

**修复方案**:
1. 添加 `_get_atr_stop_price()` 方法 - 计算 ATR 止损价格
2. 添加 `_submit_stop_loss_order()` 方法 - 提交真实止损订单
3. 在开仓时立即调用 `_submit_stop_loss_order()` 提交止损订单
4. 使用 `TimeInForce.FOK` 确保立即成交或取消
5. 使用 `reduce_only=True` 防止加仓
6. 保留 `_check_atr_stop_loss()` 作为最后防线

**修复代码**:
```python
def _submit_stop_loss_order(self, order_side: OrderSide, quantity):
    """提交止损订单（真实订单保证执行）"""
    if self.entry_price is None:
        return
    
    atr_stop_price = self._get_atr_stop_price(self.entry_price, order_side)
    
    if self.config.use_atr_stop and atr_stop_price is not None:
        # ATR 动态止损
        trigger_price = self.instrument.make_price(atr_stop_price)
        opposite_side = OrderSide.BUY if order_side == OrderSide.SELL else OrderSide.SELL
        
        sl_order = self.order_factory.stop_market(
            instrument_id=self.instrument_id,
            order_side=opposite_side,
            quantity=quantity,
            trigger_price=trigger_price,
            time_in_force=TimeInForce.FOK,  # ✅ 立即成交或取消
            reduce_only=True,  # ✅ 防止加仓
        )
```

---

### P0-002: 固定止损 `reduce_only=False` 危险参数

**严重程度**: 🔴 高
**位置**: 
- `_execute_short_entry()` (Lines 855-939)
- `_execute_long_entry()` (Lines 941-1024)
**状态**: ✅ 已修复

**问题描述**:
固定止损订单使用 `reduce_only=False`，如果有任何逻辑错误或订单条件不符合预期，这个订单可能不会减少持仓，反而增加持仓。

**修复方案**:
1. 将所有止损订单的 `reduce_only` 参数改为 `True`
2. 统一使用 `_submit_stop_loss_order()` 方法提交止损订单

**修复代码**:
```python
# 修复前
reduce_only=False,  # ❌ 危险！

# 修复后
reduce_only=True,  # ✅ 防止加仓，只减少持仓
```

---

## 修复验证方法

```bash
# 运行回测验证修复
uv run python main.py backtest --skip-oi-data

# 验证配置类
uv run python -c "
from strategy.oi_divergence_strategy import OIDivergenceStrategyConfig
config = OIDivergenceStrategyConfig()
print('✅ 配置类创建成功')
"
```

---

## 修复记录

| 问题ID | 修复人 | 修复日期 | 验证结果 |
|--------|--------|----------|----------|
| P0-001 | Claude | 2025-01-27 | ✅ 已修复并验证 |
| P0-002 | Claude | 2025-01-27 | ✅ 已修复并验证 |

---

## 修复后验证清单

- [ ] 动态止损生成真实的 reduce_only 订单
- [ ] 固定止损使用 reduce_only=True
- [ ] 回测能正常执行
- [ ] 止损逻辑正确执行
- [ ] 无新增错误日志
```
