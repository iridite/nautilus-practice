"""Tests for researcher agent"""
import pytest
from unittest.mock import Mock, patch
import json

from langgraph.infrastructure.agents.researcher import ResearcherAgent
from langgraph.shared.exceptions import LLMError


class TestResearcherAgent:
    """Test ResearcherAgent"""

    def test_agent_initialization(self):
        """Test researcher agent initialization"""
        llm_client = Mock()
        agent = ResearcherAgent(llm_client=llm_client)

        assert agent.name == "researcher"
        assert agent.llm_client == llm_client

    @pytest.mark.asyncio
    async def test_process_with_valid_response(self):
        """Test processing with valid LLM response"""
        llm_client = Mock()
        llm_response = json.dumps({
            "name": "TestStrategy",
            "description": "A test strategy",
            "code": "class TestStrategy: pass",
            "config": {"param1": 10},
            "explanation": "Test explanation"
        })
        llm_client.generate.return_value = llm_response

        agent = ResearcherAgent(llm_client=llm_client)

        state = {"user_input": "Create a trend following strategy"}
        result = await agent.process(state)

        assert "strategy_code" in result
        assert result["strategy_code"] == "class TestStrategy: pass"
        assert "messages" in result
        assert len(result["messages"]) == 2

    @pytest.mark.asyncio
    async def test_process_with_json_code_block(self):
        """Test processing with JSON in code block"""
        llm_client = Mock()
        llm_response = """Here is the strategy:
```json
{
    "name": "TestStrategy",
    "description": "A test strategy",
    "code": "class TestStrategy: pass",
    "config": {},
    "explanation": "Test"
}
```
"""
        llm_client.generate.return_value = llm_response

        agent = ResearcherAgent(llm_client=llm_client)

        state = {"user_input": "Create a strategy"}
        result = await agent.process(state)

        assert "strategy_code" in result
        assert result["strategy_code"] == "class TestStrategy: pass"

    @pytest.mark.asyncio
    async def test_process_with_llm_error(self):
        """Test processing when LLM fails"""
        llm_client = Mock()
        llm_client.generate.side_effect = Exception("API error")

        agent = ResearcherAgent(llm_client=llm_client)

        state = {"user_input": "Create a strategy"}

        with pytest.raises(LLMError):
            await agent.process(state)

    @pytest.mark.asyncio
    async def test_process_with_invalid_json(self):
        """Test processing with invalid JSON response"""
        llm_client = Mock()
        llm_client.generate.return_value = "This is not JSON"

        agent = ResearcherAgent(llm_client=llm_client)

        state = {"user_input": "Create a strategy"}

        with pytest.raises(LLMError):
            await agent.process(state)

    def test_parse_response_with_valid_json(self):
        """Test parsing valid JSON response"""
        llm_client = Mock()
        agent = ResearcherAgent(llm_client=llm_client)

        response = '{"name": "Test", "code": "pass"}'
        result = agent._parse_response(response)

        assert result["name"] == "Test"
        assert result["code"] == "pass"

    def test_parse_response_with_code_block(self):
        """Test parsing JSON in code block"""
        llm_client = Mock()
        agent = ResearcherAgent(llm_client=llm_client)

        response = '```json\n{"name": "Test"}\n```'
        result = agent._parse_response(response)

        assert result["name"] == "Test"
