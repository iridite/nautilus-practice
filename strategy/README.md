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
├── common/                        # 共享组件库（⚠️ 停止扩展）
│   ├── indicators/               # 技术指标
│   ├── signals/                  # 信号生成器
│   └── universe/                 # 动态标的池管理
├── dual_thrust.py                # Dual Thrust 突破策略
├── keltner_rs_breakout.py        # Keltner RS 突破策略
├── archived/                     # 归档策略
│   └── kalman_pairs.py          # Kalman 配对交易策略
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

### Keltner RS Breakout 策略

**文件**: `keltner_rs_breakout.py`
**状态**: ✅ 活跃维护

**核心功能**:
- 动态 Keltner 通道突破
- 双层过滤：Universe 选币 + 相对强度（vs BTC）
- BTC 市场状态过滤器
- 市场狂热度过滤（Funding Rate）
- Chandelier Exit 追踪止损 + 时间止损
- ATR 动态仓位管理

**适用场景**:
- 加密货币日线交易
- 中频趋势跟随
- 多标的组合策略

**技术特点**:
- 使用 common/ 模块化组件
- 代码量：458 行（相比原始版本减少 40%）

### Dual Thrust 策略

**文件**: `dual_thrust.py`
**状态**: ✅ 活跃维护

**核心功能**:
- 经典日内突破策略
- 基于前 N 天价格范围的动态通道
- Range = Max(HH - LC, HC - LL)

**适用场景**:
- 日内交易
- 突破系统

**技术特点**:
- 使用 common/ 模块化组件
- 代码简洁：168 行

### Kalman Pairs Trading 策略

**文件**: `archived/kalman_pairs.py`
**状态**: 📦 已归档

**核心功能**:
- 在线卡尔曼滤波器动态估计对冲比率
- 基于残差 Z-Score 的均值回归交易
- 适用于高度相关的资产对

**适用场景**:
- 配对交易（如 SOL/ETH）
- 市场中性策略

---

## 🧩 共享组件库（common/）

### ⚠️ 使用原则

**停止扩展原则**（2026-02-23 确立）:
- ✅ 保留现有组件，支持当前 2 个策略
- ❌ 不再主动添加新组件
- ✅ 新策略优先直接实现
- ✅ 只在第 3 个策略需要相同逻辑时才抽象

**YAGNI 原则**（You Aren't Gonna Need It）:
1. 新策略直接实现，不考虑复用
2. 当第 2 个策略需要相同逻辑时，再考虑抽象
3. 当第 3 个策略需要时，才创建 common 组件

### 现有组件

**indicators/**:
- `KeltnerChannel`: Keltner 通道指标
- `RelativeStrengthCalculator`: 相对强度计算
- `MarketRegimeFilter`: BTC 市场状态过滤
- `DualThrustIndicator`: Dual Thrust 通道计算

**signals/**:
- `EntrySignalGenerator`: 入场信号生成
- `ExitSignalGenerator`: 出场信号生成
- `SqueezeDetector`: Squeeze 状态检测
- `DualThrustSignalGenerator`: Dual Thrust 信号生成

**universe/**:
- `DynamicUniverseManager`: 动态标的池管理

---

## 🛠️ 开发新策略

### 开发步骤
</thinking>

<old_text line=189>
### 文档
- [AI 代码规范](../AGENTS.md) - 代码风格和最佳实践
- [配置系统指南](../docs/guides/config_system.md) - 配置文件说明
- [回测引擎指南](../backtest/README.md) - 回测系统使用

### 示例
- [DK Alpha Trend 策略](./dk_alpha_trend.py) - 完整的现代策略实现
- [Kalman Pairs 策略](./kalman_pairs.py) - 配对交易实现
- [Base 策略类](./core/base.py) - 基础类实现参考

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
- [配置系统指南](../docs/guides/config_system.md) - 配置文件说明
- [回测引擎指南](../backtest/README.md) - 回测系统使用

### 示例
- [Keltner RS Breakout 策略](./keltner_rs_breakout.py) - 完整的现代策略实现
- [Dual Thrust 策略](./dual_thrust.py) - 简洁的突破策略实现
- [Kalman Pairs 策略](./archived/kalman_pairs.py) - 配对交易实现
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
| 2026-02-23 | 4.0 | 清理：删除原始版本，统一使用重构版本；确立 common/ 停止扩展原则 |
| 2026-01-31 | 3.0 | 重构：基础设施移至 core/ 子目录 |
| 2026-01-24 | 2.0 | 归档 Kalman Pairs 策略 |
| 2025-12-xx | 1.0 | 初始版本 |

---

## ⚡ 快速开始

**运行 Keltner RS Breakout 策略回测**:

```bash
# 1. 切换到 Keltner RS Breakout 策略
# 编辑 config/active.yaml:
#   strategy: "keltner_rs_breakout"

# 2. 运行回测（推荐使用高级引擎）
uv run python main.py backtest --type high

# 3. 查看结果
# 回测报告: output/backtest/result/
# 日志文件: log/backtest/high_level/
```

**更多帮助**: 参考 [项目文档](../docs/) 或查看代码注释。
