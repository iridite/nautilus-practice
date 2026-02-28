"""Coordinator agent for workflow orchestration"""

from typing import Any

from langgraph.infrastructure.agents.base import BaseAgent
from langgraph.shared.logging import get_logger

logger = get_logger(__name__)


class CoordinatorAgent(BaseAgent):
    """协调器 Agent - 负责工作流协调"""

    def __init__(self, llm_client):
        """初始化协调器 Agent"""
        super().__init__(name="coordinator", llm_client=llm_client)

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        处理工作流协调

        Args:
            state: 当前状态（ResearchState 或 OptimizationState）

        Returns:
            更新后的状态,包含协调决策
        """
        logger.info("Coordinator processing workflow")

        # 检查是研究工作流还是优化工作流
        if "user_input" in state:
            return await self._coordinate_research(state)
        elif "strategy_id" in state:
            return await self._coordinate_optimization(state)
        else:
            error_msg = "Unknown workflow type"
            logger.error(error_msg)
            self.add_message(state, error_msg)
            return state

    async def _coordinate_research(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        协调研究工作流

        Args:
            state: ResearchState 字典

        Returns:
            更新后的状态
        """
        user_input = state.get("user_input", "")
        strategy_code = state.get("strategy_code")
        validation_result = state.get("validation_result")

        logger.info("Coordinating research workflow", has_code=bool(strategy_code))

        # 初始状态：开始研究
        if not strategy_code:
            self.add_message(
                state,
                f"Initiating strategy research workflow for: {user_input}",
            )
            return state

        # 有代码但未验证：需要验证
        if strategy_code and not validation_result:
            self.add_message(state, "Strategy code generated, proceeding to validation")
            return state

        # 已验证：检查结果
        if validation_result:
            is_valid = validation_result.get("is_valid", False)
            if is_valid:
                self.add_message(
                    state,
                    "Strategy validation passed, ready for backtesting",
                    metadata={"quality_score": validation_result.get("quality_score")},
                )
            else:
                issues = validation_result.get("issues", [])
                self.add_message(
                    state,
                    f"Strategy validation failed with {len(issues)} issues",
                    metadata={"issues": issues},
                )

        return state

    async def _coordinate_optimization(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        协调优化工作流

        Args:
            state: OptimizationState 字典

        Returns:
            更新后的状态
        """
        strategy_id = state.get("strategy_id", "")
        current_iteration = state.get("current_iteration", 0)
        should_continue = state.get("should_continue", True)
        best_score = state.get("best_score")

        logger.info(
            "Coordinating optimization workflow",
            strategy_id=strategy_id,
            iteration=current_iteration,
        )

        # 初始状态
        if current_iteration == 0:
            self.add_message(
                state,
                f"Initiating parameter optimization for strategy: {strategy_id}",
            )
            return state

        # 检查是否应该继续
        if not should_continue:
            self.add_message(
                state,
                f"Optimization completed after {current_iteration} iterations",
                metadata={"best_score": best_score},
            )
            return state

        # 继续优化
        self.add_message(
            state,
            f"Continuing optimization (iteration {current_iteration})",
            metadata={"current_best_score": best_score},
        )

        return state
