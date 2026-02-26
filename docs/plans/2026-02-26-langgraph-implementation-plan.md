# LangGraph 策略自动化系统实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 构建基于 LangGraph 的多 Agent 协作系统，实现策略自动化研究和参数优化

**Architecture:** Clean Architecture 四层架构（Presentation → Application → Domain → Infrastructure），多 Agent 协作（Coordinator、Researcher、Optimizer、Validator），使用 LangGraph 编排工作流，SQLite 存储运行记录

**Tech Stack:** LangGraph, Claude API, SQLAlchemy, Pydantic, structlog, pytest

---

## 阶段 1：基础设施搭建（Phase 1）

### Task 1.1: 项目结构初始化

**Files:**
- Create: `langgraph/__init__.py`
- Create: `langgraph/domain/__init__.py`
- Create: `langgraph/application/__init__.py`
- Create: `langgraph/infrastructure/__init__.py`
- Create: `langgraph/presentation/__init__.py`
- Create: `langgraph/shared/__init__.py`
- Create: `langgraph/tests/__init__.py`

**Step 1: 创建目录结构**

```bash
mkdir -p langgraph/{domain,application,infrastructure,presentation,shared,tests}/{models,services,repositories,use_cases,dto,interfaces,agents,graph,llm,database,backtest,code_gen,cli,utils}
touch langgraph/__init__.py
touch langgraph/domain/__init__.py
touch langgraph/application/__init__.py
touch langgraph/infrastructure/__init__.py
touch langgraph/presentation/__init__.py
touch langgraph/shared/__init__.py
touch langgraph/tests/__init__.py
```

**Step 2: 创建输出目录**

```bash
mkdir -p output/langgraph/{strategies,reports,logs}
```

**Step 3: 提交**

```bash
git add langgraph/ output/langgraph/
git commit -m "chore: initialize LangGraph project structure

- Create Clean Architecture directory layout
- Add domain, application, infrastructure, presentation layers
- Create output directories for strategies, reports, logs"
```

---

### Task 1.2: 依赖管理

**Files:**
- Modify: `pyproject.toml`

**Step 1: 添加 LangGraph 依赖**

在 `pyproject.toml` 的 `dependencies` 数组中添加：

```toml
dependencies = [
    # ... 现有依赖 ...
    "langgraph>=0.2.0",
    "langchain>=0.3.0",
    "langchain-anthropic>=0.2.0",
    "anthropic>=0.39.0",
    "sqlalchemy>=2.0.0",
    "alembic>=1.13.0",
    "python-structlog>=24.1.0",
]
```

**Step 2: 安装依赖**

```bash
uv sync
```

**Step 3: 验证安装**

```bash
uv run python -c "import langgraph; import langchain; import anthropic; print('Dependencies OK')"
```

Expected output: `Dependencies OK`

**Step 4: 提交**

```bash
git add pyproject.toml
git commit -m "chore: add LangGraph and related dependencies

- Add langgraph, langchain, langchain-anthropic
- Add anthropic SDK for Claude API
- Add sqlalchemy and alembic for database
- Add structlog for structured logging"
```

---

### Task 1.3: 配置管理

**Files:**
- Create: `langgraph/shared/config.py`
- Create: `langgraph/tests/unit/shared/test_config.py`
- Create: `.env.example`

**Step 1: 编写配置测试**

```python
# langgraph/tests/unit/shared/test_config.py
import pytest
from langgraph.shared.config import LangGraphConfig


def test_config_loads_from_env(monkeypatch):
    """测试从环境变量加载配置"""
    monkeypatch.setenv("LANGGRAPH_CLAUDE_API_KEY", "test-key")
    monkeypatch.setenv("LANGGRAPH_MAX_PARALLEL_BACKTESTS", "8")

    config = LangGraphConfig()

    assert config.claude_api_key == "test-key"
    assert config.max_parallel_backtests == 8


def test_config_defaults():
    """测试默认配置值"""
    config = LangGraphConfig(claude_api_key="test-key")

    assert config.llm_provider == "claude"
    assert config.max_parallel_backtests == 4
    assert config.log_level == "INFO"
    assert "sqlite:///" in config.database_url


def test_config_validation_missing_api_key():
    """测试缺少 API key 时抛出异常"""
    with pytest.raises(ValueError):
        LangGraphConfig()
```

**Step 2: 运行测试（预期失败）**

```bash
uv run pytest langgraph/tests/unit/shared/test_config.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'langgraph.shared.config'"

**Step 3: 实现配置类**

```python
# langgraph/shared/config.py
"""LangGraph 配置管理"""
from pathlib import Path
from pydantic import BaseModel, Field, field_validator


class LangGraphConfig(BaseModel):
    """LangGraph 系统配置"""

    # LLM 配置
    llm_provider: str = Field(default="claude", description="LLM 提供商")
    claude_api_key: str = Field(..., description="Claude API Key")
    claude_model_complex: str = Field(default="claude-opus-4-6", description="复杂任务模型")
    claude_model_fast: str = Field(default="claude-sonnet-4-6", description="快速任务模型")

    # 回测配置
    max_parallel_backtests: int = Field(default=4, ge=1, le=16, description="最大并行回测数")
    backtest_timeout: int = Field(default=300, description="单次回测超时（秒）")

    # 数据库配置
    database_url: str = Field(
        default="sqlite:///output/langgraph/database.db",
        description="数据库连接 URL"
    )

    # 日志配置
    log_level: str = Field(default="INFO", description="日志级别")
    log_file: str = Field(default="output/langgraph/logs/langgraph.log", description="日志文件路径")

    # 输出配置
    output_dir: Path = Field(default=Path("output/langgraph"), description="输出目录")

    class Config:
        env_prefix = "LANGGRAPH_"
        env_file = ".env"
        env_file_encoding = "utf-8"

    @field_validator("claude_api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        if not v or v == "":
            raise ValueError("Claude API key is required")
        return v

    def model_post_init(self, __context) -> None:
        """初始化后创建必要的目录"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "strategies").mkdir(exist_ok=True)
        (self.output_dir / "reports").mkdir(exist_ok=True)
        (self.output_dir / "logs").mkdir(exist_ok=True)


def get_config() -> LangGraphConfig:
    """获取全局配置实例"""
    return LangGraphConfig()
```

**Step 4: 运行测试（预期通过）**

```bash
uv run pytest langgraph/tests/unit/shared/test_config.py -v
```

Expected: PASS (3 tests)

**Step 5: 创建环境变量示例文件**

```bash
# .env.example
LANGGRAPH_CLAUDE_API_KEY=your-claude-api-key-here
LANGGRAPH_MAX_PARALLEL_BACKTESTS=4
LANGGRAPH_LOG_LEVEL=INFO
```

**Step 6: 提交**

```bash
git add langgraph/shared/config.py langgraph/tests/unit/shared/test_config.py .env.example
git commit -m "feat(config): add configuration management with Pydantic

- Implement LangGraphConfig with environment variable support
- Add validation for required fields (API key)
- Auto-create output directories on initialization
- Add comprehensive unit tests
- Add .env.example for reference"
```

---

### Task 1.4: 异常体系

**Files:**
- Create: `langgraph/shared/exceptions.py`
- Create: `langgraph/tests/unit/shared/test_exceptions.py`

**Step 1: 编写异常测试**

```python
# langgraph/tests/unit/shared/test_exceptions.py
import pytest
from langgraph.shared.exceptions import (
    LangGraphError,
    StrategyGenerationError,
    OptimizationError,
    BacktestError,
    ValidationError,
    LLMError,
)


def test_base_exception():
    """测试基础异常"""
    error = LangGraphError("test error")
    assert str(error) == "test error"
    assert isinstance(error, Exception)


def test_strategy_generation_error():
    """测试策略生成异常"""
    error = StrategyGenerationError("generation failed")
    assert isinstance(error, LangGraphError)


def test_optimization_error():
    """测试优化异常"""
    error = OptimizationError("optimization failed")
    assert isinstance(error, LangGraphError)


def test_backtest_error():
    """测试回测异常"""
    error = BacktestError("backtest failed")
    assert isinstance(error, LangGraphError)


def test_validation_error():
    """测试验证异常"""
    error = ValidationError("validation failed")
    assert isinstance(error, LangGraphError)


def test_llm_error():
    """测试 LLM 异常"""
    error = LLMError("LLM call failed")
    assert isinstance(error, LangGraphError)
```

**Step 2: 运行测试（预期失败）**

```bash
uv run pytest langgraph/tests/unit/shared/test_exceptions.py -v
```

Expected: FAIL with "ModuleNotFoundError"

**Step 3: 实现异常类**

```python
# langgraph/shared/exceptions.py
"""LangGraph 自定义异常"""


class LangGraphError(Exception):
    """LangGraph 基础异常"""
    pass


class StrategyGenerationError(LangGraphError):
    """策略生成失败"""
    pass


class OptimizationError(LangGraphError):
    """参数优化失败"""
    pass


class BacktestError(LangGraphError):
    """回测执行失败"""
    pass


class ValidationError(LangGraphError):
    """验证失败"""
    pass


class LLMError(LangGraphError):
    """LLM 调用失败"""
    pass


class DatabaseError(LangGraphError):
    """数据库操作失败"""
    pass


class ConfigurationError(LangGraphError):
    """配置错误"""
    pass
```

**Step 4: 运行测试（预期通过）**

```bash
uv run pytest langgraph/tests/unit/shared/test_exceptions.py -v
```

Expected: PASS (6 tests)

**Step 5: 提交**

```bash
git add langgraph/shared/exceptions.py langgraph/tests/unit/shared/test_exceptions.py
git commit -m "feat(exceptions): add custom exception hierarchy

- Implement LangGraphError as base exception
- Add domain-specific exceptions (Strategy, Optimization, Backtest, etc.)
- Add comprehensive unit tests
- Follow exception hierarchy best practices"
```

---

### Task 1.5: 日志系统

**Files:**
- Create: `langgraph/shared/logging.py`
- Create: `langgraph/tests/unit/shared/test_logging.py`

**Step 1: 编写日志测试**

```python
# langgraph/tests/unit/shared/test_logging.py
import pytest
import structlog
from langgraph.shared.logging import setup_logging, get_logger


def test_setup_logging():
    """测试日志初始化"""
    setup_logging(level="DEBUG")
    logger = get_logger("test")

    assert logger is not None
    assert isinstance(logger, structlog.stdlib.BoundLogger)


def test_logger_context():
    """测试日志上下文绑定"""
    logger = get_logger("test")
    bound_logger = logger.bind(task_id="123", strategy="test_strategy")

    # 验证绑定成功（通过检查 logger 类型）
    assert isinstance(bound_logger, structlog.stdlib.BoundLogger)


def test_multiple_loggers():
    """测试多个 logger 实例"""
    logger1 = get_logger("module1")
    logger2 = get_logger("module2")

    assert logger1 is not None
    assert logger2 is not None
```

**Step 2: 运行测试（预期失败）**

```bash
uv run pytest langgraph/tests/unit/shared/test_logging.py -v
```

Expected: FAIL with "ModuleNotFoundError"

**Step 3: 实现日志系统**

```python
# langgraph/shared/logging.py
"""LangGraph 结构化日志系统"""
import logging
import sys
from pathlib import Path
from typing import Any

import structlog


def setup_logging(
    level: str = "INFO",
    log_file: str | None = None,
    json_logs: bool = False
) -> None:
    """
    配置结构化日志系统

    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        log_file: 日志文件路径（可选）
        json_logs: 是否使用 JSON 格式（生产环境推荐）
    """
    # 配置标准库 logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )

    # 配置 structlog 处理器
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_logs:
        # 生产环境：JSON 格式
        processors.append(structlog.processors.JSONRenderer())
    else:
        # 开发环境：彩色控制台输出
        processors.extend([
            structlog.dev.ConsoleRenderer(colors=True),
        ])

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 配置文件日志（如果指定）
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(getattr(logging, level.upper()))
        logging.root.addHandler(file_handler)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    获取 logger 实例

    Args:
        name: Logger 名称（通常是模块名）

    Returns:
        结构化 logger 实例
    """
    return structlog.get_logger(name)
```

**Step 4: 运行测试（预期通过）**

```bash
uv run pytest langgraph/tests/unit/shared/test_logging.py -v
```

Expected: PASS (3 tests)

**Step 5: 提交**

```bash
git add langgraph/shared/logging.py langgraph/tests/unit/shared/test_logging.py
git commit -m "feat(logging): add structured logging with structlog

- Implement setup_logging with configurable level and output
- Support both console (dev) and JSON (prod) formats
- Add context binding for request tracing
- Add comprehensive unit tests"
```

---

## 阶段 2：领域层（Phase 2）

### Task 2.1: 领域模型 - Strategy

**Files:**
- Create: `langgraph/domain/models/__init__.py`
- Create: `langgraph/domain/models/strategy.py`
- Create: `langgraph/tests/unit/domain/models/test_strategy.py`

**Step 1: 编写 Strategy 模型测试**

```python
# langgraph/tests/unit/domain/models/test_strategy.py
import pytest
from datetime import datetime
from langgraph.domain.models.strategy import Strategy, StrategyMetadata, StrategyStatus


def test_strategy_creation():
    """测试策略创建"""
    metadata = StrategyMetadata(
        author="AI",
        version="1.0.0",
        tags=["trend", "breakout"],
        description="Test strategy"
    )

    strategy = Strategy(
        id="test-001",
        name="TestStrategy",
        code="class TestStrategy: pass",
        config={"param1": 10},
        metadata=metadata,
        status=StrategyStatus.DRAFT
    )

    assert strategy.id == "test-001"
    assert strategy.name == "TestStrategy"
    assert strategy.status == StrategyStatus.DRAFT
    assert strategy.metadata.author == "AI"


def test_strategy_validation():
    """测试策略验证"""
    strategy = Strategy(
        id="test-002",
        name="ValidStrategy",
        code="class ValidStrategy: pass",
        config={},
        metadata=StrategyMetadata(author="AI", version="1.0.0"),
        status=StrategyStatus.DRAFT
    )

    # 验证通过后状态变更
    strategy.status = StrategyStatus.VALIDATED
    assert strategy.status == StrategyStatus.VALIDATED


def test_strategy_metadata_defaults():
    """测试元数据默认值"""
    metadata = StrategyMetadata(author="AI", version="1.0.0")

    assert metadata.tags == []
    assert metadata.description == ""
    assert isinstance(metadata.created_at, datetime)
```

**Step 2: 运行测试（预期失败）**

```bash
uv run pytest langgraph/tests/unit/domain/models/test_strategy.py -v
```

Expected: FAIL with "ModuleNotFoundError"

**Step 3: 实现 Strategy 模型**

```python
# langgraph/domain/models/strategy.py
"""策略领域模型"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class StrategyStatus(str, Enum):
    """策略状态"""
    DRAFT = "draft"              # 草稿
    VALIDATED = "validated"      # 已验证
    TESTED = "tested"            # 已测试
    OPTIMIZED = "optimized"      # 已优化
    DEPLOYED = "deployed"        # 已部署
    ARCHIVED = "archived"        # 已归档


@dataclass
class StrategyMetadata:
    """策略元数据"""
    author: str
    version: str
    tags: list[str] = field(default_factory=list)
    description: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Strategy:
    """策略领域模型"""
    id: str
    name: str
    code: str
    config: dict[str, Any]
    metadata: StrategyMetadata
    status: StrategyStatus = StrategyStatus.DRAFT

    def __post_init__(self):
        """验证必填字段"""
        if not self.id:
            raise ValueError("Strategy ID is required")
        if not self.name:
            raise ValueError("Strategy name is required")
        if not self.code:
            raise ValueError("Strategy code is required")
```

**Step 4: 运行测试（预期通过）**

```bash
uv run pytest langgraph/tests/unit/domain/models/test_strategy.py -v
```

Expected: PASS (3 tests)

**Step 5: 提交**

```bash
git add langgraph/domain/models/ langgraph/tests/unit/domain/models/
git commit -m "feat(domain): add Strategy domain model

- Implement Strategy and StrategyMetadata dataclasses
- Add StrategyStatus enum for lifecycle management
- Add field validation in __post_init__
- Add comprehensive unit tests"
```

---

### Task 2.2: 领域模型 - Optimization

**Files:**
- Create: `langgraph/domain/models/optimization.py`
- Create: `langgraph/tests/unit/domain/models/test_optimization.py`

**Step 1: 编写 Optimization 模型测试**

```python
# langgraph/tests/unit/domain/models/test_optimization.py
import pytest
from langgraph.domain.models.optimization import (
    OptimizationTask,
    ParameterSpace,
    OptimizationObjective,
    OptimizationResult,
    TaskStatus
)


def test_parameter_space_creation():
    """测试参数空间创建"""
    param_space = ParameterSpace(
        parameters={
            "atr_period": {"type": "int", "min": 10, "max": 30},
            "keltner_multiplier": {"type": "float", "min": 1.0, "max": 3.0}
        }
    )

    assert "atr_period" in param_space.parameters
    assert param_space.parameters["atr_period"]["type"] == "int"


def test_optimization_task_creation():
    """测试优化任务创建"""
    param_space = ParameterSpace(
        parameters={"param1": {"type": "int", "min": 1, "max": 10}}
    )

    objective = OptimizationObjective(
        primary_metric="sharpe_ratio",
        constraints={"max_drawdown": 0.2}
    )

    task = OptimizationTask(
        id="opt-001",
        strategy_id="strat-001",
        parameter_space=param_space,
        objective=objective,
        status=TaskStatus.PENDING
    )

    assert task.id == "opt-001"
    assert task.status == TaskStatus.PENDING
    assert task.objective.primary_metric == "sharpe_ratio"


def test_optimization_result():
    """测试优化结果"""
    result = OptimizationResult(
        parameters={"param1": 5},
        metrics={"sharpe_ratio": 1.5, "max_drawdown": 0.15},
        score=1.5
    )

    assert result.parameters["param1"] == 5
    assert result.metrics["sharpe_ratio"] == 1.5
    assert result.score == 1.5
```

**Step 2: 运行测试（预期失败）**

```bash
uv run pytest langgraph/tests/unit/domain/models/test_optimization.py -v
```

Expected: FAIL

**Step 3: 实现 Optimization 模型**

```python
# langgraph/domain/models/optimization.py
"""优化领域模型"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ParameterSpace:
    """参数空间定义"""
    parameters: dict[str, dict[str, Any]]

    def __post_init__(self):
        """验证参数空间"""
        if not self.parameters:
            raise ValueError("Parameter space cannot be empty")


@dataclass
class OptimizationObjective:
    """优化目标"""
    primary_metric: str
    maximize: bool = True
    constraints: dict[str, float] = field(default_factory=dict)
    secondary_metrics: list[str] = field(default_factory=list)


@dataclass
class OptimizationResult:
    """单次优化结果"""
    parameters: dict[str, Any]
    metrics: dict[str, float]
    score: float
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class OptimizationTask:
    """优化任务"""
    id: str
    strategy_id: str
    parameter_space: ParameterSpace
    objective: OptimizationObjective
    status: TaskStatus = TaskStatus.PENDING
    results: list[OptimizationResult] = field(default_factory=list)
    best_result: OptimizationResult | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def add_result(self, result: OptimizationResult) -> None:
        """添加优化结果"""
        self.results.append(result)

        # 更新最佳结果
        if self.best_result is None or result.score > self.best_result.score:
            self.best_result = result

        self.updated_at = datetime.utcnow()
```

**Step 4: 运行测试（预期通过）**

```bash
uv run pytest langgraph/tests/unit/domain/models/test_optimization.py -v
```

Expected: PASS (3 tests)

**Step 5: 提交**

```bash
git add langgraph/domain/models/optimization.py langgraph/tests/unit/domain/models/test_optimization.py
git commit -m "feat(domain): add Optimization domain models

- Implement OptimizationTask, ParameterSpace, OptimizationObjective
- Add OptimizationResult for tracking individual runs
- Add TaskStatus enum for lifecycle management
- Add comprehensive unit tests"
```

---

## 继续实现计划...

由于实现计划非常长，我将分多个部分继续编写。当前已完成：

✅ 阶段 1：基础设施搭建（5 个任务）
✅ 阶段 2：领域层 - 部分模型（2 个任务）

接下来需要继续编写：
- 阶段 2：领域层 - Backtest 模型、仓储接口、领域服务
- 阶段 3：基础设施层 - LLM 客户端
- 阶段 4：基础设施层 - 数据库
- 阶段 5-12：Agent 实现、工作流、CLI 等

**当前文档已保存，是否继续编写剩余部分？**
