# Strategy Implementations / 策略实现

本目录包含所有交易策略的实现代码。

## 📁 目录结构

```
strategy/
├── base.py                        # 基础策略类和配置
├── oi_divergence_strategy.py     # OI Divergence 策略 (主策略)
└── archived/                      # 归档策略 (参考用途)
    ├── README.md
    ├── dual_thrust.py
    └── rs_squeeze.py
```

## 🚀 活跃策略

### OI Divergence Strategy (推荐使用)

**文件**: `oi_divergence_strategy.py`  
**版本**: Risk-Enhanced v3.0  
**状态**: ✅ 活跃维护

**核心功能**:
- 持仓量 (Open Interest) 背离检测
- 资金费率 (Funding Rate) 过滤
- 价格突破确认
- ATR 动态止损
- ATR 动态仓位管理
- 滑点监控和告警

**适用场景**:
- 永续合约交易
- 中短期交易 (1H-4H)
- 趋势跟随 + 反转捕捉

**配置示例**:
```yaml
# config/strategies/oi_divergence.yaml
name: "OIDivergenceStrategy"
module_path: "strategy.oi_divergence_strategy"
config_class: "OIDivergenceStrategyConfig"
parameters:
  lookback_bars: 48
  oi_decline_threshold: 0.05
  use_atr_stop: true
  atr_stop_multiplier: 2.0
```

**相关文档**:
- [策略概念说明](../docs/strategies/oi_divergence/concept.md)
- [数据使用指南](../docs/strategies/oi_divergence/data_usage.md)
- [实现细节](../docs/strategies/oi_divergence/implementation.md)

---

## 🏗️ 基础架构

### BaseStrategy 基类

**文件**: `base.py`

所有策略都应继承 `BaseStrategy` 基类，自动获得：

- ✅ 统一的配置管理 (`BaseStrategyConfig`)
- ✅ 安全的下单逻辑 (`submit_order_safe`)
- ✅ 标准化的仓位计算 (`calculate_order_qty`)
- ✅ 自动的标的加载 (`on_start`)
- ✅ 数据依赖声明系统

**基本用法**:
```python
from strategy.base import BaseStrategy, BaseStrategyConfig

class MyStrategyConfig(BaseStrategyConfig):
    # 策略特定参数
    my_parameter: int = 100

class MyStrategy(BaseStrategy):
    def __init__(self, config: MyStrategyConfig):
        super().__init__(config)
        # 初始化策略
    
    def on_start(self):
        super().on_start()
        # 订阅数据
    
    def on_bar(self, bar):
        super().on_bar(bar)
        # 处理 K 线数据
```

---

## 📦 归档策略

已过时或不再维护的策略移至 `archived/` 目录，仅供参考学习。

**查看归档策略**: [archived/README.md](./archived/README.md)

**归档策略列表**:
- `dual_thrust.py` - Dual Thrust 突破策略
- `rs_squeeze.py` - 相对强度挤压策略

⚠️ **不推荐在生产环境使用归档策略**，它们缺少现代风控机制且不再维护。

---

## 🛠️ 开发新策略

### 开发步骤

1. **继承基类**
   ```python
   from strategy.base import BaseStrategy, BaseStrategyConfig
   ```

2. **定义配置类**
   ```python
   class MyStrategyConfig(BaseStrategyConfig):
       # 继承通用参数: trade_size, qty_percent, leverage, stop_loss_pct
       
       # 添加策略特定参数
       my_param: int = 100
       my_threshold: float = 0.05
   ```

3. **实现策略逻辑**
   ```python
   class MyStrategy(BaseStrategy):
       def on_start(self):
           super().on_start()
           # 订阅数据
           self.subscribe_bars(self.bar_type)
       
       def on_bar(self, bar):
           super().on_bar(bar)
           # 策略逻辑
   ```

4. **创建配置文件**
   ```yaml
   # config/strategies/my_strategy.yaml
   name: "MyStrategy"
   module_path: "strategy.my_strategy"
   config_class: "MyStrategyConfig"
   parameters:
     my_param: 100
     my_threshold: 0.05
   ```

5. **运行回测**
   ```bash
   # 修改 config/active.yaml
   strategy: "my_strategy"
   
   # 运行回测
   uv run python main.py backtest
   ```

### 最佳实践

✅ **必须遵循**:
- 继承 `BaseStrategy` 和 `BaseStrategyConfig`
- 在 `on_start()` 中调用 `super().on_start()`
- 在 `on_bar()` 中调用 `super().on_bar(bar)`
- 使用 `submit_order_safe()` 下单
- 使用 `calculate_order_qty()` 计算下单量
- 使用 `Decimal` 类型处理价格和数量

✅ **强烈推荐**:
- 实现 ATR 动态止损
- 实现 ATR 动态仓位管理
- 实现滑点监控
- 添加详细的日志输出
- 编写单元测试

❌ **避免**:
- 使用 `float` 处理金融数据（精度损失）
- 硬编码参数（应使用配置文件）
- 直接访问私有属性
- 跳过基类初始化

### 风控要求

所有新策略**必须**包含：

1. **止损机制**
   - ATR 动态止损（推荐）
   - 或固定百分比止损（fallback）

2. **仓位管理**
   - 基于账户权益的仓位计算
   - 最大持仓限制
   - 杠杆控制

3. **异常处理**
   - 订单失败处理
   - 数据异常处理
   - 网络异常处理

4. **监控告警**
   - 滑点监控
   - 性能指标记录
   - 异常情况告警

---

## 📚 相关资源

### 文档
- [AI 代码规范](../AGENTS.md) - 代码风格和最佳实践
- [配置系统指南](../docs/guides/config_system.md) - 配置文件说明
- [回测引擎指南](../backtest/README.md) - 回测系统使用

### 示例
- [OI Divergence 策略](./oi_divergence_strategy.py) - 完整的现代策略实现
- [Base 策略类](./base.py) - 基础类实现参考
- [归档策略](./archived/) - 历史实现参考

### 工具
- NautilusTrader 文档: https://nautilustrader.io/docs/
- Python 量化交易指南: https://www.quantstart.com/

---

## 🤝 贡献指南

如果你开发了新策略并希望分享：

1. 确保代码符合项目规范
2. 添加详细的文档说明
3. 提供回测结果和性能指标
4. 通过单元测试验证
5. 创建 Pull Request

---

## 📝 版本历史

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-01-24 | 2.0 | 归档 Dual Thrust 和 RS Squeeze 策略 |
| 2026-01-21 | 1.5 | OI Divergence 升级到 Risk-Enhanced v3.0 |
| 2025-12-xx | 1.0 | 初始版本 |

---

## ⚡ 快速开始

**运行 OI Divergence 策略回测**:

```bash
# 1. 切换到 OI Divergence 策略
# 编辑 config/active.yaml:
#   strategy: "oi_divergence"

# 2. 运行回测
uv run python main.py backtest

# 3. 查看结果
# 回测报告: output/backtest/result/
# 日志文件: log/backtest/high_level/
```

**更多帮助**: 参考 [项目文档](../docs/) 或查看代码注释。