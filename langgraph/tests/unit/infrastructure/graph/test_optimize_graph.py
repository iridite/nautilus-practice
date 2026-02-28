"""Tests for optimization graph"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from langgraph.infrastructure.graph.optimize_graph import OptimizationGraph


class TestOptimizationGraph:
    """Test OptimizationGraph"""

    def test_graph_initialization(self):
        """Test optimization graph initialization"""
        llm_client = Mock()
        backtest_engine = Mock()
        graph = OptimizationGraph(llm_client=llm_client, backtest_engine=backtest_engine)

        assert graph.llm_client == llm_client
        assert graph.backtest_engine == backtest_engine
        assert graph.coordinator is not None
        assert graph.optimizer is not None
        assert graph.graph is not None

    @pytest.mark.asyncio
    async def test_run_optimization(self):
        """Test running optimization workflow"""
        llm_client = Mock()
        backtest_engine = Mock()
        graph = OptimizationGraph(llm_client=llm_client, backtest_engine=backtest_engine)

        # Mock the graph execution
        mock_final_state = {
            "strategy_id": "test-001",
            "parameter_space": {"param1": {"min": 10, "max": 20}},
            "messages": [],
            "current_iteration": 5,
            "best_parameters": {"param1": 15},
            "best_score": 2.5,
            "should_continue": False,
            "max_iterations": 10,
        }

        with patch.object(graph.graph, "ainvoke", new_callable=AsyncMock) as mock_ainvoke:
            mock_ainvoke.return_value = mock_final_state

            result = await graph.run(
                strategy_id="test-001",
                parameter_space={"param1": {"min": 10, "max": 20}},
                max_iterations=10,
            )

            assert result["current_iteration"] == 5
            assert result["best_score"] == 2.5
            mock_ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_coordinator_node(self):
        """Test coordinator node execution"""
        llm_client = Mock()
        backtest_engine = Mock()
        graph = OptimizationGraph(llm_client=llm_client, backtest_engine=backtest_engine)

        state = {
            "strategy_id": "test-001",
            "parameter_space": {},
            "messages": [],
            "current_iteration": 0,
            "best_parameters": None,
            "best_score": None,
            "should_continue": True,
        }

        with patch.object(graph.coordinator, "process", new_callable=AsyncMock) as mock_process:
            mock_process.return_value = state

            result = await graph._coordinator_node(state)

            assert result == state
            mock_process.assert_called_once_with(state)

    @pytest.mark.asyncio
    async def test_optimizer_node(self):
        """Test optimizer node execution"""
        llm_client = Mock()
        backtest_engine = Mock()
        graph = OptimizationGraph(llm_client=llm_client, backtest_engine=backtest_engine)

        state = {
            "strategy_id": "test-001",
            "parameter_space": {"param1": {"min": 10, "max": 20}},
            "current_iteration": 0,
        }

        with patch.object(graph.optimizer, "process", new_callable=AsyncMock) as mock_process:
            mock_process.return_value = {**state, "current_iteration": 1}

            result = await graph._optimizer_node(state)

            assert result["current_iteration"] == 1
            mock_process.assert_called_once_with(state)

    @pytest.mark.asyncio
    async def test_backtest_node(self):
        """Test backtest node execution"""
        llm_client = Mock()
        backtest_engine = Mock()
        backtest_engine.run = Mock(return_value={"sharpe_ratio": 2.0})

        graph = OptimizationGraph(llm_client=llm_client, backtest_engine=backtest_engine)

        # Create a mock message with metadata
        mock_message = Mock()
        mock_message.metadata = {"suggested_params": {"param1": 15}}

        state = {
            "strategy_id": "test-001",
            "current_iteration": 1,
            "messages": [mock_message],
            "best_parameters": None,
            "best_score": None,
        }

        # Mock database operations - patch at the source module level
        with (
            patch("sqlalchemy.create_engine"),
            patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker,
            patch(
                "langgraph.infrastructure.database.repositories.SQLAlchemyStrategyRepository"
            ) as mock_repo_class,
            patch("langgraph.shared.config.LangGraphConfig") as mock_config,
        ):
            # Setup mocks
            mock_config.return_value.database_url = "sqlite:///test.db"
            mock_session = Mock()
            mock_session.close = Mock()
            mock_sessionmaker.return_value = Mock(return_value=mock_session)

            mock_strategy = Mock()
            mock_strategy.config = {}
            mock_repo = Mock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_strategy)
            mock_repo_class.return_value = mock_repo

            result = await graph._backtest_node(state)

            assert result["backtest_result"]["sharpe_ratio"] == 2.0
            assert result["best_score"] == 2.0
            assert result["best_parameters"] == {"param1": 15}
            backtest_engine.run.assert_called_once_with(strategy=mock_strategy)
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_backtest_node_updates_best_score(self):
        """Test backtest node updates best score when improved"""
        llm_client = Mock()
        backtest_engine = Mock()
        backtest_engine.run = Mock(return_value={"sharpe_ratio": 3.0})

        graph = OptimizationGraph(llm_client=llm_client, backtest_engine=backtest_engine)

        mock_message = Mock()
        mock_message.metadata = {"suggested_params": {"param1": 18}}

        state = {
            "strategy_id": "test-001",
            "current_iteration": 2,
            "messages": [mock_message],
            "best_parameters": {"param1": 15},
            "best_score": 2.0,
        }

        # Mock database operations - patch at the source module level
        with (
            patch("sqlalchemy.create_engine"),
            patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker,
            patch(
                "langgraph.infrastructure.database.repositories.SQLAlchemyStrategyRepository"
            ) as mock_repo_class,
            patch("langgraph.shared.config.LangGraphConfig") as mock_config,
        ):
            mock_config.return_value.database_url = "sqlite:///test.db"
            mock_session = Mock()
            mock_session.close = Mock()
            mock_sessionmaker.return_value = Mock(return_value=mock_session)

            mock_strategy = Mock()
            mock_strategy.config = {}
            mock_repo = Mock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_strategy)
            mock_repo_class.return_value = mock_repo

            result = await graph._backtest_node(state)

            assert result["best_score"] == 3.0
            assert result["best_parameters"] == {"param1": 18}

    @pytest.mark.asyncio
    async def test_backtest_node_keeps_best_score(self):
        """Test backtest node keeps best score when not improved"""
        llm_client = Mock()
        backtest_engine = Mock()
        backtest_engine.run = Mock(return_value={"sharpe_ratio": 1.5})

        graph = OptimizationGraph(llm_client=llm_client, backtest_engine=backtest_engine)

        mock_message = Mock()
        mock_message.metadata = {"suggested_params": {"param1": 12}}

        state = {
            "strategy_id": "test-001",
            "current_iteration": 2,
            "messages": [mock_message],
            "best_parameters": {"param1": 15},
            "best_score": 2.0,
        }

        # Mock database operations
        with (
            patch("sqlalchemy.create_engine"),
            patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker,
            patch(
                "langgraph.infrastructure.database.repositories.SQLAlchemyStrategyRepository"
            ) as mock_repo_class,
            patch("langgraph.shared.config.LangGraphConfig") as mock_config,
        ):
            mock_config.return_value.database_url = "sqlite:///test.db"
            mock_session = Mock()
            mock_session.close = Mock()
            mock_sessionmaker.return_value = Mock(return_value=mock_session)

            mock_strategy = Mock()
            mock_strategy.config = {}
            mock_repo = Mock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_strategy)
            mock_repo_class.return_value = mock_repo

            result = await graph._backtest_node(state)

            assert result["best_score"] == 2.0
            assert result["best_parameters"] == {"param1": 15}

    @pytest.mark.asyncio
    async def test_backtest_node_strategy_not_found(self):
        """Test backtest node handles strategy not found error"""
        llm_client = Mock()
        backtest_engine = Mock()

        graph = OptimizationGraph(llm_client=llm_client, backtest_engine=backtest_engine)

        mock_message = Mock()
        mock_message.metadata = {"suggested_params": {"param1": 15}}

        state = {
            "strategy_id": "nonexistent-001",
            "current_iteration": 1,
            "messages": [mock_message],
            "best_parameters": None,
            "best_score": None,
        }

        # Mock database operations - strategy not found
        with (
            patch("sqlalchemy.create_engine"),
            patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker,
            patch(
                "langgraph.infrastructure.database.repositories.SQLAlchemyStrategyRepository"
            ) as mock_repo_class,
            patch("langgraph.shared.config.LangGraphConfig") as mock_config,
        ):
            mock_config.return_value.database_url = "sqlite:///test.db"
            mock_session = Mock()
            mock_session.close = Mock()
            mock_sessionmaker.return_value = Mock(return_value=mock_session)

            mock_repo = Mock()
            mock_repo.get_by_id = AsyncMock(return_value=None)  # Strategy not found
            mock_repo_class.return_value = mock_repo

            result = await graph._backtest_node(state)

            # Should return error result with sharpe_ratio of 0.0
            assert "error" in result["backtest_result"]
            assert "not found" in result["backtest_result"]["error"]
            assert result["backtest_result"]["sharpe_ratio"] == 0.0
            # Best score becomes 0.0 because None < 0.0 in the comparison
            assert result["best_score"] == 0.0
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_backtest_node_database_error(self):
        """Test backtest node handles database connection error"""
        llm_client = Mock()
        backtest_engine = Mock()

        graph = OptimizationGraph(llm_client=llm_client, backtest_engine=backtest_engine)

        mock_message = Mock()
        mock_message.metadata = {"suggested_params": {"param1": 15}}

        state = {
            "strategy_id": "test-001",
            "current_iteration": 1,
            "messages": [mock_message],
            "best_parameters": None,
            "best_score": None,
        }

        # Mock database operations - connection error
        with (
            patch("sqlalchemy.create_engine") as mock_create_engine,
            patch("langgraph.shared.config.LangGraphConfig") as mock_config,
        ):
            mock_config.return_value.database_url = "sqlite:///test.db"
            mock_create_engine.side_effect = Exception("Database connection failed")

            result = await graph._backtest_node(state)

            # Should return error result
            assert "error" in result["backtest_result"]
            assert "Database connection failed" in result["backtest_result"]["error"]
            assert result["backtest_result"]["sharpe_ratio"] == 0.0
            # Best score becomes 0.0 because None < 0.0 in the comparison
            assert result["best_score"] == 0.0

    def test_route_after_coordinator_continue(self):
        """Test routing when should continue"""
        llm_client = Mock()
        backtest_engine = Mock()
        graph = OptimizationGraph(llm_client=llm_client, backtest_engine=backtest_engine)

        state = {"should_continue": True}

        route = graph._route_after_coordinator(state)

        assert route == "optimizer"

    def test_route_after_coordinator_end(self):
        """Test routing when should end"""
        llm_client = Mock()
        backtest_engine = Mock()
        graph = OptimizationGraph(llm_client=llm_client, backtest_engine=backtest_engine)

        state = {"should_continue": False}

        route = graph._route_after_coordinator(state)

        assert route == "end"
