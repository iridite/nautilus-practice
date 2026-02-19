# Strategy 模块 API 文档

本文档详细说明 `strategy/` 模块的 API 接口，包括基类、配置和核心方法。

## 目录

- [BaseStrategyConfig](#basestrategyconfiguration)
- [BaseStrategy](#basestrategy)
- [策略开发指南](#策略开发指南)

---

## BaseStrategyConfig

策略配置基类，所有策略配置都应继承此类。

### 类定义

```python
from strategy.core.base import BaseStrategyConfig

class BaseStrategyConfig(StrategyConfig):
    """策略配置基类"""
```

### 配置字段

#### 基础配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `oms_type` | `str` | `"NETTING"` | 持仓模式：NETTING（净持仓）或 HEDGING（对冲持仓） |
| `symbol` | `str` | `""` | 简化标的名称，如 "ETHUSDT" |
| `timeframe` | `str` | `""` | 时间框架，如 "1d", "1h", "15m" |
| `price_type` | `str` | `"LAST"` | 价格类型：LAST, MID, BID, ASK |
| `origination` | `str` | `"EXTERNAL"` | 数据来源：EXTERNAL, INTERNAL |
| `instrument_id` | `str` | `""` | 完整标的ID（自动生成） |
| `bar_type` | `str` | `""` | 完整bar类型（自动生成） |

#### 仓位管理

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `qty_percent` | `Decimal \| float \| None` | `None` | 动态百分比模式：账户权益的百分比 |
| `use_atr_position_sizing` | `bool` | `False` | 启用 ATR 风险仓位计算 |
| `leverage` | `int` | `1` | 杠杆倍数 |
| `max_positions` | `int` | `1` | 最大并发持仓数 |

#### 风险管理

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `stop_loss_pct` | `float \| None` | `None` | 止损百分比（如 0.015 表示 1.5%） |
| `use_auto_sl` | `bool` | `True` | 启用自动止损管理 |
| `atr_period` | `int` | `20` | ATR 计算周期 |
| `atr_stop_multiplier` | `float` | `2.0` | ATR 止损倍数 |
| `max_position_risk_pct` | `float` | `0.02` | 单笔交易最大风险百分比 |

### 使用示例

```python
from strategy.core.base import BaseStrategyConfig

class MyStrategyConfig(BaseStrategyConfig):
    """自定义策略配置"""
    
    # 简化配置（推荐）
    symbol: str = "BTCUSDT"
    timeframe: str = "1h"
    
    # 仓位管理
    qty_percent: float = 0.1  # 使用 10% 账户权益
    leverage: int = 2
    
    # 策略特定参数
    lookback_period: int = 20
    entry_threshold: float = 0.05
```

---

## BaseStrategy

策略基类，提供统一的策略开发接口。

### 类定义

```python
from strategy.core.base import BaseStrategy

class BaseStrategy(Strategy):
    """策略基类"""
```

### 核心方法

#### `__init__(config: BaseStrategyConfig)`

初始化策略实例。

**参数**:
- `config`: 策略配置对象

**示例**:
```python
class MyStrategy(BaseStrategy):
    def __init__(self, config: MyStrategyConfig):
        super().__init__(config)
        self.lookback_period = config.lookback_period
```

#### `on_start()`

策略启动时的生命周期钩子。子类必须调用 `super().on_start()` 以确保 instrument 正确加载。

**示例**:
```python
def on_start(self):
    super().on_start()
    self.log.info("策略启动")
    
    # 订阅数据
    bar_type = BarType.from_str(self.config.bar_type)
    self.subscribe_bars(bar_type)
```

#### `on_bar(bar: Bar)`

处理 Bar 数据的生命周期钩子。子类必须调用 `super().on_bar(bar)` 以启用自动风险管理。

**参数**:
- `bar`: Bar 数据对象

**示例**:
```python
def on_bar(self, bar: Bar):
    super().on_bar(bar)  # 必须调用
    
    # 策略逻辑
    close = float(bar.close)
    if close > self.upper_band:
        self._handle_entry(bar)
```

#### `on_data(data: CustomData)`

处理自定义数据（如 OI、Funding Rate）。

**参数**:
- `data`: 自定义数据对象

**示例**:
```python
def on_data(self, data: CustomData):
    if isinstance(data, FundingRateData):
        self.current_funding_rate = float(data.funding_rate)
```

#### `calculate_order_qty(price: float | Decimal, atr_value: Optional[Decimal] = None) -> Quantity`

计算下单数量（仓位大小）。

**参数**:
- `price`: 当前市场价格
- `atr_value`: ATR 值（用于 ATR 风险模式）

**返回**:
- `Quantity`: 计算得到的下单数量

**计算模式**:

1. **动态百分比模式** (`qty_percent` 设置时):
   ```
   数量 = (账户权益 × 百分比 × 杠杆) / 价格
   ```

2. **ATR 风险模式** (`use_atr_position_sizing=True` 时):
   ```
   止损距离 = ATR × 止损倍数
   风险金额 = 账户权益 × 风险百分比
   数量 = 风险金额 / 止损距离
   ```

**示例**:
```python
# 动态百分比模式
qty = self.calculate_order_qty(bar.close)

# ATR 风险模式
qty = self.calculate_order_qty(bar.close, atr_value=Decimal(str(self.atr)))
```

#### `submit_order_safe(order: Order, reason: str = "")`

安全提交订单，包含验证和日志记录。

**参数**:
- `order`: 订单对象
- `reason`: 下单原因（用于日志）

**示例**:
```python
order = self.order_factory.market(
    instrument_id=self.instrument.id,
    order_side=OrderSide.BUY,
    quantity=qty,
)
self.submit_order_safe(order, "突破上��做多")
```

#### `close_all_positions(instrument_id: InstrumentId)`

平掉指定标的的所有持仓。

**参数**:
- `instrument_id`: 标的 ID

**示例**:
```python
self.close_all_positions(self.instrument.id)
self.log.info("止损平仓")
```

---

## 策略开发指南

### 基本结构

```python
from strategy.core.base import BaseStrategy, BaseStrategyConfig
from nautilus_trader.model.data import Bar

class MyStrategyConfig(BaseStrategyConfig):
    """策略配置"""
    symbol: str = "BTCUSDT"
    timeframe: str = "1h"
    qty_percent: float = 0.1
    
    # 策略参数
    lookback_period: int = 20
    entry_threshold: float = 0.05

class MyStrategy(BaseStrategy):
    """自定义策略"""
    
    def __init__(self, config: MyStrategyConfig):
        super().__init__(config)
        self.lookback_period = config.lookback_period
        self.entry_threshold = config.entry_threshold
        
        # 初始化指标
        self.closes = []
        self.sma = None
    
    def on_start(self):
        """策略启动"""
        super().on_start()
        self.log.info(f"策略启动: lookback={self.lookback_period}")
        
        # 订阅数据
        bar_type = BarType.from_str(self.config.bar_type)
        self.subscribe_bars(bar_type)
    
    def on_bar(self, bar: Bar):
        """处理 Bar 数据"""
        super().on_bar(bar)  # 必须调用
        
        # 更新指标
        self.closes.append(float(bar.close))
        if len(self.closes) > self.lookback_period:
            self.closes.pop(0)
        
        if len(self.closes) < self.lookback_period:
            return
        
        self.sma = sum(self.closes) / len(self.closes)
        
        # 交易逻辑
        close = float(bar.close)
        
        # 入场条件
        if not self.portfolio.is_net_long(self.instrument.id):
            if close > self.sma * (1 + self.entry_threshold):
                qty = self.calculate_order_qty(bar.close)
                if qty and qty > 0:
                    order = self.order_factory.market(
                        instrument_id=self.instrument.id,
                        order_side=OrderSide.BUY,
                        quantity=qty,
                    )
                    self.submit_order_safe(order, "突破均线做多")
        
        # 出场条件
        else:
            if close < self.sma:
                self.close_all_positions(self.instrument.id)
                self.log.info("跌破均线平仓")
```

### 最佳实践

1. **始终调用父类方法**
   ```python
   def on_start(self):
       super().on_start()  # 必须
       # 你的代码
   
   def on_bar(self, bar: Bar):
       super().on_bar(bar)  # 必须
       # 你的代码
   ```

2. **使用 Decimal 进行金融计算**
   ```python
   from decimal import Decimal
   
   entry_price = Decimal(str(bar.close))
   stop_price = entry_price * Decimal("0.98")
   ```

3. **检查持仓状态**
   ```python
   if self.portfolio.is_net_long(self.instrument.id):
       # 已有多头持仓
   elif self.portfolio.is_net_short(self.instrument.id):
       # 已有空头持仓
   else:
       # 无持仓
   ```

4. **验证数量有效性**
   ```python
   qty = self.calculate_order_qty(bar.close)
   if qty and qty > 0:
       # 提交订单
   ```

5. **使用日志记录关键信息**
   ```python
   self.log.info(f"开仓: price={close:.2f}, qty={qty}")
   self.log.warning(f"余额不足")
   self.log.error(f"订单被拒绝: {reason}")
   ```

### 常见模式

#### 指标计算

```python
from collections import deque

class MyStrategy(BaseStrategy):
    def __init__(self, config):
        super().__init__(config)
        self.closes = deque(maxlen=20)
        self.ema = None
    
    def _update_indicators(self):
        if len(self.closes) >= 20:
            if self.ema is None:
                self.ema = sum(self.closes) / len(self.closes)
            else:
                alpha = 2.0 / (20 + 1)
                self.ema = alpha * self.closes[-1] + (1 - alpha) * self.ema
```

#### 持仓跟踪

```python
class MyStrategy(BaseStrategy):
    def __init__(self, config):
        super().__init__(config)
        self.entry_price = None
        self.highest_high = None
    
    def _handle_entry(self, bar):
        qty = self.calculate_order_qty(bar.close)
        if qty and qty > 0:
            order = self.order_factory.market(
                instrument_id=self.instrument.id,
                order_side=OrderSide.BUY,
                quantity=qty,
            )
            self.submit_order_safe(order)
            
            # 记录持仓信息
            self.entry_price = Decimal(str(bar.close))
            self.highest_high = float(bar.high)
    
    def _handle_exit(self, bar):
        # 更新最高价
        self.highest_high = max(self.highest_high, float(bar.high))
        
        # 跟踪止损
        trailing_stop = self.highest_high * 0.95
        if float(bar.close) < trailing_stop:
            self.close_all_positions(self.instrument.id)
            self._reset_position_tracking()
    
    def _reset_position_tracking(self):
        self.entry_price = None
        self.highest_high = None
```

---

## 参考资料

- [NautilusTrader 官方文档](https://nautilustrader.io/)
- [Keltner RS Breakout 策略示例](../guides/keltner-rs-breakout.md)
- [Dual Thrust 策略示例](../guides/dual-thrust.md)

---

**最后更新**: 2026-02-19
