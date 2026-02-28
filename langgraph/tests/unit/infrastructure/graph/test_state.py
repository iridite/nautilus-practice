"""Tests for LangGraph state definitions"""

from datetime import datetime
from langgraph.infrastructure.graph.state import (
    ResearchState,
    OptimizationState,
    AgentMessage,
)


class TestAgentMessage:
    """Test AgentMessage dataclass"""

    def test_agent_message_creation(self):
        """Test creating an agent message"""
        msg = AgentMessage(agent="researcher", content="Test message", timestamp=datetime.utcnow())

        assert msg.agent == "researcher"
        assert msg.content == "Test message"
        assert isinstance(msg.timestamp, datetime)

    def test_agent_message_with_metadata(self):
        """Test agent message with metadata"""
        msg = AgentMessage(
            agent="optimizer",
            content="Optimization complete",
            metadata={"iterations": 10, "best_score": 1.5},
        )

        assert msg.metadata["iterations"] == 10
        assert msg.metadata["best_score"] == 1.5


class TestResearchState:
    """Test ResearchState"""

    def test_research_state_creation(self):
        """Test creating research state"""
        state = ResearchState(
            user_input="Create a trend following strategy",
            messages=[],
            strategy_code=None,
            validation_result=None,
            backtest_result=None,
        )

        assert state.user_input == "Create a trend following strategy"
        assert state.messages == []
        assert state.strategy_code is None

    def test_research_state_with_messages(self):
        """Test research state with messages"""
        msg1 = AgentMessage(agent="coordinator", content="Starting research")
        msg2 = AgentMessage(agent="researcher", content="Analyzing market")

        state = ResearchState(
            user_input="Test input",
            messages=[msg1, msg2],
            strategy_code=None,
            validation_result=None,
            backtest_result=None,
        )

        assert len(state.messages) == 2
        assert state.messages[0].agent == "coordinator"
        assert state.messages[1].agent == "researcher"


class TestOptimizationState:
    """Test OptimizationState"""

    def test_optimization_state_creation(self):
        """Test creating optimization state"""
        state = OptimizationState(
            strategy_id="test-001",
            parameter_space={"param1": {"min": 1, "max": 10}},
            messages=[],
            current_iteration=0,
            best_parameters=None,
            best_score=None,
            should_continue=True,
        )

        assert state.strategy_id == "test-001"
        assert state.current_iteration == 0
        assert state.should_continue is True

    def test_optimization_state_with_results(self):
        """Test optimization state with results"""
        state = OptimizationState(
            strategy_id="test-002",
            parameter_space={},
            messages=[],
            current_iteration=5,
            best_parameters={"param1": 5},
            best_score=1.8,
            should_continue=False,
        )

        assert state.current_iteration == 5
        assert state.best_parameters["param1"] == 5
        assert state.best_score == 1.8
        assert state.should_continue is False
