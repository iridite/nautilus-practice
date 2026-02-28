"""Validator agent for code validation"""

import json
from typing import Any

from langgraph.infrastructure.agents.base import BaseAgent
from langgraph.infrastructure.llm.prompt_templates import CodeValidationPrompt
from langgraph.shared.exceptions import LLMError
from langgraph.shared.logging import get_logger

logger = get_logger(__name__)


class ValidatorAgent(BaseAgent):
    """验证器 Agent - 负责代码验证"""

    def __init__(self, llm_client):
        """初始化验证器 Agent"""
        super().__init__(name="validator", llm_client=llm_client)
        self.prompt_generator = CodeValidationPrompt()

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        处理代码验证请求

        Args:
            state: ResearchState 字典

        Returns:
            更新后的状态,包含验证结果
        """
        strategy_code = state.get("strategy_code", "")

        if not strategy_code:
            error_msg = "No strategy code to validate"
            logger.warning(error_msg)
            self.add_message(state, error_msg)
            state["validation_result"] = {
                "is_valid": False,
                "issues": [error_msg],
                "fixes": [],
                "quality_score": 0,
            }
            return state

        logger.info("Validator processing code", code_length=len(strategy_code))

        self.add_message(state, "Starting code validation")

        try:
            # 定义验证规则
            validation_rules = [
                "Code must be valid Python syntax",
                "Code must follow NautilusTrader framework conventions",
                "Code must include proper error handling",
                "Code must have clear variable names",
                "Code must include necessary imports",
            ]

            # 获取之前的错误（如果有）
            previous_errors = None
            if state.get("validation_result"):
                previous_result = state["validation_result"]
                if not previous_result.get("is_valid"):
                    previous_errors = previous_result.get("issues", [])

            # 生成提示词
            prompt = self.prompt_generator.generate(
                code=strategy_code,
                validation_rules=validation_rules,
                previous_errors=previous_errors,
            )

            # 调用 LLM
            response = self.llm_client.generate(
                prompt=prompt,
                system=CodeValidationPrompt.SYSTEM_PROMPT,
            )

            # 解析响应
            validation_result = self._parse_response(response)

            # 更新状态
            state["validation_result"] = validation_result

            is_valid = validation_result.get("is_valid", False)
            quality_score = validation_result.get("quality_score", 0)

            self.add_message(
                state,
                f"Code validation completed: {'PASSED' if is_valid else 'FAILED'} (quality: {quality_score}/100)",
                metadata={
                    "is_valid": is_valid,
                    "issues": validation_result.get("issues", []),
                    "quality_score": quality_score,
                },
            )

            logger.info(
                "Code validation completed",
                is_valid=is_valid,
                quality_score=quality_score,
                issues_count=len(validation_result.get("issues", [])),
            )

        except Exception as e:
            error_msg = f"Code validation failed: {str(e)}"
            logger.error(error_msg, error=str(e))
            self.add_message(state, error_msg, metadata={"error": str(e)})
            state["validation_result"] = {
                "is_valid": False,
                "issues": [error_msg],
                "fixes": [],
                "quality_score": 0,
            }

        return state

    def _parse_response(self, response: str) -> dict[str, Any]:
        """
        解析 LLM 响应

        Args:
            response: LLM 响应文本

        Returns:
            解析后的验证结果

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
