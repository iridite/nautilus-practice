"""Tests for optimizer agent"""

import pytest
from unittest.mock import Mock
import json

from langgraph.infrastructure.agents.optimizer import OptimizerAgent
from langgraph.shared.exceptions import LLMError


class TestOptimizerAgent:
    """Test OptimizerAgent"""

    def test_agent_initialization(self):
        """Test optimizer agent initialization"""
        llm_client = Mock()
        agent = OptimizerAgent(llm_client=llm_client)

        assert agent.name == "optimizer"
        assert agent.llm_client == llm_client

    @pytest.mark.asyncio
    async def test_process_first_iteration(self):
        """Test processing first optimization iteration"""
        llm_client = Mock()
        llm_response = json.dumps(
            {
                "suggested_params": {"param1": 15, "param2": 0.5},
                "reasoning": "Test reasoning",
                "expected_improvement": "Should improve by 10%",
            }
        )
        llm_client.generate.return_value = llm_response

        agent = OptimizerAgent(llm_client=llm_client)

        state = {
            "strategy_id": "test-001",
            "parameter_space": {
                "param1": {"min": 10, "max": 20},
                "param2": {"min": 0.1, "max": 1.0},
            },
            "current_iteration": 0,
            "best_parameters": None,
            "best_score": None,
            "should_continue": True,
        }

        result = await agent.process(state)

        assert result["current_iteration"] == 1
        assert "messages" in result
        assert len(result["messages"]) == 2

    @pytest.mark.asyncio
    async def test_process_with_existing_parameters(self):
        """Test processing with existing best parameters"""
        llm_client = Mock()
        llm_response = json.dumps(
            {
                "suggested_params": {"param1": 18},
                "reasoning": "Increase param1",
                "expected_improvement": "Better performance",
            }
        )
        llm_client.generate.return_value = llm_response

        agent = OptimizerAgent(llm_client=llm_client)

        state = {
            "strategy_id": "test-002",
            "parameter_space": {"param1": {"min": 10, "max": 20}},
            "current_iteration": 3,
            "best_parameters": {"param1": 15},
            "best_score": 1.5,
            "should_continue": True,
        }

        result = await agent.process(state)

        assert result["current_iteration"] == 4
        assert "messages" in result

    @pytest.mark.asyncio
    async def test_process_with_llm_error(self):
        """Test processing when LLM fails"""
        llm_client = Mock()
        llm_client.generate.side_effect = Exception("API error")

        agent = OptimizerAgent(llm_client=llm_client)

        state = {
            "strategy_id": "test-003",
            "parameter_space": {},
            "current_iteration": 0,
            "best_parameters": None,
            "best_score": None,
            "should_continue": True,
        }

        with pytest.raises(LLMError):
            await agent.process(state)

    def test_get_default_parameters(self):
        """Test getting default parameters from space"""
        llm_client = Mock()
        agent = OptimizerAgent(llm_client=llm_client)

        parameter_space = {"param1": {"min": 10, "max": 20}, "param2": {"min": 0.0, "max": 1.0}}

        defaults = agent._get_default_parameters(parameter_space)

        assert defaults["param1"] == 15.0  # (10 + 20) / 2
        assert defaults["param2"] == 0.5  # (0 + 1) / 2

    def test_parse_response_with_valid_json(self):
        """Test parsing valid JSON response"""
        llm_client = Mock()
        agent = OptimizerAgent(llm_client=llm_client)

        response = '{"suggested_params": {"p": 1}, "reasoning": "test"}'
        result = agent._parse_response(response)

        assert "suggested_params" in result
        assert result["suggested_params"]["p"] == 1

    def test_parse_response_with_code_block(self):
        """Test parsing JSON in code block"""
        llm_client = Mock()
        agent = OptimizerAgent(llm_client=llm_client)

        response = '```json\n{"suggested_params": {}}\n```'
        result = agent._parse_response(response)

        assert "suggested_params" in result
