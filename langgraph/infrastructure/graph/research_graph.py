"""Research workflow graph using LangGraph"""

from pathlib import Path
from typing import Any, Optional

from infrastructure.graph._import_utils import import_external_langgraph

StateGraph, END = import_external_langgraph()  # type: ignore[misc]

from infrastructure.agents.coordinator import CoordinatorAgent
from infrastructure.agents.researcher import ResearcherAgent
from infrastructure.agents.validator import ValidatorAgent
from infrastructure.graph._error_handling import with_retry, with_timeout
from infrastructure.graph.checkpoint import CheckpointManager
from infrastructure.llm.claude_client import ClaudeClient
from shared.logging import get_logger

logger = get_logger(__name__)


class ResearchGraph:
    """Strategy research workflow graph"""

    def __init__(
        self,
        llm_client: ClaudeClient,
        checkpoint_dir: Optional[Path] = None,
        enable_checkpoints: bool = True,
    ):
        """
        初始化研究工作流图

        Args:
            llm_client: LLM 客户端
            checkpoint_dir: 检查点目录
            enable_checkpoints: 是否启用检查点
        """
        self.llm_client = llm_client
        self.coordinator = CoordinatorAgent(llm_client=llm_client)
        self.researcher = ResearcherAgent(llm_client=llm_client)
        self.validator = ValidatorAgent(llm_client=llm_client)

        # 初始化检查点管理器
        if enable_checkpoints:
            if checkpoint_dir is None:
                checkpoint_dir = Path.cwd() / ".langgraph" / "checkpoints" / "research"
            self.checkpoint_manager: Optional[CheckpointManager] = CheckpointManager(checkpoint_dir)
        else:
            self.checkpoint_manager = None

        self.graph = self._build_graph()
        logger.info("Research graph initialized", checkpoints_enabled=enable_checkpoints)

    def _build_graph(self) -> Any:
        """
        构建工作流图

        Returns:
            StateGraph 对象
        """
        # 创建状态图
        workflow = StateGraph(dict)  # type: ignore[type-var]

        # 添加节点
        workflow.add_node("coordinator", self._coordinator_node)  # type: ignore[type-var]
        workflow.add_node("researcher", self._researcher_node)  # type: ignore[type-var]
        workflow.add_node("validator", self._validator_node)  # type: ignore[type-var]

        # 设置入口点
        workflow.set_entry_point("coordinator")

        # 添加条件边
        workflow.add_conditional_edges(
            "coordinator",
            self._route_after_coordinator,
            {
                "researcher": "researcher",
                "validator": "validator",
                "end": END,
            },
        )

        # 研究员 -> 协调员
        workflow.add_edge("researcher", "coordinator")

        # 验证器 -> 协调员
        workflow.add_edge("validator", "coordinator")

        return workflow.compile()

    @with_timeout(30.0)
    @with_retry(max_retries=3)
    async def _coordinator_node(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        协调员节点

        Args:
            state: 当前状态

        Returns:
            更新后的状态
        """
        logger.debug("Executing coordinator node")
        result = await self.coordinator.process(state)

        # 保存检查点
        if self.checkpoint_manager and state.get("workflow_id"):
            self.checkpoint_manager.save_checkpoint(
                workflow_id=state["workflow_id"],
                node_name="coordinator",
                state=result,
            )

        return result

    @with_timeout(30.0)
    @with_retry(max_retries=3)
    async def _researcher_node(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        研究员节点

        Args:
            state: 当前状态

        Returns:
            更新后的状态
        """
        logger.debug("Executing researcher node")
        result = await self.researcher.process(state)

        # 保存检查点
        if self.checkpoint_manager and state.get("workflow_id"):
            self.checkpoint_manager.save_checkpoint(
                workflow_id=state["workflow_id"],
                node_name="researcher",
                state=result,
            )

        return result

    @with_timeout(30.0)
    @with_retry(max_retries=3)
    async def _validator_node(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        验证器节点

        Args:
            state: 当前状态

        Returns:
            更新后的状态
        """
        logger.debug("Executing validator node")
        result = await self.validator.process(state)

        # 保存检查点
        if self.checkpoint_manager and state.get("workflow_id"):
            self.checkpoint_manager.save_checkpoint(
                workflow_id=state["workflow_id"],
                node_name="validator",
                state=result,
            )

        return result

    def _route_after_coordinator(self, state: dict[str, Any]) -> str:
        """
        协调员之后的路由逻辑

        Args:
            state: 当前状态

        Returns:
            下一个节点名称
        """
        # 如果没有策略代码,去研究员
        if not state.get("strategy_code"):
            logger.debug("Routing to researcher: no strategy code")
            return "researcher"

        # 如果有策略代码但没有验证结果,去验证器
        if not state.get("validation_result"):
            logger.debug("Routing to validator: no validation result")
            return "validator"

        # 如果验证失败,去研究员重新生成
        validation_result = state.get("validation_result", {})
        if not validation_result.get("is_valid", False):
            logger.debug("Routing to researcher: validation failed")
            return "researcher"

        # 验证通过,结束
        logger.debug("Routing to end: validation passed")
        return "end"

    async def run(self, user_input: str, workflow_id: Optional[str] = None) -> dict[str, Any]:
        """
        运行研究工作流

        Args:
            user_input: 用户输入
            workflow_id: 工作流 ID（用于检查点恢复）

        Returns:
            最终状态
        """
        import uuid

        # 生成或使用提供的 workflow_id
        if workflow_id is None:
            workflow_id = str(uuid.uuid4())

        logger.info(
            "Starting research workflow", user_input_length=len(user_input), workflow_id=workflow_id
        )

        # 尝试从检查点恢复
        checkpoint_data = None
        if self.checkpoint_manager:
            checkpoint_data = self.checkpoint_manager.load_checkpoint(workflow_id)

        if checkpoint_data:
            logger.info(
                "Resuming from checkpoint",
                workflow_id=workflow_id,
                node_name=checkpoint_data.get("node_name"),
            )
            initial_state = checkpoint_data["state"]
            initial_state["workflow_id"] = workflow_id
        else:
            initial_state: dict[str, Any] = {
                "workflow_id": workflow_id,
                "user_input": user_input,
                "messages": [],
                "strategy_code": None,
                "validation_result": None,
                "backtest_result": None,
            }

        final_state = await self.graph.ainvoke(initial_state)

        # 清理检查点
        if self.checkpoint_manager:
            self.checkpoint_manager.archive_checkpoint(workflow_id)
            self.checkpoint_manager.delete_checkpoint(workflow_id)

        logger.info("Research workflow completed", has_code=bool(final_state.get("strategy_code")))
        return final_state  # type: ignore[no-any-return]
