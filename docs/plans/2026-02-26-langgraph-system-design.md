# LangGraph 策略自动化系统设计文档

**日期**: 2026-02-26
**版本**: 1.0
**状态**: 已批准

## 1. 概述

### 1.1 目标

构建基于 LangGraph 的策略自动化研究和优化系统，实现：

- **策略研究与生成（A）**：AI 自动研究市场特征，生成新策略代码
- **参数优化（B）**：智能优化现有策略的参数
- **端到端自动化（C）**：从策略研究到参数优化的完整流程（后期目标）

### 1.2 核心特性

- 多 Agent 协作架构（Coordinator、Researcher、Optimizer、Validator）
- 混合输入模式（自然语言、市场观察、参考策略改进）
- 自适应参数优化（智能搜索 + 策略理解 + 结构建议）
- 混合交互模式（全自动、检查点确认、实时对话）
- 轻度集成现有系统，逐步深度集成
- Claude API 驱动，预留多模型支持
- 数据库记录管理（SQLite），支持历史查询

### 1.3 技术栈

- **LangGraph**: Agent 编排和状态管理
- **Claude API**: Opus（复杂推理）+ Sonnet（快速迭代）
- **SQLAlchemy**: ORM 和数据库访问
- **SQLite**: 运行记录存储
- **Pydantic**: 配置验证和数据模型
- **structlog**: 结构化日志
- **pytest**: 测试框架

---

## 2. 架构设计

### 2.1 分层架构（Clean Architecture）

```
┌─────────────────────────────────────────────────────┐
│  Presentation Layer (表示层)                        │
│  - CLI 命令接口                                      │
│  - 输出格式化                                        │
│  - 交互式界面                                        │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  Application Layer (应用层)                         │
│  - Use Cases (用例编排)                             │
│  - DTO (数据传输对象)                               │
│  - 接口定义                                          │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  Domain Layer (领域层)                              │
│  - 领域模型 (Strategy, Optimization, Backtest)      │
│  - 领域服务 (业务规则)                              │
│  - 仓储接口 (抽象)                                  │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  Infrastructure Layer (基础设施层)                  │
│  - LangGraph Agent 实现                             │
│  - LLM 客户端封装                                   │
│  - 数据库实现                                        │
│  - 回测引擎适配器                                    │
└─────────────────────────────────────────────────────┘
```

### 2.2 多 Agent 协作架构

```
                    ┌─────────────────┐
                    │  Coordinator    │
                    │   (协调者)      │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ↓              ↓              ↓
      ┌──────────┐   ┌──────────┐   ┌──────────┐
      │Researcher│   │Optimizer │   │Validator │
      │ (研究员) │   │ (优化器) │   │ (验证器) │
      └──────────┘   └──────────┘   └──────────┘
```

**Agent 职责**：

- **Coordinator Agent**: 管理工作流、路由任务、用户交互
- **Researcher Agent**: 策略研究、市场分析、代码生成
- **Optimizer Agent**: 参数优化、回测调度、结果评估
- **Validator Agent**: 代码验证、测试执行、质量检查

### 2.3 工作流示例

**场景 1：策略研究**
```
用户输入 → Coordinator → Researcher (分析+生成代码)
         → Validator (验证+测试) → 返回结果
```

**场景 2：参数优化**
```
用户输入 → Coordinator → Optimizer (智能搜索参数空间)
         → 并行回测 → 评估结果 → 返回最优参数
```

**场景 3：端到端（未来）**
```
用户输入 → Coordinator → Researcher → Validator
         → Optimizer → Validator → 返回完整策略
```

---

## 3. 目录结构

```
nautilus-practice/
├── langgraph/
│   ├── __init__.py
│   │
│   ├── domain/                      # 领域层（核心业务逻辑）
│   │   ├── models/                  # 领域模型
│   │   │   ├── strategy.py          # Strategy, StrategyMetadata
│   │   │   ├── optimization.py      # OptimizationTask, ParameterSpace
│   │   │   ├── backtest.py          # BacktestResult, PerformanceMetrics
│   │   │   └── research.py          # ResearchTask, MarketInsight
│   │   ├── services/                # 领域服务（业务规则）
│   │   │   ├── strategy_analyzer.py # 策略分析逻辑
│   │   │   ├── parameter_selector.py # 参数选择逻辑
│   │   │   └── performance_evaluator.py # 性能评估逻辑
│   │   └── repositories/            # 仓储接口（抽象）
│   │       ├── strategy_repository.py
│   │       ├── backtest_repository.py
│   │       └── optimization_repository.py
│   │
│   ├── application/                 # 应用层（用例编排）
│   │   ├── use_cases/               # 用例实现
│   │   │   ├── research_strategy.py # 策略研究用例
│   │   │   ├── optimize_parameters.py # 参数优化用例
│   │   │   ├── validate_strategy.py # 策略验证用例
│   │   │   └── end_to_end_workflow.py # 端到端用例（未来）
│   │   ├── dto/                     # 数据传输对象
│   │   │   ├── requests.py          # 请求 DTO
│   │   │   └── responses.py         # 响应 DTO
│   │   └── interfaces/              # 应用层接口
│   │       └── llm_service.py       # LLM 服务接口
│   │
│   ├── infrastructure/              # 基础设施层（技术实现）
│   │   ├── agents/                  # LangGraph Agent 实现
│   │   │   ├── base.py              # BaseAgent（共享逻辑）
│   │   │   ├── coordinator.py
│   │   │   ├── researcher.py
│   │   │   ├── optimizer.py
│   │   │   └── validator.py
│   │   ├── graph/                   # LangGraph 工作流
│   │   │   ├── nodes.py             # 图节点定义
│   │   │   ├── edges.py             # 图边定义
│   │   │   ├── research_graph.py    # 研究工作流
│   │   │   ├── optimize_graph.py    # 优化工作流
│   │   │   └── state.py             # 状态定义
│   │   ├── llm/                     # LLM 客户端
│   │   │   ├── claude_client.py     # Claude API 封装
│   │   │   ├── prompt_templates.py  # 提示词模板
│   │   │   └── response_parser.py   # 响应解析
│   │   ├── database/                # 数据库实现
│   │   │   ├── models.py            # SQLAlchemy 模型
│   │   │   ├── repositories/        # 仓储实现
│   │   │   │   ├── strategy_repo_impl.py
│   │   │   │   ├── backtest_repo_impl.py
│   │   │   │   └── optimization_repo_impl.py
│   │   │   └── migrations/          # Alembic 迁移
│   │   ├── backtest/                # 回测引擎适配器
│   │   │   ├── adapter.py           # 适配现有回测引擎
│   │   │   └── parallel_runner.py   # 并行回测调度
│   │   └── code_gen/                # 代码生成工具
│   │       ├── strategy_template.py # 策略代码模板
│   │       ├── validator.py         # 代码验证器
│   │       └── formatter.py         # 代码格式化
│   │
│   ├── presentation/                # 表示层（用户接口）
│   │   ├── cli/                     # CLI 接口
│   │   │   ├── commands.py          # CLI 命令
│   │   │   ├── formatters.py        # 输出格式化
│   │   │   └── interactive.py       # 交互式界面
│   │   └── api/                     # REST API（未来）
│   │
│   ├── shared/                      # 共享模块
│   │   ├── config.py                # 配置管理
│   │   ├── logging.py               # 日志配置
│   │   ├── exceptions.py            # 自定义异常
│   │   ├── constants.py             # 常量定义
│   │   └── utils/                   # 工具函数
│   │
│   └── tests/                       # 测试（镜像源码结构）
│       ├── unit/                    # 单元测试
│       ├── integration/             # 集成测试
│       ├── e2e/                     # 端到端测试
│       └── fixtures/                # 测试数据
│
├── output/
│   └── langgraph/
│       ├── strategies/              # 生成的策略代码
│       ├── reports/                 # Markdown 报告
│       ├── logs/                    # 运行日志
│       └── database.db              # SQLite 数据库
│
└── docs/
    └── langgraph/                   # LangGraph 文档
        ├── architecture.md          # 架构文档
        ├── user_guide.md            # 用户指南
        └── api_reference.md         # API 参考
```

---

## 4. 核心设计原则

### 4.1 SOLID 原则

#### 单一职责原则（SRP）
- **Agent**：只负责 LLM 交互和决策
- **Service**：只负责业务逻辑
- **Repository**：只负责数据持久化
- **Use Case**：只负责编排流程

#### 开闭原则（OCP）
```python
# 易于扩展新的 LLM 提供商
class LLMService(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        pass

class ClaudeLLMService(LLMService):
    def generate(self, prompt: str) -> str:
        # Claude 实现
        pass
```

#### 依赖倒置原则（DIP）
```python
# domain/repositories/strategy_repository.py (接口)
class StrategyRepository(ABC):
    @abstractmethod
    def save(self, strategy: Strategy) -> str:
        pass

# infrastructure/database/repositories/strategy_repo_impl.py (实现)
class StrategyRepositoryImpl(StrategyRepository):
    def save(self, strategy: Strategy) -> str:
        # SQLAlchemy 实现
        pass
```

### 4.2 错误处理

```python
# shared/exceptions.py
class LangGraphError(Exception):
    """基础异常"""
    pass

class StrategyGenerationError(LangGraphError):
    """策略生成失败"""
    pass

class OptimizationError(LangGraphError):
    """优化失败"""
    pass

class BacktestError(LangGraphError):
    """回测失败"""
    pass
```

### 4.3 可观测性

```python
# 使用结构化日志
import structlog

logger = structlog.get_logger()

logger.info(
    "optimization_started",
    task_id=task_id,
    strategy_name=strategy_name,
    parameter_space=param_space
)
```

### 4.4 配置管理

```python
# shared/config.py
from pydantic import BaseModel

class LangGraphConfig(BaseModel):
    llm_provider: str = "claude"
    claude_api_key: str
    max_parallel_backtests: int = 4
    database_url: str = "sqlite:///output/langgraph/database.db"
    log_level: str = "INFO"

    class Config:
        env_prefix = "LANGGRAPH_"  # 从环境变量读取
```

### 4.5 测试策略

- **单元测试**：测试每个类和函数的独立逻辑
- **集成测试**：测试 Agent 和工作流的协作
- **端到端测试**：测试完整的用户场景
- **Mock 策略**：使用 Mock LLM 避免 API 调用成本

```python
# tests/unit/domain/services/test_parameter_selector.py
def test_select_next_parameters():
    selector = ParameterSelector()
    history = [...]
    next_params = selector.select_next(history)
    assert next_params is not None

# tests/integration/test_research_flow.py
@pytest.mark.integration
def test_research_flow_with_mock_llm(mock_llm_service):
    # 使用 Mock LLM 测试完整流程
    pass
```

---

## 5. 数据模型

### 5.1 领域模型

#### Strategy（策略）
```python
@dataclass
class Strategy:
    id: str
    name: str
    description: str
    code: str
    config: dict
    metadata: StrategyMetadata
    created_at: datetime
    updated_at: datetime
```

#### OptimizationTask（优化任务）
```python
@dataclass
class OptimizationTask:
    id: str
    strategy_id: str
    parameter_space: ParameterSpace
    objective: OptimizationObjective
    status: TaskStatus
    results: list[OptimizationResult]
    created_at: datetime
```

#### BacktestResult（回测结果）
```python
@dataclass
class BacktestResult:
    id: str
    strategy_id: str
    parameters: dict
    metrics: PerformanceMetrics
    trades: list[Trade]
    created_at: datetime
```

### 5.2 数据库模型（SQLAlchemy）

```python
class StrategyModel(Base):
    __tablename__ = "strategies"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    code = Column(Text, nullable=False)
    config = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    # 关系
    backtest_results = relationship("BacktestResultModel", back_populates="strategy")
    optimization_tasks = relationship("OptimizationTaskModel", back_populates="strategy")
```

---

## 6. 工作流设计

### 6.1 策略研究工作流

```python
# infrastructure/graph/research_graph.py
from langgraph.graph import StateGraph

def create_research_graph():
    graph = StateGraph(ResearchState)

    # 节点
    graph.add_node("understand_request", understand_request_node)
    graph.add_node("analyze_market", analyze_market_node)
    graph.add_node("generate_strategy", generate_strategy_node)
    graph.add_node("validate_code", validate_code_node)
    graph.add_node("run_backtest", run_backtest_node)

    # 边
    graph.add_edge("understand_request", "analyze_market")
    graph.add_edge("analyze_market", "generate_strategy")
    graph.add_edge("generate_strategy", "validate_code")
    graph.add_conditional_edges(
        "validate_code",
        lambda state: "run_backtest" if state.code_valid else "generate_strategy"
    )

    graph.set_entry_point("understand_request")
    graph.set_finish_point("run_backtest")

    return graph.compile()
```

### 6.2 参数优化工作流

```python
# infrastructure/graph/optimize_graph.py
def create_optimize_graph():
    graph = StateGraph(OptimizeState)

    # 节点
    graph.add_node("analyze_strategy", analyze_strategy_node)
    graph.add_node("select_parameters", select_parameters_node)
    graph.add_node("run_parallel_backtests", run_parallel_backtests_node)
    graph.add_node("evaluate_results", evaluate_results_node)
    graph.add_node("decide_next_step", decide_next_step_node)

    # 边
    graph.add_edge("analyze_strategy", "select_parameters")
    graph.add_edge("select_parameters", "run_parallel_backtests")
    graph.add_edge("run_parallel_backtests", "evaluate_results")
    graph.add_conditional_edges(
        "decide_next_step",
        lambda state: "select_parameters" if state.should_continue else END
    )

    return graph.compile()
```

---

## 7. CLI 接口设计

### 7.1 命令结构

```bash
# 策略研究
uv run python main.py research --mode natural --input "基于布林带的反转策略"
uv run python main.py research --mode market-driven --symbols BTCUSDT,ETHUSDT
uv run python main.py research --mode improve --base-strategy keltner_rs_breakout

# 参数优化
uv run python main.py optimize --strategy keltner_rs_breakout --mode auto
uv run python main.py optimize --strategy keltner_rs_breakout --params "atr_period,keltner_multiplier"

# 端到端（未来）
uv run python main.py e2e --input "趋势跟踪策略" --auto-optimize

# 查询历史
uv run python main.py history --type research
uv run python main.py history --type optimization --strategy keltner_rs_breakout
```

### 7.2 交互模式

```python
# presentation/cli/interactive.py
class InteractiveMode:
    def run(self):
        """交互式对话模式"""
        print("LangGraph 策略助手（输入 'exit' 退出）")

        while True:
            user_input = input("\n你: ")
            if user_input.lower() == "exit":
                break

            response = self.coordinator.process(user_input)
            print(f"\n助手: {response}")
```

---

## 8. 实现路线图

### 阶段 1：基础设施（Week 1-2）
- [ ] 项目结构搭建
- [ ] 配置管理（Pydantic + 环境变量）
- [ ] 日志系统（structlog）
- [ ] 异常体系
- [ ] 数据库模型（SQLAlchemy）
- [ ] 数据库迁移（Alembic）

### 阶段 2：领域层（Week 2-3）
- [ ] 领域模型定义
- [ ] 仓储接口定义
- [ ] 领域服务实现
  - [ ] StrategyAnalyzer
  - [ ] ParameterSelector
  - [ ] PerformanceEvaluator

### 阶段 3：基础设施层 - LLM（Week 3-4）
- [ ] Claude API 客户端封装
- [ ] 提示词模板系统
- [ ] 响应解析器
- [ ] 多模型支持接口（预留）

### 阶段 4：基础设施层 - 回测（Week 4-5）
- [ ] 回测引擎适配器
- [ ] 并行回测调度器
- [ ] 结果收集和聚合

### 阶段 5：Researcher Agent（Week 5-7）
- [ ] BaseAgent 实现
- [ ] Researcher Agent 实现
- [ ] 策略代码生成
- [ ] 代码模板系统
- [ ] 研究工作流（LangGraph）

### 阶段 6：Validator Agent（Week 7-8）
- [ ] Validator Agent 实现
- [ ] 代码验证器
- [ ] 测试执行器
- [ ] 质量检查规则

### 阶段 7：Optimizer Agent（Week 8-10）
- [ ] Optimizer Agent 实现
- [ ] 参数空间定义
- [ ] 智能参数选择算法
- [ ] 优化工作流（LangGraph）

### 阶段 8：Coordinator Agent（Week 10-11）
- [ ] Coordinator Agent 实现
- [ ] 任务路由逻辑
- [ ] 用户交互管理
- [ ] 混合模式支持

### 阶段 9：应用层（Week 11-12）
- [ ] Use Case 实现
  - [ ] ResearchStrategyUseCase
  - [ ] OptimizeParametersUseCase
  - [ ] ValidateStrategyUseCase
- [ ] DTO 定义

### 阶段 10：表示层（Week 12-13）
- [ ] CLI 命令实现
- [ ] 输出格式化
- [ ] 交互式界面
- [ ] 集成到 main.py

### 阶段 11：测试（Week 13-14）
- [ ] 单元测试（覆盖率 > 80%）
- [ ] 集成测试
- [ ] 端到端测试
- [ ] Mock 和 Fixture

### 阶段 12：文档和优化（Week 14-15）
- [ ] 架构文档
- [ ] 用户指南
- [ ] API 参考
- [ ] 性能优化
- [ ] 代码审查

### 阶段 13：端到端工作流（Week 15-16，可选）
- [ ] E2E Use Case 实现
- [ ] E2E 工作流（LangGraph）
- [ ] 完整流程测试

---

## 9. 风险和挑战

### 9.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| LLM 生成代码质量不稳定 | 高 | 多轮验证 + 自动修复 + 人工审查 |
| 参数优化耗时过长 | 中 | 智能剪枝 + 并行执行 + 早停机制 |
| LangGraph 学习曲线陡峭 | 中 | 从简单工作流开始 + 参考官方示例 |
| 数据库性能瓶颈 | 低 | 索引优化 + 批量写入 + 未来迁移 PostgreSQL |

### 9.2 业务风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 生成的策略过拟合 | 高 | 多时间段验证 + Walk-forward 测试 |
| 优化目标不合理 | 中 | 多目标平衡 + 用户可配置 |
| 用户期望过高 | 中 | 明确系统能力边界 + 渐进式交付 |

---

## 10. 成功指标

### 10.1 功能指标

- [ ] 能够根据自然语言描述生成可运行的策略代码
- [ ] 生成的策略代码通过率 > 80%（首次生成或一次修复后）
- [ ] 参数优化找到的最优参数比随机搜索提升 > 20%
- [ ] 优化速度比网格搜索快 > 3x

### 10.2 质量指标

- [ ] 单元测试覆盖率 > 80%
- [ ] 集成测试覆盖核心工作流
- [ ] 代码符合 PEP 8 和项目规范
- [ ] 文档完整（架构 + 用户指南 + API）

### 10.3 性能指标

- [ ] 策略生成时间 < 5 分钟（包括验证和简单回测）
- [ ] 参数优化支持 4+ 并行回测
- [ ] 数据库查询响应时间 < 100ms

---

## 11. 未来扩展

### 11.1 短期（3-6 个月）

- 端到端工作流完整实现
- 可视化面板（HTML 报告）
- 分布式回测支持
- 更多 LLM 提供商（OpenAI、本地模型）

### 11.2 中期（6-12 个月）

- REST API 接口
- Web UI 界面
- 策略市场（分享和复用策略）
- 实时监控和告警

### 11.3 长期（12+ 个月）

- 多策略组合优化
- 强化学习集成
- 自动化实盘部署
- 社区生态建设

---

## 12. 参考资料

- [LangGraph 官方文档](https://langchain-ai.github.io/langgraph/)
- [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [SOLID 原则](https://en.wikipedia.org/wiki/SOLID)
- [NautilusTrader 文档](https://nautilustrader.io/)
- [SQLAlchemy 文档](https://docs.sqlalchemy.org/)

---

## 附录 A：术语表

- **Agent**: LangGraph 中的智能体，负责特定任务
- **Use Case**: 应用层的用例，编排业务流程
- **Repository**: 仓储模式，抽象数据访问
- **DTO**: Data Transfer Object，数据传输对象
- **DIP**: Dependency Inversion Principle，依赖倒置原则
- **SRP**: Single Responsibility Principle，单一职责原则

---

**文档结束**
