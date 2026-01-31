# 仓位计算模式分析

## 重构完成状态

✅ **已完成重构** (2026-01-30)

## 原实现（base.py:416-479）

### 模式1：固定仓位（trade_size）
```python
if self.base_config.trade_size is not None and self.base_config.trade_size > 0:
    return instrument.make_qty(self.base_config.trade_size)
```
- **逻辑**：直接使用配置的固定数量
- **示例**：`trade_size=0.1` → 每次交易 0.1 BTC
- **优点**：简单直接
- **缺点**：不考虑账户规模

### 模式2：动态百分比（qty_percent）
```python
target_notional = equity * self.base_config.qty_percent * leverage
raw_qty = target_notional / price
```
- **逻辑**：`数量 = (权益 × 百分比 × 杠杆) / 价格`
- **示例**：权益10000U，10%，2x杠杆，BTC价格50000 → 0.04 BTC
- **优点**：随账户规模动态调整
- **缺点**：不考虑波动率风险

### 模式3：ATR风险（未使用）
```python
def _calculate_position_size_from_risk(self, equity, atr_value):
    stop_distance = atr_value * atr_stop_multiplier
    max_risk_amount = equity * max_position_risk_pct
    target_qty = max_risk_amount / stop_distance
```
- **逻辑**：基于ATR和风险百分比计算
- **状态**：代码存在但从未被调用
- **问题**：32行代码完全浪费

## 核心问题

### 1. 模式冲突
- 固定仓位和动态百分比是互斥的
- 当前用 if-elif 串联，优先级隐式定义
- 用户可能同时配置两个参数导致困惑

### 2. ATR模式是死代码
- `_calculate_position_size_from_risk` 从未被 `calculate_order_qty` 调用
- 相关配置参数（7个）占用空间但无作用
- 增加理解成本但无实际价值

### 3. 复杂度收益比低
- 64行代码实现2个有效模式 + 1个无效模式
- 实际只需要30行即可实现2个有效模式

## 简化建议

### 方案：保留2个实用模式，删除ATR

```python
def calculate_order_qty(self, price: float | Decimal) -> Quantity:
    price = Decimal(str(price))
    if price <= 0:
        return Quantity.from_int(0)
    
    instrument = self.get_instrument()
    
    # 固定仓位优先
    if self.base_config.trade_size:
        return instrument.make_qty(self.base_config.trade_size)
    
    # 动态百分比
    if self.base_config.qty_percent:
        equity = self._get_equity(instrument)
        if not equity:
            return Quantity.from_int(0)
        
        leverage = min(self.base_config.leverage, 
                      getattr(instrument, 'max_leverage', 999))
        notional = equity * self.base_config.qty_percent * leverage
        qty = notional / price
        
        if instrument.multiplier:
            qty /= Decimal(str(instrument.multiplier))
        
        return instrument.make_qty(qty)
    
    return Quantity.from_int(0)
```

**收益**：
- 从64行减少到30行（减少53%）
- 删除未使用的ATR代码（32行）
- 逻辑更清晰，优先级明确
- 保留所有实际使用的功能

**删除内容**：
- `_calculate_position_size_from_risk` 方法
- `_get_account_equity` 方法（可合并到简化版）
- 7个ATR相关配置参数
- 2个滑点控制参数（未实现）

**配置简化**：
```python
# 删除这些未使用的参数
use_atr_stop: bool = True
atr_period: int = 14
atr_stop_multiplier: float = 2.0
use_atr_position_sizing: bool = True
atr_volatility_target: float = 0.02
max_position_risk_pct: float = 0.1
atr_tp_multiplier: float = 3.0
max_slippage_pct: float = 0.005
enable_slippage_alert: bool = True
```

## 重构结果

### 已实现的改进

1. **废弃模式1（固定仓位）**
   - `trade_size` 参数使用时抛出 ValueError
   - 引导用户使用模式2或模式3

2. **保留模式2（动态百分比）**
   - 功能不变，继续支持

3. **实现模式3（ATR风险仓位）**
   - 新增 `_calculate_atr_qty()` 方法
   - 基于行业标准公式实现
   - 公式: 数量 = (权益 × 风险%) / (ATR × 止损倍数)
   - 添加详细的中文注释和日志

4. **简化配置参数**
   - 删除9个未使用的ATR相关参数
   - 保留3个核心参数: `atr_period`, `atr_stop_multiplier`, `max_position_risk_pct`
   - 新增 `use_atr_position_sizing` 开关

5. **代码精简**
   - 删除 `_get_account_equity()` 方法（32行）
   - 配置参数从17个减少到8个
   - 总体减少约50行代码

### 使用方式

```python
# 模式2: 动态百分比（默认）
config = BaseStrategyConfig(
    qty_percent=Decimal("0.1"),  # 10%
    leverage=2
)
qty = strategy.calculate_order_qty(price=50000)

# 模式3: ATR风险
config = BaseStrategyConfig(
    use_atr_position_sizing=True,
    max_position_risk_pct=0.02,  # 2%风险
    atr_stop_multiplier=2.0,
    leverage=1
)
qty = strategy.calculate_order_qty(price=50000, atr_value=Decimal("100"))
```

## 结论

重构完成，仓位计算模式从3个（1个死代码）优化为2个实用模式，代码更清晰，功能更强大。
