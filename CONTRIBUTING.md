# 贡献指南

感谢你对 Nautilus Practice 项目的关注！我们欢迎各种形式的贡献。

## 行为准则

- 尊重所有贡献者
- 保持友好和专业的交流
- 接受建设性的批评
- 关注对项目最有利的事情

## 如何贡献

### 报告 Bug

如果你发现了 Bug，请创建一个 Issue 并包含以下信息：

- **清晰的标题**：简洁描述问题
- **复现步骤**：详细的步骤说明
- **期望行为**：你期望发生什么
- **实际行为**：实际发生了什么
- **环境信息**：
  - Python 版本
  - NautilusTrader 版本
  - 操作系统
  - 相关配置文件

**示例**：

```markdown
## Bug 描述
回测引擎在加载 Universe 时抛出 KeyError

## 复现步骤
1. 配置 universe.enabled = true
2. 运行 `uv run python main.py backtest --type high`
3. 观察错误

## 期望行为
成功加载 Universe 并开始回测

## 实际行为
抛出 KeyError: '2024-01'

## 环境
- Python: 3.12.12
- NautilusTrader: 1.223.0
- OS: Ubuntu 22.04
```

### 提出新功能

如果你有新功能的想法，请创建一个 Issue 并包含：

- **功能描述**：清晰描述新功能
- **使用场景**：为什么需要这个功能
- **实现建议**：如果有的话，提供实现思路
- **替代方案**：是否考虑过其他方案

### 提交代码

#### 1. Fork 仓库

点击 GitHub 页面右上角的 "Fork" 按钮。

#### 2. 克隆你的 Fork

```bash
git clone https://github.com/YOUR_USERNAME/nautilus-practice.git
cd nautilus-practice
```

#### 3. 添加上游仓库

```bash
git remote add upstream https://github.com/iridite/nautilus-practice.git
```

#### 4. 创建功能分支

```bash
# 从最新的 main 分支创建
git checkout main
git pull upstream main
git checkout -b feat/your-feature-name
```

**分支命名规范**：

- `feat/*`: 新功能（如 `feat/add-rsi-indicator`）
- `fix/*`: Bug 修复（如 `fix/universe-loading-error`）
- `docs/*`: 文档更新（如 `docs/update-readme`）
- `refactor/*`: 代码重构（如 `refactor/simplify-config`）
- `test/*`: 测试相关（如 `test/add-adapter-tests`）
- `chore/*`: 构建/工具相关（如 `chore/update-dependencies`）

#### 5. 开发

**安装依赖**：

```bash
uv sync
```

**代码规范**：

- 遵循 PEP 8 风格指南
- 使用 ruff 进行代码检查和格式化
- 添加必要的类型注解
- 编写清晰的文档字符串

**运行代码检查**：

```bash
# Lint 检查
uv run ruff check .

# 代码格式化
uv run ruff format .

# 类型检查
uv run pyright
```

**编写测试**：

- 为新功能添加单元测试
- 确保所有测试通过
- 测试覆盖率应保持或提高

```bash
# 运行所有测试
uv run python -m unittest discover -s tests -p "test_*.py" -v

# 运行特定测试
uv run python -m unittest tests.test_your_module -v
```

#### 6. 提交更改

**Commit 规范**：

遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type**：
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档更新
- `refactor`: 代码重构
- `test`: 测试相关
- `chore`: 构建/工具相关
- `perf`: 性能优化
- `style`: 代码风格（不影响功能）

**示例**：

```bash
git add .
git commit -m "feat(universe): add support for monthly frequency

- Add ME (month-end) frequency option
- Update Universe generator to handle monthly periods
- Add tests for monthly frequency

Closes #123"
```

**Commit 消息最佳实践**：

- 使用现在时态（"add" 而不是 "added"）
- 首行不超过 72 字符
- 详细描述在空行后
- 引用相关 Issue（如 `Closes #123`）

#### 7. 推送到你的 Fork

```bash
git push origin feat/your-feature-name
```

#### 8. 创建 Pull Request

1. 访问你的 Fork 页面
2. 点击 "Compare & pull request"
3. 填写 PR 描述

**PR 描述模板**：

```markdown
## 概述
简要描述这个 PR 的目的

## 改动内容
- 改动 1
- 改动 2
- 改动 3

## 测试
- [ ] 添加了单元测试
- [ ] 所有测试通过
- [ ] 手动测试通过

## 相关 Issue
Closes #123

## 截图（如适用）
[添加截图]

## 检查清单
- [ ] 代码遵循项目规范
- [ ] 添加了必要的文档
- [ ] 更新了 CHANGELOG（如适用）
- [ ] 所有 CI 检查通过
```

#### 9. Code Review

- 响应 Review 意见
- 根据反馈修改代码
- 保持 PR 更新

```bash
# 同步上游更改
git fetch upstream
git rebase upstream/main

# 推送更新
git push origin feat/your-feature-name --force-with-lease
```

## 开发指南

### 项目结构

```
nautilus-practice/
├── strategy/              # 策略实现
│   ├── common/           # 可复用组件
│   └── core/             # 策略基类
├── backtest/             # 回测引擎
├── sandbox/              # 沙盒引擎
├── live/                 # 实盘引擎
├── config/               # 配置文件
├── core/                 # 核心系统
├── scripts/              # 工具脚本
├── utils/                # 工具模块
├── data/                 # 数据目录
├── docs/                 # 文档
└── tests/                # 测试
```

### 添加新策略

1. **创建策略文件**：`strategy/your_strategy.py`

```python
from strategy.core.base import BaseStrategy
from strategy.core.config import BaseStrategyConfig

class YourStrategyConfig(BaseStrategyConfig):
    """策略配置"""
    param1: float = 1.0
    param2: int = 20

class YourStrategy(BaseStrategy):
    """你的策略"""

    def __init__(self, config: YourStrategyConfig):
        super().__init__(config)
        self.param1 = config.param1
        self.param2 = config.param2

    def on_bar(self, bar):
        """处理 Bar 数据"""
        # 实现你的策略逻辑
        pass
```

2. **创建配置文件**：`config/strategies/your_strategy.yaml`

```yaml
name: your_strategy
module_path: strategy.your_strategy
config_class: YourStrategyConfig
parameters:
  param1: 1.0
  param2: 20
```

3. **添加测试**：`tests/test_your_strategy.py`

```python
import unittest
from strategy.your_strategy import YourStrategy, YourStrategyConfig

class TestYourStrategy(unittest.TestCase):
    def test_initialization(self):
        config = YourStrategyConfig(param1=1.0, param2=20)
        strategy = YourStrategy(config)
        self.assertEqual(strategy.param1, 1.0)
        self.assertEqual(strategy.param2, 20)
```

4. **更新文档**：在 README.md 中添加策略说明

### 添加新指标

1. **创建指标文件**：`strategy/common/indicators/your_indicator.py`

```python
from nautilus_trader.indicators.base.indicator import Indicator

class YourIndicator(Indicator):
    """你的指标"""

    def __init__(self, period: int = 20):
        super().__init__()
        self.period = period

    def update_raw(self, value: float):
        """更新指标值"""
        # 实现指标计算逻辑
        pass
```

2. **添加测试**：`tests/test_your_indicator.py`

3. **更新文档**：在相关文档中说明指标用途

### 代码风格

**Python 代码**：

- 使用 4 空格缩进
- 最大行长度 100 字符
- 使用类型注解
- 编写文档字符串

```python
def calculate_indicator(
    data: list[float],
    period: int = 20,
    multiplier: float = 2.0,
) -> float:
    """计算指标值

    Args:
        data: 输入数据
        period: 计算周期
        multiplier: 乘数

    Returns:
        计算结果

    Raises:
        ValueError: 当数据不足时
    """
    if len(data) < period:
        raise ValueError(f"Data length {len(data)} < period {period}")

    # 实现逻辑
    return result
```

**YAML 配置**：

- 使用 2 空格缩进
- 键值对使用 `: ` 分隔（冒号后有空格）
- 布尔值使用 `true`/`false`

```yaml
strategy:
  name: example
  parameters:
    period: 20
    enabled: true
```

### 测试指南

**单元测试**：

- 测试文件命名：`test_*.py`
- 测试类命名：`Test*`
- 测试方法命名：`test_*`

```python
import unittest
from unittest.mock import Mock, patch

class TestYourModule(unittest.TestCase):
    def setUp(self):
        """测试前准备"""
        self.config = Mock()

    def tearDown(self):
        """测试后清理"""
        pass

    def test_feature(self):
        """测试功能"""
        result = your_function()
        self.assertEqual(result, expected)
```

**集成测试**：

- 测试完整的工作流
- 使用真实的配置文件
- 验证端到端功能

### 文档规范

**代码文档**：

- 所有公共类和函数必须有文档字符串
- 使用 Google 风格的文档字符串
- 包含参数、返回值、异常说明

**Markdown 文档**：

- 使用清晰的标题层级
- 添加代码示例
- 包含实际的使用场景

## 发布流程

（仅限维护者）

1. 更新版本号
2. 更新 CHANGELOG.md
3. 创建 Git tag
4. 推送到 GitHub
5. 创建 Release

## 获取帮助

- **GitHub Issues**: https://github.com/iridite/nautilus-practice/issues
- **GitHub Discussions**: https://github.com/iridite/nautilus-practice/discussions

## 许可证

通过贡献代码，你同意你的贡献将在 MIT 许可证下发布。

---

再次感谢你的贡献！🎉
