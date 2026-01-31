# Strategy Implementations / 策略实现

本目录包含所有交易策略的实现代码。

## 📁 目录结构

```
strategy/
├── core/                          # 基础设施模块
│   ├── base.py                   # 基础策略类和配置
│   ├── loader.py                 # 策略动态加载器
│   ├── dependency_checker.py     # 数据依赖检查
│   └── __init__.py              # 导出接口
├── dk_alpha_trend.py             # DK Alpha Trend 策略
├── dual_thrust.py                # Dual Thrust 策略
├── kalman_pairs.py               # Kalman 配对交易策略
├── __init__.py                   # 向后兼容导出
└── README.md                     # 本文档
```

## 🏗️ 基础架构

### BaseStrategy 基类

**文件**: `core/base.py`

所有策略都应继承 `BaseStrategy` 基类，自动获得：

- ✅ 统一的配置管理 (`BaseStrategyConfig`)
- ✅ 安全的下单逻辑 (`submit_order_safe`)
- ✅ 标准化的仓位计算 (`calculate_order_qty`)
- ✅ 自动的标的加载 (`on_start`)
- ✅ 数据依赖声明系统

**基本用法**:
```python
from strategy.core.base import BaseStrategy, BaseStrategyConfig

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

**向后兼容导入**:
```python
# 推荐：直接从 core 导入
from strategy.core.base import BaseStrategy, BaseStrategyConfig

# 兼容：从顶层导入（内部转发到 core）
from strategy import BaseStrategy, BaseStrategyConfig
```

---

## 🚀 策略实现

### DK Alpha Trend 策略

**文件**: `dk_alpha_trend.py`
**状态**: ✅ 活跃维护

**核心功能**:
- 动态肯特纳通道突破
- 相对强弱选币（vs BTC）
- TTM Squeeze 波动率状态
- Chandelier Exit 追踪止损

**适用场景**:
- 加密货币日线交易
- 中低频趋势跟随

### Kalman Pairs Trading 策略

**文件**: `kalman_pairs.py`
**状态**: ✅ 活跃维护

**核心功能**:
- 在线卡尔曼滤波器动态估计对冲比率
- 基于残差 Z-Score 的均值回归交易
- 适用于高度相关的资产对

**适用场景**:
- 配对交易（如 SOL/ETH）
- 市场中性策略

### Dual Thrust 策略

**文件**: `dual_thrust.py`
**状态**: ⚠️ 基础实现

**核心功能**:
- 经典日内突破策略
- 基于前N天价格范围的动态通道

**适用场景**:
- 日内交易
- 突破系统

---

## 🛠️ 开发新策略

### 开发步骤

1. **继承基类**
   ```python
   from strategy.core.base import BaseStrategy, BaseStrategyConfig
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
- [DK Alpha Trend 策略](./dk_alpha_trend.py) - 完整的现代策略实现
- [Kalman Pairs 策略](./kalman_pairs.py) - 配对交易实现
- [Base 策略类](./core/base.py) - 基础类实现参考

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
| 2026-01-31 | 3.0 | 重构：基础设施移至 core/ 子目录 |
| 2026-01-24 | 2.0 | 归档 Dual Thrust 和 RS Squeeze 策略 |
| 2025-12-xx | 1.0 | 初始版本 |

---

## ⚡ 快速开始

**运行 DK Alpha Trend 策略回测**:

```bash
# 1. 切换到 DK Alpha Trend 策略
# 编辑 config/active.yaml:
#   strategy: "dk_alpha_trend"

# 2. 运行回测
uv run python main.py backtest

# 3. 查看结果
# 回测报告: output/backtest/result/
# 日志文件: log/backtest/high_level/
```

**更多帮助**: 参考 [项目文档](../docs/) 或查看代码注释。
