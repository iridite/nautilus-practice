"""Prompt templates for LLM interactions"""

from typing import Any, Optional


class PromptTemplate:
    """基础提示词模板类"""

    def __init__(self, template: str):
        """
        初始化提示词模板

        Args:
            template: 模板字符串，使用 {variable} 格式的占位符
        """
        self.template = template

    def render(self, **kwargs: Any) -> str:
        """
        渲染模板

        Args:
            **kwargs: 模板变量

        Returns:
            渲染后的字符串

        Raises:
            KeyError: 缺少必需的模板变量
        """
        return self.template.format(**kwargs)


class StrategyGenerationPrompt:
    """策略生成提示词"""

    SYSTEM_PROMPT = """You are an expert quantitative trading strategy developer.
Your task is to generate high-quality trading strategy code based on user requirements.

Guidelines:
- Generate complete, runnable Python code
- Follow NautilusTrader framework conventions
- Include proper error handling and logging
- Use clear variable names and comments
- Consider risk management and position sizing
"""

    USER_TEMPLATE = """Generate a trading strategy with the following requirements:

Requirements:
{requirements}

{market_context_section}
{reference_code_section}

Please provide:
1. Strategy name and description
2. Complete Python code implementing the strategy
3. Configuration parameters with sensible defaults
4. Brief explanation of the strategy logic

Format your response as JSON:
{{
    "name": "strategy_name",
    "description": "strategy description",
    "code": "complete Python code",
    "config": {{"param1": value1, "param2": value2}},
    "explanation": "brief explanation"
}}
"""

    def generate(
        self,
        requirements: str,
        market_context: Optional[str] = None,
        reference_code: Optional[str] = None,
    ) -> str:
        """
        生成策略生成提示词

        Args:
            requirements: 策略需求描述
            market_context: 市场背景信息（可选）
            reference_code: 参考代码（可选）

        Returns:
            完整的提示词
        """
        # 构建可选部分
        market_context_section = ""
        if market_context:
            market_context_section = f"\nMarket Context:\n{market_context}\n"

        reference_code_section = ""
        if reference_code:
            reference_code_section = f"\nReference Code:\n```python\n{reference_code}\n```\n"

        # 渲染模板
        user_prompt = self.USER_TEMPLATE.format(
            requirements=requirements,
            market_context_section=market_context_section,
            reference_code_section=reference_code_section,
        )

        return user_prompt


class ParameterOptimizationPrompt:
    """参数优化提示词"""

    SYSTEM_PROMPT = """You are an expert in trading strategy parameter optimization.
Your task is to suggest better parameter values based on current performance metrics.

Guidelines:
- Analyze current parameters and performance
- Suggest incremental improvements, not radical changes
- Consider parameter interactions and constraints
- Provide reasoning for each suggestion
"""

    USER_TEMPLATE = """Optimize parameters for the following strategy:

Strategy Code:
```python
{strategy_code}
```

Current Parameters:
{current_params}

Performance Metrics:
{performance_metrics}

{constraints_section}

Please suggest improved parameter values with reasoning.

Format your response as JSON:
{{
    "suggested_params": {{"param1": new_value1, "param2": new_value2}},
    "reasoning": "explanation of why these values should improve performance",
    "expected_improvement": "what metrics should improve and by how much"
}}
"""

    def generate(
        self,
        strategy_code: str,
        current_params: dict,
        performance_metrics: dict,
        constraints: Optional[dict] = None,
    ) -> str:
        """
        生成参数优化提示词

        Args:
            strategy_code: 策略代码
            current_params: 当前参数
            performance_metrics: 性能指标
            constraints: 参数约束（可选）

        Returns:
            完整的提示词
        """
        # 格式化参数和指标
        params_str = "\n".join(f"- {k}: {v}" for k, v in current_params.items())
        metrics_str = "\n".join(f"- {k}: {v}" for k, v in performance_metrics.items())

        # 构建约束部分
        constraints_section = ""
        if constraints:
            constraints_lines = []
            for param, bounds in constraints.items():
                if isinstance(bounds, dict):
                    min_val = bounds.get("min", "N/A")
                    max_val = bounds.get("max", "N/A")
                    constraints_lines.append(f"- {param}: min={min_val}, max={max_val}")
            if constraints_lines:
                constraints_section = "\nParameter Constraints:\n" + "\n".join(constraints_lines)

        # 渲染模板
        user_prompt = self.USER_TEMPLATE.format(
            strategy_code=strategy_code,
            current_params=params_str,
            performance_metrics=metrics_str,
            constraints_section=constraints_section,
        )

        return user_prompt


class CodeValidationPrompt:
    """代码验证提示词"""

    SYSTEM_PROMPT = """You are an expert code reviewer for trading strategies.
Your task is to validate code quality, correctness, and adherence to requirements.

Guidelines:
- Check for syntax errors and runtime issues
- Verify adherence to framework conventions
- Identify potential bugs and edge cases
- Suggest improvements for code quality
"""

    USER_TEMPLATE = """Validate the following code:

Code:
```python
{code}
```

Validation Rules:
{validation_rules}

{previous_errors_section}

Please provide:
1. Is the code valid? (yes/no)
2. List of issues found (if any)
3. Suggested fixes (if needed)

Format your response as JSON:
{{
    "is_valid": true/false,
    "issues": ["issue1", "issue2"],
    "fixes": ["fix1", "fix2"],
    "quality_score": 0-100
}}
"""

    def generate(
        self,
        code: str,
        validation_rules: list[str],
        previous_errors: Optional[list[str]] = None,
    ) -> str:
        """
        生成代码验证提示词

        Args:
            code: 待验证的代码
            validation_rules: 验证规则列表
            previous_errors: 之前的错误信息（可选）

        Returns:
            完整的提示词
        """
        # 格式化验证规则
        rules_str = "\n".join(f"- {rule}" for rule in validation_rules)

        # 构建错误部分
        previous_errors_section = ""
        if previous_errors:
            errors_str = "\n".join(f"- {error}" for error in previous_errors)
            previous_errors_section = f"\nPrevious Errors to Fix:\n{errors_str}\n"

        # 渲染模板
        user_prompt = self.USER_TEMPLATE.format(
            code=code,
            validation_rules=rules_str,
            previous_errors_section=previous_errors_section,
        )

        return user_prompt
