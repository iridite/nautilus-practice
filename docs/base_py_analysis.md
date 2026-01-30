# base.py 分析报告

## 核心功能概览

### 当前结构（650行，3个类）

**1. DataDependency (63行)**
- 数据依赖声明类
- 管理策略所需的数据类型（OHLCV/OI/Funding）

**2. BaseStrategyConfig (120行)**
- 继承自 NautilusTrader 的 StrategyConfig
- 包含：
  - 仓位计算参数（固定/动态百分比）
  - 风险管理参数（止损/杠杆）
  - ATR相关参数（止损/仓位/止盈）
  - 滑点控制
  - 数据依赖管理

**3. BaseStrategy (461行)**
- 继承自 NautilusTrader 的 Strategy
- 核心功能：
  - 仓位计算（固定/动态）
  - 自动止损管理
  - 余额检查
  - 订单提交封装
  - ATR风险管理

---

## 复杂度来源

### 1. 功能过载 ⚠️
- 混合了 3 种不同的仓位计算模式
- ATR 功能（止损/仓位/止盈）但实际未被使用
- 数据依赖系统完整但只做占位检查

### 2. 未使用的代码 🔴
- `_calculate_position_size_from_risk` (32行) - ATR仓位计算
- `_get_account_equity` (29行) - ATR相关
- ATR配置参数（7个）
- 滑点控制参数（2个）

### 3. 过度抽象
- DataDependency 类完整实现但 `_is_dependency_satisfied` 只返回 True
- 6个数据依赖相关方法，实际未产生价值

---

## 简化方案

### 方案A：激进精简（推荐）
**目标：300行以内**

```python
class BaseStrategyConfig(StrategyConfig):
    instrument_id: str
    trade_size: Optional[float] = None  # 固定仓位
    qty_percent: Optional[Decimal] = None  # 动态百分比
    leverage: int = 1
    stop_loss_pct: Optional[float] = None
    use_auto_sl: bool = True

class BaseStrategy(Strategy):
    # 保留核心：
    - 仓位计算（固定/动态二选一）
    - 自动止损
    - 订单提交封装
    
    # 删除：
    - 所有 ATR 相关（未使用）
    - 数据依赖系统（移到 main.py）
    - 滑点控制（未实现）
```

**收益**：
- 代码量减少 50%+
- 清晰的职责边界
- 更易维护和理解

### 方案B：保守优化
**目标：450行**

- 保留 ATR 框架但标记为实验性
- 简化数据依赖为简单列表
- 移除未使用的辅助方法

---

## 建议

**立即行动**：
1. 删除所有 ATR 相关代码（100行+）
2. 将数据依赖检查移到 main.py
3. 删除 `_get_account_equity` 等未使用方法

**核心保留**：
- 仓位计算（2种模式）
- 自动止损
- 余额检查
- 订单提交封装

**结果**：一个清晰、专注的基础策略类，只做它应该做的事。
