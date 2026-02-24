# CLAUDE.md

This file provides comprehensive guidance for Claude Code (claude.ai/code) and AI agents working with code in this repository.

## 项目概述

这是一个基于 NautilusTrader 框架的加密货币量化交易策略开发和回测平台，专注于永续合约交易。

- **框架**: NautilusTrader 1.223.0
- **Python 版本**: 3.12.12+ (严格要求 `>=3.12.12, <3.13`)
- **包管理器**: `uv` (现代 Python 包管理器)
- **主要交易所**: Binance, OKX
- **测试覆盖率**: 386 个测试，99.7% 通过率（1 个已知失败）

## 常用命令

### 环境设置
```bash
# 安装所有依赖
uv sync

# 安装 Git Hooks（阻止直接提交到 main 分支）
./scripts/setup-hooks.sh

# 激活虚拟环境（如需要）
source .venv/bin/activate
```

### 运行测试
```bash
# 运行所有测试
uv run python -m unittest discover -s tests -p "test_*.py" -v

# 运行单个测试文件
uv run python -m unittest tests/test_oi_divergence.py -v

# 运行特定测试类
uv run python -m unittest tests.test_oi_divergence.TestCustomData -v

# 运行特定测试方法
uv run python -m unittest tests.test_oi_divergence.TestCustomData.test_open_interest_data_creation -v

# 使用 pytest 运行测试（如果可用）
uv run pytest tests/test_common_components.py -v
```

### 运行回测
```bash
# 基本回测（使用低级引擎，默认）
uv run python main.py backtest

# 使用高级引擎（推荐，性能提升 32%）
uv run python main.py backtest --type high

# 指定首选交易所和重试设置（针对需要 OI/Funding 数据的策略）
uv run python main.py backtest --oi-exchange binance --max-retries 5

# 跳过 OI 数据检查（仅当策略不需要 OI/Funding 数据时使用）
uv run python main.py backtest --skip-oi-data

# 运行特定策略回测
uv run python backtest/backtest_oi_divergence.py
```

### 代码质量检查
```bash
# 运行完整检查（推荐：分支验证 + lint + 格式化 + 测试 + PR 大小检查）
./scripts/check.sh

# 单独运行 Ruff lint
uv run ruff check .
uv run ruff check --fix .  # 自动修复

# 单独运行 Ruff 格式化
uv run ruff format .
uv run ruff format --check .  # 仅检查不修改

# 类型检查（如果配置了 mypy）
uv run mypy .
```

## 核心架构

### 1. 配置系统 (core/)

**三层架构**: YAML → Pydantic 验证 → Adapter → 应用

- `schemas.py`: Pydantic 数据模型（统一配置类）
- `loader.py`: YAML 配置加载器
- `adapter.py`: 配置适配器和统一访问接口
- `exceptions.py`: 配置异常类

**访问模式**:
```python
from core.adapter import get_adapter

adapter = get_adapter()
config = adapter.build_backtest_config()
```

**重要**: 配置系统已从 4 层简化为 3 层，移除了 `models.py` 和 `settings.py` 中间层。

### 2. 策略系统 (strategy/)

**模块化组件架构** (2026-02-20 重构):

```
strategy/
├── core/
│   ├── base.py              # 基础策略类（统一仓位管理）
│   ├── dependency_checker.py  # 策略依赖检查
│   └── loader.py            # 策略配置加载器
├── common/                  # 可复用策略组件库
│   ├── indicators/          # 技术指标（Keltner, RS, Market Regime）
│   ├── signals/             # 入场/出场信号生成器
│   └── universe/            # 动态 Universe 管理
├── keltner_rs_breakout.py  # Keltner RS 突破策略
├── dual_thrust.py          # Dual Thrust 突破策略
└── archived/               # 归档策略
    └── kalman_pairs.py     # Kalman 滤波配对交易策略
```

**关键成就**:
- 代码减少 40% (1080 行 → 650 行)
- 代码复用率提升 700% (10% → 80%)
- 新策略开发时间减少 60% (3-5 天 → 1-2 天)

**开发新策略时**:
1. 优先检查 `strategy/common/` 中的可复用组件
2. 仅实现策略特定逻辑
3. 组合组件构建策略
4. 添加策略特定测试

**多标的策略实例化机制**:

⚠️ **重要架构概念**: NautilusTrader 框架中，每个策略实例只能交易一个标的（symbol）。

对于需要交易多个标的的策略（如 Keltner RS Breakout），系统会自动为每个标的创建一个独立的策略实例：

```python
# 配置: universe_top_n = 15
# 系统行为: 创建 15 个独立的策略实例

KeltnerRSBreakoutStrategy(symbol="ETHUSDT")   # 实例 1
KeltnerRSBreakoutStrategy(symbol="BTCUSDT")   # 实例 2
KeltnerRSBreakoutStrategy(symbol="SOLUSDT")   # 实例 3
# ... 共 15 个实例
```

**关键特性**:
- 每个实例独立运行，拥有独立的状态和持仓
- 实例之间不共享数据（除非通过 common 组件）
- `max_positions` 参数限制的是单个实例的持仓数（通常为 1）
- 总持仓数 = 活跃实例数 × max_positions

**配置示例**:
```yaml
universe_top_n: 15        # 创建 15 个策略实例
max_positions: 1          # 每个实例最多持有 1 个仓位
# 结果: 最多同时持有 15 个仓位（每个标的 1 个）
```

这是 NautilusTrader 的架构设计，不是我们的实现选择。理解这一点对于正确配置策略参数和理解回测结果至关重要。

### 3. 数据管理 (utils/data_management/)

**统一数据管理模块**:

- `data_validator.py`: 数据验证和 feed 准备
- `data_manager.py`: 高级数据管理器
- `data_retrieval.py`: 主数据检索逻辑
- `data_fetcher.py`: 多源 OHLCV 获取器
- `data_limits.py`: 交易所数据限制检查
- `data_loader.py`: CSV 数据加载工具

**数据目录结构** (data/):
- `instrument/`: 交易工具定义
- `raw/`: 原始市场数据
- `parquet/`: Parquet 格式缓存
- `models/`: 机器学习模型
- `record/`: 交易记录
- `top/`: Top 市值数据

### 4. 回测引擎 (backtest/)

**两种引擎实现**:

1. **低级引擎** (`engine_low.py`): 直接使用 BacktestEngine API
   - 完全控制回测流程
   - 适合高级用户和自定义需求

2. **高级引擎** (`engine_high.py`): 使用 BacktestNode 和 Parquet 目录
   - 简化配置和使用
   - 适合快速策略验证
   - **性能更优**: 比低级引擎快 32%（272.45s vs 360.92s）

**重要注意事项**:
- CSV 数据文件必须使用 "datetime" 或 "timestamp" 作为时间列名
- 高级引擎默认期望 "datetime" 列
- 两个引擎都已验证可与 NautilusTrader 1.223.0 正常工作
- **推荐使用高级引擎**（Parquet 缓存提供 10x 数据加载速度提升）

### 5. CLI 模块 (cli/)

- `commands.py`: 命令实现（数据检查、回测执行）
- `file_cleanup.py`: 自动清理旧日志/输出文件

### 6. 工具模块 (utils/)

**核心工具**:
- `custom_data.py`: 自定义数据类型（OI, Funding Rate）
- `oi_funding_adapter.py`: OI/Funding 数据适配器
- `symbol_parser.py`: 符号解析工具
- `time_helpers.py`: 时间处理工具
- `network.py`: 网络重试工具
- `path_helpers.py`: 路径操作工具
- `instrument_helpers.py`: 交易工具辅助函数
- `universe.py`: Universe 管理

**性能分析工具** (utils/performance/):
- `metrics.py`: 性能指标计算（13 个指标）
- `analyzer.py`: 策略分析器
- `reporter.py`: 报告生成器

**性能分析工具** (utils/profiling/):
- `profiler.py`: 回测性能分析器
- `analyzer.py`: Profile 分析器
- `reporter.py`: Profile 报告生成器

## 代码风格指南

### 类型注解
- **必须**: 所有函数需要完整的类型注解
- **现代语法**: 使用 Python 3.12+ 联合类型语法 (`int | None` 而非 `Optional[int]`)
- **金融精度**: 金融计算必须使用 `Decimal` 而非 `float`

### 文档字符串
- 详细的参数描述
- 支持中英文混合
- 包含示例（如适用）

### 命名约定
- 函数和变量: `snake_case`
- 类: `PascalCase`
- 常量: `UPPER_SNAKE_CASE`
- 私有成员: `_leading_underscore`

### Ruff 配置
```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W"]
ignore = ["E501", "E402", "N803", "N805", "N806", "I001"]
```

## 测试策略

### 测试覆盖率要求
- 最低覆盖率: 55% (`--cov-fail-under=55`)
- 排除文件: `sandbox/`, `scripts/`, `main.py`, `profiling/`, `examples/`

### 测试组织
- 单元测试: `tests/test_*.py`
- 集成测试: `tests/integration/`
- 组件测试: `tests/test_common_components.py`
- 逻辑验证: `tests/verify_refactoring.py`

### 运行测试后
实现新功能或模块后，始终运行测试以验证功能，然后再提交。

## 已知问题

### 测试失败
- **test_config_list_functions** (tests/integration/test_config_system.py:62)
  - 错误: `AssertionError: 'prod' not found in ['base', 'dev', 'live', 'sandbox']`
  - 原因: 测试期望 `prod` 环境但配置中不存在
  - 状态: 待修复
  - 解决方案:
    - 选项 A: 添加 `config/environments/prod.yaml`
    - 选项 B: 修改测试，移除 `prod` 断言

## 重要架构决策

### 1. 模块化策略组件 (2026-02-20)
- 将策略代码重构为可复用组件
- 组件存储在 `strategy/common/`
- 显著减少代码重复和开发时间

### 2. 配置系统简化 (2026-01-31)
- 从 4 层简化为 3 层架构
- 移除 `models.py` 和 `settings.py`
- 统一使用 Pydantic 进行验证

### 3. 性能优化发现 (2026-02-20)
- 高级引擎比低级引擎快 32%
- Parquet 缓存提供 10x 数据加载速度提升
- 数据加载是主要瓶颈（低级引擎中占 18.5%）

### 4. Universe 生成器配置
- 支持多种重新平衡频率: 月度 (M)、周度 (W-MON)、双周 (2W-MON)
- 启动时自动配置验证
- 防止前瞻偏差: T 期数据生成 T+1 期 universe
- 输出格式: `data/universe_{N}_{FREQ}.json`

## Git 工作流

### 提交消息格式
```
<type>(<scope>): <short summary>

类型: fix, feat, refactor, chore, ci, docs, test, perf
示例: refactor(core/adapter): delegate instrument/bar restore to instrument_helpers
```

### 分支命名
```
feature/xxx, fix/xxx, refactor/xxx, ci/xxx
示例: feature/instrument-helper-adapter
```

### AI Agent 策略
- 在推送前本地运行完整测试套件
- 保持提交小而专注
- 不要在未经明确授权的情况下创建或合并 PR
- 推送到远程前获得明确许可

### GitHub Copilot PR 审阅

项目已配置 GitHub Copilot 自动审阅 PR。Copilot 会根据 `.github/copilot-instructions.md` 中的指导原则进行审阅。

**审阅重点**:
- 代码质量和最佳实践
- 测试覆盖率（最低 28%）
- 代码风格和格式化
- 安全性和性能
- NautilusTrader 特定规范
- 架构设计和反过度工程化

**使用方法**:
1. 创建 PR 后，Copilot 会自动进行审阅
2. 审阅结果会以评论形式出现在 PR 中
3. 根据建议修改代码
4. 推送更新后 Copilot 会重新审阅

**注意**: Copilot 审阅是辅助工具，不替代人工审阅。最终合并决策仍需人工确认。

### 自动合并工作流

项目配置了自动合并工作流（`.github/workflows/auto-merge.yml`），满足条件的 PR 会自动合并。

**触发条件**（满足任一即可）:
- 分支名称匹配模式：`fix/*`, `feat/*`, `docs/*`, `chore/*`, `refactor/*`, `test/*`
- PR 带有 `auto-merge` 标签
- PR 由 bot 创建（dependabot, renovate）

**合并条件**（必须全部满足）:
- ✅ 所有 CI 检查通过（tests, lint, coverage）
- ✅ PR 已被批准（至少 1 个 approval）或由 bot 创建
- ✅ 没有合并冲突
- ✅ 分支与 main 同步
- ✅ 没有 `do-not-merge` 标签

**合并策略**:
- 使用 squash merge（压缩所有提交为一个）
- 自动删除源分支
- 添加合并日志和评论

**使用示例**:

```bash
# 1. 创建符合命名规范的分支（自动触发）
git checkout -b fix/bug-description

# 2. 或者手动添加 auto-merge 标签
gh pr create --label auto-merge

# 3. 禁用自动合并（添加标签）
gh pr edit <pr-number> --add-label do-not-merge

# 4. 查看 PR 状态
gh pr view <pr-number>
```

**工作流程**:
1. 创建 PR → Copilot 自动审阅
2. CI 检查运行（tests, lint, coverage）
3. 获得人工批准（或 bot PR 自动批准）
4. 所有检查通过 → 自动合并
5. 源分支自动删除

**安全措施**:
- 不会合并直接推送到 main 的 PR
- 不会合并有 `do-not-merge` 标签的 PR
- 不会合并有冲突的 PR
- 不会合并 CI 检查失败的 PR
- 保留人工审阅的最终决定权

**最佳实践**:
- 保持 PR 小而专注（< 500 行净增加）
- 确保测试覆盖率达标
- 遵循代码规范（Ruff 检查通过）
- 及时响应 Copilot 审阅建议
- 对于重大变更，即使自动合并可用也建议人工审阅

## 数据依赖声明

策略可以声明所需的数据类型:

```python
from strategy.core.base import BaseStrategy, BaseStrategyConfig

class MyStrategyConfig(BaseStrategyConfig):
    def __init__(self):
        super().__init__()

        # 声明所需的 OI 数据依赖
        self.add_data_dependency(
            data_type="oi",
            required=True,
            period="1h",
            exchange="binance",
            auto_fetch=True
        )
```

系统将自动检测和获取所需数据。

## 性能分析工作流

### 策略性能分析
```python
from utils.performance import PerformanceMetrics, StrategyAnalyzer

# 计算指标
metrics = PerformanceMetrics(returns, trades, initial_capital=100000)
sharpe = metrics.sharpe_ratio()
max_dd = metrics.max_drawdown()

# 比较策略
analyzer = StrategyAnalyzer()
analyzer.add_strategy("Strategy A", returns_a, trades_a)
comparison = analyzer.compare_strategies()
```

### 回测性能分析
```python
from utils.profiling import BacktestProfiler, ProfileAnalyzer

# Profile 回测
profiler = BacktestProfiler()
with profiler.profile():
    run_backtest(config)

# 分析瓶颈
analyzer = ProfileAnalyzer("output/backtest.prof")
hotspots = analyzer.get_hotspots(top_n=20)
bottlenecks = analyzer.identify_bottlenecks(threshold=0.05)
```

## 常见陷阱

1. **CSV 时间列**: 必须命名为 "datetime" 或 "timestamp"
2. **Python 版本**: 严格要求 3.12.12+，不支持 3.13
3. **金融计算**: 使用 `Decimal` 而非 `float`
4. **数据加载**: 优先使用高级引擎（Parquet 缓存）
5. **策略开发**: 在实现前检查 `strategy/common/` 中的可复用组件
6. **性能优化**: 在优化前始终进行 profile（不要假设）

## 项目维护经验教训

### 1. 模块化策略架构 (2026-02-20)

**问题**: 策略代码单体化，重复率高（每个策略约 1080 行）
- 新策略开发需要 3-5 天
- 90% 代码重复
- 难以维护和测试

**解决方案**: 提取可复用组件到 `strategy/common/`
- 创建 7 个可复用组件（指标、信号、universe）
- 策略代码减少 40% (1080 → 650 行)
- 代码复用率提升 700% (10% → 80%)

**关键经验**:
1. **组件设计**: 单一职责，清晰接口
2. **测试优先**: 提取组件前先编写测试
3. **逻辑验证**: 验证重构后的代码产生相同结果
4. **文档完善**: 全面的文档加速采用
5. **渐进迁移**: 过渡期间保留原始版本

### 2. 性能分析与性能分析工具 (2026-02-20)

**问题**: 需要工具来评估策略性能和识别回测瓶颈
- 没有系统化的策略性能比较方法
- 不清楚哪个回测引擎更快
- 代码中的性能瓶颈未知

**解决方案**: 构建全面的性能分析和性能分析工具
- 创建策略性能分析工具（约 1,790 行）
- 创建回测性能分析工具（约 1,450 行）
- 实现 13 个性能指标（Sharpe、Sortino、Calmar 等）
- 集成 cProfile 进行瓶颈识别

**关键发现**:
- ✅ 高级引擎比低级引擎快 32%（272.45s vs 360.92s）
- ✅ 数据加载是主要瓶颈（10x 差异：66.75s vs 6.5s）
- ✅ Parquet 缓存提供 10x 数据加载速度提升

**关键经验**:
1. **优化前先 Profile**: 真实数据揭示意外结果（高级引擎更快）
2. **数据加载很重要**: Parquet 缓存比 CSV ��� 10 倍
3. **测量一切**: 13 个指标提供全面的策略评估
4. **自动化分析**: 报告生成节省大量时间
5. **记录发现**: 性能报告指导优化决策

**意外发现**:
- 最初假设低级引擎会更快（代码更简单）
- 实际测试显示高级引擎快 32%
- 原因: Parquet 缓存 vs 重复 CSV 读取
- 教训: 始终测量，不要假设

### 3. 配置系统简化 (2026-01-31)

**问题**: 配置系统过于复杂（4 层架构）
- `models.py` (dataclass 模型)
- `settings.py` (中间层)
- 难以理解和维护

**解决方案**: 简化为 3 层架构
- YAML → Pydantic 验证 → Adapter → 应用
- 删除 2 个文件，移除 429 行代码
- 统一使用 Pydantic 进行验证

**关键经验**:
1. **简单即美**: 更少的层次 = 更容易理解
2. **统一验证**: Pydantic 提供类型安全和验证
3. **清晰接口**: `get_adapter()` 提供统一访问点

## AI Agent Git & CI 策略

### 一般原则
1. **不自主创建或合并 PR**: AI agent 不得自行创建或合并 PR
2. **推送控制**: 仅在明确授权后才能推送到远程
3. **测试优先**: 推送前运行完整测试套件
4. **变更透明**: 提供简洁的补丁摘要（文件、动机、测试结果）

### ⚠️ 关键教训（从实际错误中学到）

**问题**: AI Agent 两次直接在 main 分支提交代码，违反分支管理规则

**根本原因**:
- pre-push hook **只能阻止推送操作**，**无法阻止本地提交**
- AI Agent 在开始工作时没有先创建分支
- 依赖 hook 提醒而非主动遵守规则

**正确流程（必须严格遵守）**:
1. **开始任何工作前**，先检查当前分支：`git branch --show-current`
2. **如果在 main 分支**，立即创建新分支：`git checkout -b <type>/<description>`
3. **完成工作后**，推送分支并创建 PR
4. **绝不直接在 main 分支提交**，即使是小改动

**补救流程**（如果已经在 main 提交）:
```bash
# 1. 创建新分支指向错误的 commit
git branch <type>/<description> <commit-hash>

# 2. 重置 main 到上一个正确的 commit
git reset --hard <previous-commit>

# 3. Force push main（需要 --no-verify）
git push origin main --force --no-verify

# 4. 切换到新分支并推送
git checkout <type>/<description>
git push origin <type>/<description> --no-verify

# 5. 创建并合并 PR
gh pr create --title "..." --body "..."
gh pr merge <pr-number> --squash --delete-branch
```

**记住**: Hook 是最后一道防线，不是第一道。主动遵守规则，不要等 hook 提醒。

### 提交前检查清单
- [ ] 运行 `uv sync` 确保环境可重现
- [ ] 运行完整测试: `uv run python -m unittest discover -s tests -p "test_*.py" -v`
- [ ] 准备简洁的补丁摘要（文件、动机、测试）
- [ ] 获得明确许可推送远程变更
- [ ] 使用提交和分支命名约定

### 测试失败时的行为
1. 收集完整的失败回溯和最小重现测试
2. 尝试 1-2 个安全的诊断修复（拼写错误、缺少导入）
3. 向人类审查者提供建议的补丁和简短解释
4. 不要自动尝试大型重构

### 仓库隐私说明
此仓库是私有的。所有文件（包括敏感配置、API 密钥和专有代码）都可以安全地提交到版本控制。远程仓库托管在具有受限访问权限的私有服务器上。

## 分支管理规则

### 严格禁止

1. **永远不要直接在 main 分支提交**
2. **所有变更必须通过 PR**
3. **所有 PR 必须通过 CI 检查**

### 分支命名规范

必须遵循格式：`<type>/<description>`

| 类型 | 用途 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat/add-rsi-strategy` |
| `fix` | Bug 修复 | `fix/position-sizing-bug` |
| `refactor` | 重构 | `refactor/simplify-config` |
| `chore` | 配置/工具 | `chore/update-deps` |
| `docs` | 文档 | `docs/update-readme` |
| `test` | 测试 | `test/add-unit-tests` |

### 工作流程

```bash
# 1. 创建新分支
git checkout -b feat/your-feature-name

# 2. 开发完成后运行完整检查
./scripts/check.sh

# 3. 推送并创建 PR
git push origin feat/your-feature-name
```

**check.sh 脚本功能**:
- ✅ 验证分支命名规范
- ✅ 运行 Ruff lint 检查
- ✅ 验证代码格式
- ✅ 运行完整测试套件
- ✅ 检查 PR 大小（警告 >500 行，拒绝 >1000 行）
- ✅ 统计变更文件数（警告 >20 个文件）

### PR 大小限制

- ⚠️ 警告：净增加 > 500 行
- ❌ 拒绝：净增加 > 1000 行
- ⚠️ 警告：修改 > 20 个文件

详细规则见：`docs/DEVELOPMENT_RULES.md`

---

## 反过度工程化原则

### 核心原则

1. **YAGNI (You Aren't Gonna Need It)**
   - 不要为"未来可能需要"的功能写代码
   - 只解决当前存在的实际问题

2. **保持简单**
   - 2-3 个策略不需要复杂的组件库
   - 直接的代码比过度抽象更好

3. **投入产出比**
   - 每行代码都应该有明确的业务价值
   - 避免"完美主义"陷阱

### 警告信号

如果你发现自己在做以下事情，请停下来：

- ❌ 为 2 个策略构建支持 20+ 策略的基础设施
- ❌ 写大量"计划"和"分析"文档
- ❌ 构建"未来可能用到"的工具
- ❌ 重构已经工作的代码（没有明确痛点）
- ❌ 创建"以防万一"的抽象层

### 正确的做法

- ✅ 专注于开发新策略（业务价值）
- ✅ 只在��到实际重复时才抽象
- ✅ 保持 PR 小而专注（< 500 行）
- ✅ 文档简洁实用（不要写没人读的文档）

---

## 文档参考

- `README.md`: 项目概述和快速开始
- `SETUP_COMPLETE.md`: 分支管理配置完成说明
- `docs/DEVELOPMENT_RULES.md`: 详细开发规范
- `docs/QUICK_START_BRANCH_MANAGEMENT.md`: 快速参考
- `docs/BRANCH_PROTECTION_SETUP.md`: GitHub 配置指南
- `strategy/common/README.md`: 策略组件库文档
- `utils/performance/README.md`: 性能分析工具文档
- `utils/profiling/README.md`: 性能分析工具文档
- `docs/MODULAR_REFACTORING.md`: 模块化重构报告
