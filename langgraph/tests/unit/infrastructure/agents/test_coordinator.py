"""Tests for coordinator agent"""
import pytest
from unittest.mock import Mock

from langgraph.infrastructure.agents.coordinator import CoordinatorAgent


class TestCoordinatorAgent:
    """Test CoordinatorAgent"""

    def test_agent_initialization(self):
        """Test coordinator agent initialization"""
        llm_client = Mock()
        agent = CoordinatorAgent(llm_client=llm_client)

        assert agent.name == "coordinator"
        assert agent.llm_client == llm_client

    @pytest.mark.asyncio
    async def test_coordinate_research_initial_state(self):
        """Test coordinating research workflow in initial state"""
        llm_client = Mock()
        agent = CoordinatorAgent(llm_client=llm_client)

        state = {
            "user_input": "Create a trend following strategy",
            "messages": [],
            "strategy_code": None,
            "validation_result": None,
            "backtest_result": None
        }

        result = await agent.process(state)

        assert "messages" in result
        assert len(result["messages"]) == 1
        assert "Initiating strategy research" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_coordinate_research_with_code(self):
        """Test coordinating research workflow with generated code"""
        llm_client = Mock()
        agent = CoordinatorAgent(llm_client=llm_client)

        state = {
            "user_input": "Create a strategy",
            "messages": [],
            "strategy_code": "class TestStrategy: pass",
            "validation_result": None,
            "backtest_result": None
        }

        result = await agent.process(state)

        assert "messages" in result
        assert "proceeding to validation" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_coordinate_research_validation_passed(self):
        """Test coordinating research workflow when validation passed"""
        llm_client = Mock()
        agent = CoordinatorAgent(llm_client=llm_client)

        state = {
            "user_input": "Create a strategy",
            "messages": [],
            "strategy_code": "class TestStrategy: pass",
            "validation_result": {
                "is_valid": True,
                "quality_score": 85
            },
            "backtest_result": None
        }

        result = await agent.process(state)

        assert "messages" in result
        assert "validation passed" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_coordinate_research_validation_failed(self):
        """Test coordinating research workflow when validation failed"""
        llm_client = Mock()
        agent = CoordinatorAgent(llm_client=llm_client)

        state = {
            "user_input": "Create a strategy",
            "messages": [],
            "strategy_code": "invalid code",
            "validation_result": {
                "is_valid": False,
                "issues": ["Syntax error", "Missing import"]
            },
            "backtest_result": None
        }

        result = await agent.process(state)

        assert "messages" in result
        assert "validation failed" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_coordinate_optimization_initial_state(self):
        """Test coordinating optimization workflow in initial state"""
        llm_client = Mock()
        agent = CoordinatorAgent(llm_client=llm_client)

        state = {
            "strategy_id": "test-001",
            "parameter_space": {},
            "messages": [],
            "current_iteration": 0,
            "best_parameters": None,
            "best_score": None,
            "should_continue": True
        }

        result = await agent.process(state)

        assert "messages" in result
        assert "Initiating parameter optimization" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_coordinate_optimization_in_progress(self):
        """Test coordinating optimization workflow in progress"""
        llm_client = Mock()
        agent = CoordinatorAgent(llm_client=llm_client)

        state = {
            "strategy_id": "test-002",
            "parameter_space": {},
            "messages": [],
            "current_iteration": 5,
            "best_parameters": {"param1": 15},
            "best_score": 1.8,
            "should_continue": True
        }

        result = await agent.process(state)

        assert "messages" in result
        assert "Continuing optimization" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_coordinate_optimization_completed(self):
        """Test coordinating optimization workflow when completed"""
        llm_client = Mock()
        agent = CoordinatorAgent(llm_client=llm_client)

        state = {
            "strategy_id": "test-003",
            "parameter_space": {},
            "messages": [],
            "current_iteration": 10,
            "best_parameters": {"param1": 18},
            "best_score": 2.5,
            "should_continue": False
        }

        result = await agent.process(state)

        assert "messages" in result
        assert "Optimization completed" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_coordinate_unknown_workflow(self):
        """Test coordinating unknown workflow type"""
        llm_client = Mock()
        agent = CoordinatorAgent(llm_client=llm_client)

        state = {"unknown_field": "value"}

        result = await agent.process(state)

        assert "messages" in result
        assert "Unknown workflow type" in result["messages"][0].content
