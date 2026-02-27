"""Optimization workflow graph using LangGraph"""
from pathlib import Path
from typing import Any, Optional

from infrastructure.graph._import_utils import import_external_langgraph

StateGraph, END = import_external_langgraph()  # type: ignore[misc]

from infrastructure.agents.coordinator import CoordinatorAgent
from infrastructure.agents.optimizer import OptimizerAgent
from infrastructure.backtest.engine import BacktestEngine
from infrastructure.graph._error_handling import with_retry, with_timeout
from infrastructure.graph.checkpoint import CheckpointManager
from infrastructure.llm.claude_client import ClaudeClient
from shared.logging import get_logger

logger = get_logger(__name__)


class OptimizationGraph:
    """Parameter optimization workflow graph"""

    def __init__(
        self,
        llm_client: ClaudeClient,
        backtest_engine: BacktestEngine,
        checkpoint_dir: Optional[Path] = None,
        enable_checkpoints: bool = True,
    ):
        """
        初始化优化工作流图

        Args:
            llm_client: LLM 客户端
            backtest_engine: 回测引擎
            checkpoint_dir: 检查点目录
            enable_checkpoints: 是否启用检查点
        """
        self.llm_client = llm_client
        self.backtest_engine = backtest_engine
        self.coordinator = CoordinatorAgent(llm_client=llm_client)
        self.optimizer = OptimizerAgent(llm_client=llm_client)

        # 初始化检查点管理器
        if enable_checkpoints:
            if checkpoint_dir is None:
                checkpoint_dir = Path.cwd() / ".langgraph" / "checkpoints" / "optimization"
            self.checkpoint_manager: Optional[CheckpointManager] = CheckpointManager(checkpoint_dir)
        else:
            self.checkpoint_manager = None

        self.graph = self._build_graph()
        logger.info("Optimization graph initialized", checkpoints_enabled=enable_checkpoints)

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

    @with_timeout(60.0)
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

    @with_timeout(60.0)
    @with_retry(max_retries=3)
    async def _optimizer_node(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        优化器节点

        Args:
            state: 当前状态

        Returns:
            更新后的状态
        """
        logger.debug("Executing optimizer node")
        result = await self.optimizer.process(state)

        # 保存检查点
        if self.checkpoint_manager and state.get("workflow_id"):
            self.checkpoint_manager.save_checkpoint(
                workflow_id=state["workflow_id"],
                node_name="optimizer",
                state=result,
            )

        return result

    @with_timeout(60.0)
    @with_retry(max_retries=3)
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

        logger.info(f"Running backtest for iteration {current_iteration}")

        try:
            # Validate strategy_id
            if not strategy_id or not isinstance(strategy_id, str):
                raise ValueError("Invalid strategy_id: must be a non-empty string")

            # Load strategy from database
            from langgraph.infrastructure.database.repositories import SQLAlchemyStrategyRepository
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            from langgraph.shared.config import LangGraphConfig

            # Load config from environment
            try:
                config = LangGraphConfig()
            except Exception as config_error:
                logger.error(f"Failed to load config: {config_error}")
                raise ValueError(f"Configuration error: {config_error}") from config_error

            engine = create_engine(config.database_url)
            Session = sessionmaker(bind=engine)
            session = Session()

            try:
                repo = SQLAlchemyStrategyRepository(session)
                strategy = await repo.get_by_id(strategy_id)

                if strategy is None:
                    raise ValueError(f"Strategy {strategy_id} not found in database")

                # Update strategy config with suggested parameters
                if suggested_params:
                    logger.debug(f"Updating strategy config with params: {suggested_params}")
                    strategy.config.update(suggested_params)

                # Run backtest with the loaded strategy
                backtest_result = self.backtest_engine.run(strategy=strategy)

            finally:
                session.close()

        except Exception as e:
            logger.error(f"Backtest failed: {e}", exc_info=True)
            backtest_result = {
                "error": str(e),
                "sharpe_ratio": 0.0,
                "metrics": {}
            }

        # 更新状态
        state["backtest_result"] = backtest_result

        # 更新最佳参数
        current_score = backtest_result.get("sharpe_ratio", 0.0)
        best_score = state.get("best_score")

        if best_score is None or current_score > best_score:
            state["best_score"] = current_score
            state["best_parameters"] = suggested_params
            logger.info(f"New best score: {current_score}")

        # 保存检查点
        if self.checkpoint_manager and state.get("workflow_id"):
            self.checkpoint_manager.save_checkpoint(
                workflow_id=state["workflow_id"],
                node_name="backtest",
                state=state,
                metadata={"iteration": current_iteration, "score": current_score},
            )

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
        self,
        strategy_id: str,
        parameter_space: dict[str, Any],
        max_iterations: int = 10,
        workflow_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        运行优化工作流

        Args:
            strategy_id: 策略 ID
            parameter_space: 参数空间
            max_iterations: 最大迭代次数
            workflow_id: 工作流 ID（用于检查点恢复）

        Returns:
            最终状态
        """
        import uuid

        # 生成或使用提供的 workflow_id
        if workflow_id is None:
            workflow_id = str(uuid.uuid4())

        logger.info(
            "Starting optimization workflow",
            strategy_id=strategy_id,
            max_iterations=max_iterations,
            workflow_id=workflow_id,
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
                iteration=checkpoint_data.get("metadata", {}).get("iteration"),
            )
            initial_state = checkpoint_data["state"]
            initial_state["workflow_id"] = workflow_id
        else:
            initial_state = {
                "workflow_id": workflow_id,
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

        # 清理检查点
        if self.checkpoint_manager:
            self.checkpoint_manager.archive_checkpoint(workflow_id)
            self.checkpoint_manager.delete_checkpoint(workflow_id)

        logger.info(
            "Optimization workflow completed",
            iterations=final_state.get("current_iteration"),
            best_score=final_state.get("best_score"),
        )
        return final_state  # type: ignore[no-any-return]
