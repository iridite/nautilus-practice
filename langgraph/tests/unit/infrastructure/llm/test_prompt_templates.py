"""Tests for prompt templates"""
import pytest
from langgraph.infrastructure.llm.prompt_templates import (
    PromptTemplate,
    StrategyGenerationPrompt,
    ParameterOptimizationPrompt,
    CodeValidationPrompt,
)


class TestPromptTemplate:
    """测试基础提示词模板"""

    def test_simple_template(self):
        """测试简单模板渲染"""
        template = PromptTemplate("Hello, {name}!")
        result = template.render(name="World")
        assert result == "Hello, World!"

    def test_multiple_variables(self):
        """测试多变量模板"""
        template = PromptTemplate("User: {user}, Age: {age}")
        result = template.render(user="Alice", age=30)
        assert result == "User: Alice, Age: 30"

    def test_missing_variable(self):
        """测试缺少变量时抛出异常"""
        template = PromptTemplate("Hello, {name}!")
        with pytest.raises(KeyError):
            template.render()


class TestStrategyGenerationPrompt:
    """测试策略生成提示词"""

    def test_generate_from_requirements(self):
        """测试从需求生成策略"""
        prompt = StrategyGenerationPrompt()
        result = prompt.generate(
            requirements="Create a momentum strategy using RSI",
            market_context="Crypto market, high volatility",
        )

        assert "momentum strategy" in result.lower()
        assert "rsi" in result.lower()
        assert "crypto" in result.lower()

    def test_generate_with_reference(self):
        """测试基于参考策略生成"""
        prompt = StrategyGenerationPrompt()
        result = prompt.generate(
            requirements="Improve the existing strategy",
            reference_code="class MyStrategy: pass",
        )

        assert "improve" in result.lower()
        assert "class MyStrategy" in result

    def test_generate_minimal(self):
        """测试最小化输入"""
        prompt = StrategyGenerationPrompt()
        result = prompt.generate(requirements="Simple moving average crossover")

        assert "moving average" in result.lower()
        assert len(result) > 100  # 应该生成详细的提示词


class TestParameterOptimizationPrompt:
    """测试参数优化提示词"""

    def test_optimize_parameters(self):
        """测试参数优化提示词生成"""
        prompt = ParameterOptimizationPrompt()
        result = prompt.generate(
            strategy_code="class Strategy: pass",
            current_params={"period": 20, "threshold": 0.5},
            performance_metrics={"sharpe": 1.2, "max_drawdown": -0.15},
        )

        assert "period" in result
        assert "20" in result
        assert "sharpe" in result.lower()

    def test_optimize_with_constraints(self):
        """测试带约束的优化"""
        prompt = ParameterOptimizationPrompt()
        result = prompt.generate(
            strategy_code="class Strategy: pass",
            current_params={"period": 20},
            performance_metrics={"sharpe": 1.2},
            constraints={"period": {"min": 10, "max": 50}},
        )

        assert "10" in result
        assert "50" in result
        assert "constraint" in result.lower()


class TestCodeValidationPrompt:
    """测试代码验证提示词"""

    def test_validate_code(self):
        """测试代码验证提示词"""
        prompt = CodeValidationPrompt()
        result = prompt.generate(
            code="def strategy(): return True",
            validation_rules=["Must inherit from Strategy", "Must implement on_bar"],
        )

        assert "def strategy()" in result
        assert "inherit from Strategy" in result
        assert "on_bar" in result

    def test_validate_with_errors(self):
        """测试带错误信息的验证"""
        prompt = CodeValidationPrompt()
        result = prompt.generate(
            code="invalid code",
            validation_rules=["Check syntax"],
            previous_errors=["SyntaxError: invalid syntax"],
        )

        assert "invalid code" in result
        assert "SyntaxError" in result
