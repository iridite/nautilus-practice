# LangGraph Infrastructure

这是一个基于 LangGraph 的多智能体系统基础设施,用于自动化量化交易策略的研究、开发和优化。

## 架构概览

```
langgraph/infrastructure/
├── agents/          # 智能体实现
├── backtest/        # 回测引擎
├── code_gen/        # 代码生成
├── database/        # 数据持久化
├── graph/           # 工作流图
└── llm/            # LLM 客户端和提示模板
```

## 核心组件

### 1. Agents (智能体)

所有智能体都继承自 `BaseAgent`,提供统一的接口:

- **CoordinatorAgent**: 协调器,负责任务分解和流程控制
- **ResearcherAgent**: 研究员,负责策略研究和代码生成
- **OptimizerAgent**: 优化器,负责参数优化
- **ValidatorAgent**: 验证器,负责代码验证和质量评估

每个智能体都支持:
- 异步处理 (`async def process()`)
- 结构化日志记录
- 状态管理
- 错误处理

### 2. Graph Workflows (工作流图)

使用 LangGraph 的 StateGraph 实现多智能体协作:

#### ResearchGraph (研究工作流)

```
用户输入 → Coordinator → Researcher → Validator → 结束
                ↑            ↓           ↓
                └────────────┴───────────┘
                   (验证失败时循环)
```

功能:
- 根据用户需求生成策略代码
- 自动验证代码质量
- 支持迭代改进

#### OptimizationGraph (优化工作流)

```
策略代码 → Coordinator → Optimizer → Backtest → 结束
                ↑           ↓          ↓
                └───────────┴──────────┘
                  (未达到最大迭代次数时循环)
```

功能:
- 参数空间探索
- 回测评估
- 追踪最佳参数组合

### 3. LLM Integration (LLM 集成)

#### ClaudeClient
- 封装 Anthropic API
- 支持重试机制
- Token 计数
- 结构化日志

#### Prompt Templates
- `StrategyGenerationPrompt`: 策略生成提示
- `ParameterOptimizationPrompt`: 参数优化提示
- `CodeValidationPrompt`: 代码验证提示

### 4. Backtest Engine (回测引擎)

集成项目现有的回测系统:
- 支持高频和低频回测
- 性能指标计算
- 结果持久化

### 5. Code Generation (代码生成)

- `StrategyGenerator`: 从需求生成策略代码
- 支持模板化生成
- 代码格式化和验证

### 6. Database (数据库)

使用 SQLite 存储:
- 策略元数据
- 回测结果
- 优化历史
- 对话记录

## 状态管理

### ResearchState
```python
@dataclass
class ResearchState:
    user_input: str                    # 用户输入
    messages: list[AgentMessage]       # 消息历史
    strategy_code: str | None          # 生成的策略代码
    validation_result: dict | None     # 验证结果
    backtest_result: dict | None       # 回测结果
```

### OptimizationState
```python
@dataclass
class OptimizationState:
    strategy_id: str                   # 策略 ID
    current_params: dict               # 当前参数
    backtest_result: dict | None       # 回测结果
    best_params: dict | None           # 最佳参数
    best_score: float | None           # 最佳得分
    iteration: int                     # 当前迭代次数
    max_iterations: int                # 最大迭代次数
    messages: list[AgentMessage]       # 消息历史
```

## 使用示例

### 研究工作流

```python
from langgraph.infrastructure.graph.research_graph import ResearchGraph
from langgraph.infrastructure.llm.claude_client import ClaudeClient

# 初始化
llm_client = ClaudeClient(api_key="your-api-key")
research_graph = ResearchGraph(llm_client=llm_client)

# 运行研究工作流
result = await research_graph.run(
    "创建一个基于 MACD 的趋势跟踪策略"
)

print(f"生成的策略代码: {result['strategy_code']}")
print(f"验证结果: {result['validation_result']}")
```

### 优化工作流

```python
from langgraph.infrastructure.graph.optimize_graph import OptimizationGraph
from langgraph.infrastructure.llm.claude_client import ClaudeClient

# 初始化
llm_client = ClaudeClient(api_key="your-api-key")
optimize_graph = OptimizationGraph(llm_client=llm_client)

# 运行优化工作流
result = await optimize_graph.run(
    strategy_id="my-strategy",
    initial_params={"fast_period": 12, "slow_period": 26},
    max_iterations=10
)

print(f"最佳参数: {result['best_params']}")
print(f"最佳得分: {result['best_score']}")
```

## 测试

所有组件都有完整的单元测试:

```bash
# 运行所有测试
uv run pytest langgraph/tests/unit/infrastructure/ -v

# 运行特定模块测试
uv run pytest langgraph/tests/unit/infrastructure/agents/ -v
uv run pytest langgraph/tests/unit/infrastructure/graph/ -v
```

测试覆盖:
- 112 个测试用例
- 覆盖所有核心组件
- 包含异步测试
- Mock 外部依赖

## 已知问题

### 包名冲突

项目目录名 `langgraph` 与外部 LangGraph 包冲突。我们使用临时的 `sys.path` 和 `sys.modules` 修改来解决这个问题。详见 `graph/IMPORT_WORKAROUND.md`。

## 开发指南

### 添加新的智能体

1. 继承 `BaseAgent`
2. 实现 `process()` 方法
3. 添加相应的测试
4. 更新工作流图

### 添加新的工作流

1. 创建新的 Graph 类
2. 定义状态数据类
3. 实现节点函数
4. 定义路由逻辑
5. 添加测试

### 添加新的提示模板

1. 在 `prompt_templates.py` 中定义模板
2. 使用 `PromptTemplate` 类
3. 添加测试用例

## 依赖

- `langgraph>=0.2.59`: 工作流编排
- `anthropic>=0.42.0`: Claude API
- `structlog>=24.4.0`: 结构化日志
- `sqlalchemy>=2.0.0`: 数据库 ORM

## 许可证

MIT
