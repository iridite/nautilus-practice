"""Research workflow graph using LangGraph"""
import sys
from pathlib import Path
from typing import Any

# Import external langgraph.graph by temporarily modifying sys.modules and sys.path
# This prevents conflicts with the project's langgraph module

# Step 1: Remove project's langgraph from sys.modules
_original_langgraph = sys.modules.pop("langgraph", None)
_original_langgraph_infra = sys.modules.pop("langgraph.infrastructure", None)

# Step 2: Temporarily filter sys.path to exclude project directory
_project_root = str(Path(__file__).parent.parent.parent.parent)
_original_path = sys.path.copy()

try:
    # Filter out project directory and editable install paths
    sys.path = [
        p for p in sys.path
        if p != _project_root and p != '' and not p.startswith("__editable__")
    ]

    # Import external langgraph
    import langgraph.graph as _lg  # type: ignore[import-untyped]

    StateGraph = _lg.StateGraph
    END = _lg.END
finally:
    # Restore sys.path and sys.modules
    sys.path = _original_path
    if _original_langgraph is not None:
        sys.modules["langgraph"] = _original_langgraph
    if _original_langgraph_infra is not None:
        sys.modules["langgraph.infrastructure"] = _original_langgraph_infra

from langgraph.infrastructure.agents.coordinator import CoordinatorAgent
from langgraph.infrastructure.agents.researcher import ResearcherAgent
from langgraph.infrastructure.agents.validator import ValidatorAgent
from langgraph.infrastructure.llm.claude_client import ClaudeClient
from langgraph.shared.logging import get_logger

logger = get_logger(__name__)


class ResearchGraph:
    """Strategy research workflow graph"""

    def __init__(self, llm_client: ClaudeClient):
        """
        初始化研究工作流图

        Args:
            llm_client: LLM 客户端
        """
        self.llm_client = llm_client
        self.coordinator = CoordinatorAgent(llm_client=llm_client)
        self.researcher = ResearcherAgent(llm_client=llm_client)
        self.validator = ValidatorAgent(llm_client=llm_client)

        self.graph = self._build_graph()
        logger.info("Research graph initialized")

    def _build_graph(self) -> Any:  # type: ignore[type-arg]
        """
        构建工作流图

        Returns:
            StateGraph 对象
        """
        # 创建状态图
        workflow = StateGraph(dict)

        # 添加节点
        workflow.add_node("coordinator", self._coordinator_node)
        workflow.add_node("researcher", self._researcher_node)
        workflow.add_node("validator", self._validator_node)

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

    async def _coordinator_node(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        协调员节点

        Args:
            state: 当前状态

        Returns:
            更新后的状态
        """
        logger.debug("Executing coordinator node")
        return await self.coordinator.process(state)

    async def _researcher_node(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        研究员节点

        Args:
            state: 当前状态

        Returns:
            更新后的状态
        """
        logger.debug("Executing researcher node")
        return await self.researcher.process(state)

    async def _validator_node(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        验证器节点

        Args:
            state: 当前状态

        Returns:
            更新后的状态
        """
        logger.debug("Executing validator node")
        return await self.validator.process(state)

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

    async def run(self, user_input: str) -> dict[str, Any]:
        """
        运行研究工作流

        Args:
            user_input: 用户输入

        Returns:
            最终状态
        """
        logger.info("Starting research workflow", user_input_length=len(user_input))

        initial_state = {
            "user_input": user_input,
            "messages": [],
            "strategy_code": None,
            "validation_result": None,
            "backtest_result": None,
        }

        final_state = await self.graph.ainvoke(initial_state)

        logger.info("Research workflow completed", has_code=bool(final_state.get("strategy_code")))
        return final_state
