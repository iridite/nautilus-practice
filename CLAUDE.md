# Claude AI Agent 开发指南

本文档为 AI Agent 提供项目开发指南和工作规范。

## 项目概述

Nautilus Practice 是一个加密货币量化交易回测平台，基于 NautilusTrader 框架。

## 核心架构

### 1. 模块化策略架构

策略代码组织为可复用组件：
- `strategy/common/indicators/` - 技术指标（Keltner、RSI 等）
- `strategy/common/signals/` - 信号生成器（入场、出场）
- `strategy/common/universe/` - 标的选择（动态 Universe）

### 2. 双回测引擎

- **低级引擎** (`backtest/engine_low.py`): 简单、直接、易调试
  - 适用场景：快速验证、调试策略逻辑
  - 限制：可能不生成完整的统计数据（PNL、Sharpe 等）

- **高级引擎** (`backtest/engine_high.py`): 快 32%、Parquet 缓存、10x 数据加载速度
  - 适用场景：正式回测、性能分析、参数优化
  - 优势：完整的统计数据、更快的执行速度

**重要**:
- 优先使用高级引擎进行正式回测
- 低级引擎主要用于调试和快速验证
- 两个引擎各有用途，不需要优化调用代码

### 3. 配置系统

3 层架构：YAML → Pydantic 验证 → Adapter → 应用

```python
from core.config_adapter import get_adapter

adapter = get_adapter()
strategy_config = adapter.get_strategy_config()
env_config = adapter.get_environment_config()
```

## 工作规范

### Git 工作流（必须严格遵守）

1. **开始任何工作前**，先检查当前分支：
   ```bash
   git branch --show-current
   ```

2. **如果在 main 分支**，立即创建新分支：
   ```bash
   git checkout -b <type>/<description>
   ```

3. **绝不直接在 main 分支提交**，即使是小改动

4. **分支命名规范**:
   - `feat/`: 新功能（如 `feat/strategy-optimization`）
   - `fix/`: Bug 修复
   - `refactor/`: 代码重构
   - `docs/`: 文档更新
   - `test/`: 测试相关
   - `chore/`: 构建、工具、依赖更新（如 `chore/fix-github-actions`）

5. **分支关注点分离**:
   - 策略优化 → `feat/strategy-optimization`
   - 基础设施改进 → `chore/fix-github-actions`
   - 不要在功能分支中混入基础设施修改

### Commit Message 规范

遵循 Conventional Commits:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**示例**:
```
feat(strategy): add filter statistics and zero-trade diagnostics

- Add filter_stats tracking for 8 filters
- Implement _log_filter_statistics() with auto-warning
- Use ERROR level for 100% blocked warnings

Resolves: #123
```

### 测试要求

提交前必须运行测试：

```bash
uv run python -m unittest discover -s tests -p "test_*.py" -v
```

## 开发指南

### 添加新策略

1. 创建策略文件：`strategy/my_strategy.py`
2. 继承 `Strategy` 基类
3. 实现核心方法：`on_bar()`, `on_stop()`
4. 添加配置：`config/strategies/my_strategy.yaml`
5. 编写测试：`tests/test_my_strategy.py`

### 添加新组件

1. 选择组件类型：indicators / signals / universe
2. 创建文件：`strategy/common/<type>/my_component.py`
3. 实现接口
4. 编写单元测试
5. 更新文档

### 调试零交易问题

使用过滤器诊断系统：

1. 启用 DEBUG 日志：
   ```yaml
   # config/environments/dev.yaml
   logging:
     level: "DEBUG"
     components_only: false
   ```

2. 运行回测查看过滤器统计

3. 根据统计报告调整配置

## 关键经验教训

### 1. Git 分支管理

**问题**: AI Agent 两次直接在 main 分支提交代码

**根本原因**: pre-push hook 只能阻止推送，无法阻止本地提交

**解决方案**: 开始工作前主动检查分支，不依赖 hook 提醒

### 2. 过滤器组合效应

**问题**: 多个独立过滤器导致 100% 信号被拦截

**原因**: 组合概率是乘法关系（8 个过滤器 × 90% 通过率 = 43% 总通过率）

**解决方案**: 使用过滤器统计系统量化每个过滤器的影响

### 3. NautilusTrader 多标的机制

**关键发现**: 每个策略实例只能交易一个标的

**影响**: `universe_top_n: 15` 会创建 15 个独立策略实例

**设计建议**:
- Universe 大小要合理（太小 → 信号被拦截，太大 → 资金分散）
- 更新频率要匹配策略周期

### 4. 数据周期匹配

**问题**: 使用 1h 数据运行日线策略会将指标时间尺度压缩 24 倍

**解决方案**: 严格匹配数据周期和策略配置

### 5. 日志配置的影响

**问题**: `components_only: true` 会过滤策略实例日志

**解决方案**: 调试时设置 `components_only: false`

### 6. 回测引擎选择

**问题**: 低级引擎可能不生成完整的统计数据

**现象**:
- `pnl` 和 `returns` 字段为空
- 只有基本的订单和持仓统计

**解决方案**:
- 正式回测使用高级引擎：`--type high`
- 低级引擎仅用于快速调试

### 7. 参数调优的关键影响

**问题**: 过于保��的参数导致所有信号被过滤

**关键参数**:
- `keltner_trigger_multiplier`: 1.5 太严格 → 建议 2.0-2.3
- `deviation_threshold`: 0.25 太严格 → 建议 0.30-0.35
- `stop_loss_atr_multiplier`: 影响风险控制，建议 2.4-2.8

**教训**:
- 参数微调对交易数量影响巨大
- 使用 `feat/strategy-optimization` 分支进行参数实验
- 对比不同参数组合的回测结果

## 性能优化

### 数据加载

- 使用 Parquet 缓存：10x 速度提升
- 避免重复 CSV 读取
- 批量处理数据

### 回测引擎

- 高级引擎比低级引擎快 32%
- 使用 cProfile 识别瓶颈
- 优化数据加载是关键

## 常用命令

```bash
# 检查当前分支
git branch --show-current

# 创建新分支
git checkout -b <type>/<description>

# 运行测试
uv run python -m unittest discover -s tests -p "test_*.py" -v

# 运行回测（推荐高级引擎）
uv run python main.py backtest --type high

# 分析回测结果
python scripts/analyze_backtest_results.py

# 代码检查
uv run ruff check .
uv run ruff format .

# 查看变更
git status
git diff

# 查看最新回测结果
ls -lht output/backtest/result/*.json | head -3
```

## 详细文档

更多详细信息请参考：

- [架构决策记录](docs/lessons-learned/ARCHITECTURE_DECISIONS.md)
- [TUI 集成经验](docs/lessons-learned/TUI_INTEGRATION.md)
- [Git 工作流](docs/lessons-learned/GIT_WORKFLOW.md)
- [策略调试与诊断](docs/lessons-learned/STRATEGY_DEBUGGING.md)

## 注意事项

1. **保留 debug 日志**: 用户明确要求保留所有 debug 日志信息
2. **双引擎设计**: 维持低级和高级引擎，不需要优化调用代码
3. **测试优先**: 提交前必须运行测试
4. **小步提交**: 每个 commit 只做一件事
5. **描述性消息**: 清晰说明"为什么"而非"是什么"
