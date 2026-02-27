"""Optimizer agent for parameter optimization"""
import json
from typing import Any

from langgraph.infrastructure.agents.base import BaseAgent
from langgraph.infrastructure.llm.prompt_templates import ParameterOptimizationPrompt
from langgraph.shared.exceptions import LLMError
from langgraph.shared.logging import get_logger

logger = get_logger(__name__)


class OptimizerAgent(BaseAgent):
    """优化器 Agent - 负责参数优化"""

    def __init__(self, llm_client):
        """初始化优化器 Agent"""
        super().__init__(name="optimizer", llm_client=llm_client)
        self.prompt_generator = ParameterOptimizationPrompt()

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        处理参数优化请求

        Args:
            state: OptimizationState 字典

        Returns:
            更新后的状态,包含优化建议
        """
        strategy_id = state.get("strategy_id", "")
        parameter_space = state.get("parameter_space", {})
        current_iteration = state.get("current_iteration", 0)

        logger.info(
            "Optimizer processing request",
            strategy_id=strategy_id,
            iteration=current_iteration,
        )

        self.add_message(
            state,
            f"Starting parameter optimization iteration {current_iteration}",
        )

        try:
            # 获取当前参数和性能指标
            best_parameters = state.get("best_parameters", {})
            best_score = state.get("best_score")

            # 如果是第一次迭代,使用参数空间的默认值
            if not best_parameters:
                best_parameters = self._get_default_parameters(parameter_space)
                performance_metrics = {"score": 0.0, "note": "Initial parameters"}
            else:
                performance_metrics = {
                    "score": best_score,
                    "iteration": current_iteration,
                }

            # 生成提示词
            prompt = self.prompt_generator.generate(
                strategy_code=f"# Strategy ID: {strategy_id}",
                current_params=best_parameters,
                performance_metrics=performance_metrics,
                constraints=parameter_space,
            )

            # 调用 LLM
            response = self.llm_client.generate(
                prompt=prompt,
                system=ParameterOptimizationPrompt.SYSTEM_PROMPT,
            )

            # 解析响应
            optimization_data = self._parse_response(response)

            # 更新状态
            suggested_params = optimization_data.get("suggested_params", {})

            self.add_message(
                state,
                f"Optimization suggestion generated for iteration {current_iteration}",
                metadata={
                    "suggested_params": suggested_params,
                    "reasoning": optimization_data.get("reasoning"),
                    "expected_improvement": optimization_data.get("expected_improvement"),
                },
            )

            # 更新迭代计数
            state["current_iteration"] = current_iteration + 1

            logger.info(
                "Parameter optimization completed",
                iteration=current_iteration,
                suggested_params=suggested_params,
            )

        except Exception as e:
            error_msg = f"Parameter optimization failed: {str(e)}"
            logger.error(error_msg, error=str(e))
            self.add_message(state, error_msg, metadata={"error": str(e)})
            raise LLMError(error_msg) from e

        return state

    def _get_default_parameters(self, parameter_space: dict[str, Any]) -> dict[str, Any]:
        """
        从参数空间获取默认参数值

        Args:
            parameter_space: 参数空间定义

        Returns:
            默认参数字典
        """
        defaults = {}
        for param, bounds in parameter_space.items():
            if isinstance(bounds, dict):
                min_val = bounds.get("min", 0)
                max_val = bounds.get("max", 100)
                # 使用中间值作为默认值
                defaults[param] = (min_val + max_val) / 2
        return defaults

    def _parse_response(self, response: str) -> dict[str, Any]:
        """
        解析 LLM 响应

        Args:
            response: LLM 响应文本

        Returns:
            解析后的优化数据

        Raises:
            LLMError: 解析失败
        """
        try:
            # 尝试直接解析 JSON
            return json.loads(response)
        except json.JSONDecodeError:
            # 尝试提取 JSON 代码块
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                json_str = response[start:end].strip()
                return json.loads(json_str)
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                json_str = response[start:end].strip()
                return json.loads(json_str)
            else:
                raise LLMError(f"Failed to parse LLM response as JSON: {response[:200]}")
