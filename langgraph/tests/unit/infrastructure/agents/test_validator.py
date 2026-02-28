"""Tests for validator agent"""
import pytest
from unittest.mock import Mock
import json

from langgraph.infrastructure.agents.validator import ValidatorAgent


class TestValidatorAgent:
    """Test ValidatorAgent"""

    def test_agent_initialization(self):
        """Test validator agent initialization"""
        llm_client = Mock()
        agent = ValidatorAgent(llm_client=llm_client)

        assert agent.name == "validator"
        assert agent.llm_client == llm_client

    @pytest.mark.asyncio
    async def test_process_with_valid_code(self):
        """Test processing with valid code"""
        llm_client = Mock()
        llm_response = json.dumps({
            "is_valid": True,
            "issues": [],
            "fixes": [],
            "quality_score": 85
        })
        llm_client.generate.return_value = llm_response

        agent = ValidatorAgent(llm_client=llm_client)

        state = {"strategy_code": "class TestStrategy: pass"}
        result = await agent.process(state)

        assert "validation_result" in result
        assert result["validation_result"]["is_valid"] is True
        assert result["validation_result"]["quality_score"] == 85
        assert "messages" in result

    @pytest.mark.asyncio
    async def test_process_with_invalid_code(self):
        """Test processing with invalid code"""
        llm_client = Mock()
        llm_response = json.dumps({
            "is_valid": False,
            "issues": ["Syntax error on line 5", "Missing import"],
            "fixes": ["Fix syntax", "Add import"],
            "quality_score": 30
        })
        llm_client.generate.return_value = llm_response

        agent = ValidatorAgent(llm_client=llm_client)

        state = {"strategy_code": "invalid code"}
        result = await agent.process(state)

        assert "validation_result" in result
        assert result["validation_result"]["is_valid"] is False
        assert len(result["validation_result"]["issues"]) == 2
        assert result["validation_result"]["quality_score"] == 30

    @pytest.mark.asyncio
    async def test_process_with_no_code(self):
        """Test processing when no code provided"""
        llm_client = Mock()
        agent = ValidatorAgent(llm_client=llm_client)

        state = {}
        result = await agent.process(state)

        assert "validation_result" in result
        assert result["validation_result"]["is_valid"] is False
        assert "No strategy code to validate" in result["validation_result"]["issues"][0]

    @pytest.mark.asyncio
    async def test_process_with_previous_errors(self):
        """Test processing with previous validation errors"""
        llm_client = Mock()
        llm_response = json.dumps({
            "is_valid": True,
            "issues": [],
            "fixes": [],
            "quality_score": 90
        })
        llm_client.generate.return_value = llm_response

        agent = ValidatorAgent(llm_client=llm_client)

        state = {
            "strategy_code": "class TestStrategy: pass",
            "validation_result": {
                "is_valid": False,
                "issues": ["Previous error"],
                "fixes": [],
                "quality_score": 0
            }
        }

        result = await agent.process(state)

        assert result["validation_result"]["is_valid"] is True
        # LLM should have been called with previous errors
        assert llm_client.generate.called

    @pytest.mark.asyncio
    async def test_process_with_llm_error(self):
        """Test processing when LLM fails"""
        llm_client = Mock()
        llm_client.generate.side_effect = Exception("API error")

        agent = ValidatorAgent(llm_client=llm_client)

        state = {"strategy_code": "class TestStrategy: pass"}
        result = await agent.process(state)

        # Should handle error gracefully
        assert "validation_result" in result
        assert result["validation_result"]["is_valid"] is False
        assert "Code validation failed" in result["validation_result"]["issues"][0]

    def test_parse_response_with_valid_json(self):
        """Test parsing valid JSON response"""
        llm_client = Mock()
        agent = ValidatorAgent(llm_client=llm_client)

        response = '{"is_valid": true, "issues": [], "quality_score": 100}'
        result = agent._parse_response(response)

        assert result["is_valid"] is True
        assert result["quality_score"] == 100

    def test_parse_response_with_code_block(self):
        """Test parsing JSON in code block"""
        llm_client = Mock()
        agent = ValidatorAgent(llm_client=llm_client)

        response = '```json\n{"is_valid": false, "issues": ["error"]}\n```'
        result = agent._parse_response(response)

        assert result["is_valid"] is False
        assert len(result["issues"]) == 1
