"""Tests for research graph"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from langgraph.infrastructure.graph.research_graph import ResearchGraph


class TestResearchGraph:
    """Test ResearchGraph"""

    def test_graph_initialization(self):
        """Test research graph initialization"""
        llm_client = Mock()
        graph = ResearchGraph(llm_client=llm_client)

        assert graph.llm_client == llm_client
        assert graph.coordinator is not None
        assert graph.researcher is not None
        assert graph.validator is not None
        assert graph.graph is not None

    @pytest.mark.asyncio
    async def test_run_with_valid_strategy(self):
        """Test running research workflow with valid strategy"""
        llm_client = Mock()
        graph = ResearchGraph(llm_client=llm_client)

        # Mock the graph execution
        mock_final_state = {
            "user_input": "Create a trend following strategy",
            "messages": [],
            "strategy_code": "class TestStrategy: pass",
            "validation_result": {"is_valid": True, "quality_score": 85},
            "backtest_result": None,
        }

        with patch.object(graph.graph, "ainvoke", new_callable=AsyncMock) as mock_ainvoke:
            mock_ainvoke.return_value = mock_final_state

            result = await graph.run("Create a trend following strategy")

            assert result["strategy_code"] == "class TestStrategy: pass"
            assert result["validation_result"]["is_valid"] is True
            mock_ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_coordinator_node(self):
        """Test coordinator node execution"""
        llm_client = Mock()
        graph = ResearchGraph(llm_client=llm_client)

        state = {
            "user_input": "Create a strategy",
            "messages": [],
            "strategy_code": None,
            "validation_result": None,
            "backtest_result": None,
        }

        with patch.object(graph.coordinator, "process", new_callable=AsyncMock) as mock_process:
            mock_process.return_value = state

            result = await graph._coordinator_node(state)

            assert result == state
            mock_process.assert_called_once_with(state)

    @pytest.mark.asyncio
    async def test_researcher_node(self):
        """Test researcher node execution"""
        llm_client = Mock()
        graph = ResearchGraph(llm_client=llm_client)

        state = {"user_input": "Create a strategy"}

        with patch.object(graph.researcher, "process", new_callable=AsyncMock) as mock_process:
            mock_process.return_value = {**state, "strategy_code": "class TestStrategy: pass"}

            result = await graph._researcher_node(state)

            assert result["strategy_code"] == "class TestStrategy: pass"
            mock_process.assert_called_once_with(state)

    @pytest.mark.asyncio
    async def test_validator_node(self):
        """Test validator node execution"""
        llm_client = Mock()
        graph = ResearchGraph(llm_client=llm_client)

        state = {"strategy_code": "class TestStrategy: pass"}

        with patch.object(graph.validator, "process", new_callable=AsyncMock) as mock_process:
            mock_process.return_value = {
                **state,
                "validation_result": {"is_valid": True, "quality_score": 90},
            }

            result = await graph._validator_node(state)

            assert result["validation_result"]["is_valid"] is True
            mock_process.assert_called_once_with(state)

    def test_route_after_coordinator_no_code(self):
        """Test routing when no strategy code exists"""
        llm_client = Mock()
        graph = ResearchGraph(llm_client=llm_client)

        state = {"strategy_code": None}

        route = graph._route_after_coordinator(state)

        assert route == "researcher"

    def test_route_after_coordinator_no_validation(self):
        """Test routing when code exists but no validation"""
        llm_client = Mock()
        graph = ResearchGraph(llm_client=llm_client)

        state = {"strategy_code": "class TestStrategy: pass", "validation_result": None}

        route = graph._route_after_coordinator(state)

        assert route == "validator"

    def test_route_after_coordinator_validation_failed(self):
        """Test routing when validation failed"""
        llm_client = Mock()
        graph = ResearchGraph(llm_client=llm_client)

        state = {
            "strategy_code": "invalid code",
            "validation_result": {"is_valid": False, "issues": ["Syntax error"]},
        }

        route = graph._route_after_coordinator(state)

        assert route == "researcher"

    def test_route_after_coordinator_validation_passed(self):
        """Test routing when validation passed"""
        llm_client = Mock()
        graph = ResearchGraph(llm_client=llm_client)

        state = {
            "strategy_code": "class TestStrategy: pass",
            "validation_result": {"is_valid": True, "quality_score": 85},
        }

        route = graph._route_after_coordinator(state)

        assert route == "end"
