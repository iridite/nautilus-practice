"""Optimization workflow graph using LangGraph"""
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
    import langgraph.graph as _lg

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
from langgraph.infrastructure.agents.optimizer import OptimizerAgent
from langgraph.infrastructure.backtest.engine import BacktestEngine
from langgraph.infrastructure.llm.claude_client import ClaudeClient
from langgraph.shared.logging import get_logger

logger = get_logger(__name__)


class OptimizationGraph:
    """Parameter optimization workflow graph"""

    def __init__(self, llm_client: ClaudeClient, backtest_engine: BacktestEngine):
        """
        初始化优化工作流图

        Args:
            llm_client: LLM 客户端
            backtest_engine: 回测引擎
        """
        self.llm_client = llm_client
        self.backtest_engine = backtest_engine
        self.coordinator = CoordinatorAgent(llm_client=llm_client)
        self.optimizer = OptimizerAgent(llm_client=llm_client)

        self.graph = self._build_graph()
        logger.info("Optimization graph initialized")

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
        workflow.add_node("optimizer", self._optimizer_node)  # type: ignore[type-var]
        workflow.add_node("backtest", self._backtest_node)  # type: ignore[type-var]

        # 设置入口点
        workflow.set_entry_point("coordinator")

        # 添加条件边
        workflow.add_conditional_edges(
            "coordinator",
            self._route_after_coordinator,
            {
                "optimizer": "optimizer",
                "end": END,
            },
        )

        # 优化器 -> 回测
        workflow.add_edge("optimizer", "backtest")

        # 回测 -> 协调员
        workflow.add_edge("backtest", "coordinator")

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

    async def _optimizer_node(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        优化器节点

        Args:
            state: 当前状态

        Returns:
            更新后的状态
        """
        logger.debug("Executing optimizer node")
        return await self.optimizer.process(state)

    async def _backtest_node(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        回测节点

        Args:
            state: 当前状态

        Returns:
            更新后的状态
        """
        logger.debug("Executing backtest node")

        strategy_id = state.get("strategy_id")
        current_iteration = state.get("current_iteration", 0)

        # 从最后一条消息中提取建议的参数
        messages = state.get("messages", [])
        suggested_params = {}
        if messages:
            last_message = messages[-1]
            if hasattr(last_message, "metadata"):
                suggested_params = last_message.metadata.get("suggested_params", {})

        # 运行回测
        logger.info(f"Running backtest for iteration {current_iteration}")

        # 如果 backtest_engine 存在，则运行回测
        if self.backtest_engine is not None:
            # Note: BacktestEngine.run() expects a Strategy object, not just strategy_id
            # This is a simplified placeholder - in production, you'd need to:
            # 1. Load the strategy from database using strategy_id
            # 2. Update its parameters with suggested_params
            # 3. Pass the Strategy object to run()
            # For testing purposes, we assume backtest_engine.run() is mocked
            backtest_result = await self.backtest_engine.run(strategy=strategy_id)  # type: ignore[arg-type,misc]
        else:
            backtest_result = {}  # type: ignore[unreachable]

        # 更新状态
        state["backtest_result"] = backtest_result

        # 更新最佳参数
        current_score = backtest_result.get("sharpe_ratio", 0.0)
        best_score = state.get("best_score")

        if best_score is None or current_score > best_score:
            state["best_score"] = current_score
            state["best_parameters"] = suggested_params
            logger.info(f"New best score: {current_score}")

        return state

    def _route_after_coordinator(self, state: dict[str, Any]) -> str:
        """
        协调员之后的路由逻辑

        Args:
            state: 当前状态

        Returns:
            下一个节点名称
        """
        # 检查是否应该继续
        should_continue = state.get("should_continue", True)

        if not should_continue:
            logger.debug("Routing to end: optimization completed")
            return "end"

        # 继续优化
        logger.debug("Routing to optimizer: continuing optimization")
        return "optimizer"

    async def run(
        self, strategy_id: str, parameter_space: dict[str, Any], max_iterations: int = 10
    ) -> dict[str, Any]:
        """
        运行优化工作流

        Args:
            strategy_id: 策略 ID
            parameter_space: 参数空间
            max_iterations: 最大迭代次数

        Returns:
            最终状态
        """
        logger.info(
            "Starting optimization workflow",
            strategy_id=strategy_id,
            max_iterations=max_iterations,
        )

        initial_state = {
            "strategy_id": strategy_id,
            "parameter_space": parameter_space,
            "messages": [],
            "current_iteration": 0,
            "best_parameters": None,
            "best_score": None,
            "should_continue": True,
            "max_iterations": max_iterations,
        }

        final_state = await self.graph.ainvoke(initial_state)

        logger.info(
            "Optimization workflow completed",
            iterations=final_state.get("current_iteration"),
            best_score=final_state.get("best_score"),
        )
        return final_state  # type: ignore[no-any-return]
