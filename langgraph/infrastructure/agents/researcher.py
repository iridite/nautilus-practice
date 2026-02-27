"""Researcher agent for strategy research"""
import json
from typing import Any

from langgraph.infrastructure.agents.base import BaseAgent
from langgraph.infrastructure.llm.prompt_templates import StrategyGenerationPrompt
from langgraph.shared.exceptions import LLMError
from langgraph.shared.logging import get_logger

logger = get_logger(__name__)


class ResearcherAgent(BaseAgent):
    """研究员 Agent - 负责策略研究和代码生成"""

    def __init__(self, llm_client):
        """初始化研究员 Agent"""
        super().__init__(name="researcher", llm_client=llm_client)
        self.prompt_generator = StrategyGenerationPrompt()

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        处理策略研究请求

        Args:
            state: ResearchState 字典

        Returns:
            更新后的状态,包含生成的策略代码
        """
        user_input = state.get("user_input", "")

        logger.info("Researcher processing request", input_length=len(user_input))

        self.add_message(state, f"Starting strategy research for: {user_input}")

        try:
            # 生成提示词
            prompt = self.prompt_generator.generate(
                requirements=user_input,
                market_context=None,
                reference_code=None,
            )

            # 调用 LLM
            response = self.llm_client.generate(
                prompt=prompt,
                system=StrategyGenerationPrompt.SYSTEM_PROMPT,
            )

            # 解析响应
            strategy_data = self._parse_response(response)

            # 更新状态
            state["strategy_code"] = strategy_data.get("code", "")

            self.add_message(
                state,
                f"Strategy generated: {strategy_data.get('name', 'Unknown')}",
                metadata={
                    "strategy_name": strategy_data.get("name"),
                    "description": strategy_data.get("description"),
                    "config": strategy_data.get("config"),
                },
            )

            logger.info("Strategy research completed", strategy_name=strategy_data.get("name"))

        except Exception as e:
            error_msg = f"Strategy research failed: {str(e)}"
            logger.error(error_msg, error=str(e))
            self.add_message(state, error_msg, metadata={"error": str(e)})
            raise LLMError(error_msg) from e

        return state

    def _parse_response(self, response: str) -> dict[str, Any]:
        """
        解析 LLM 响应

        Args:
            response: LLM 响应文本

        Returns:
            解析后的策略数据

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
