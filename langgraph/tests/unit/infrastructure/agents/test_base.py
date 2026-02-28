"""Tests for base agent"""

import pytest
from unittest.mock import Mock
from datetime import datetime

from langgraph.infrastructure.agents.base import BaseAgent
from langgraph.infrastructure.graph.state import AgentMessage


class ConcreteAgent(BaseAgent):
    """Concrete implementation for testing"""

    async def process(self, state):
        """Test implementation"""
        self.add_message(state, "Processing")
        return state


class TestBaseAgent:
    """Test BaseAgent class"""

    def test_agent_initialization(self):
        """Test agent can be initialized"""
        llm_client = Mock()
        agent = ConcreteAgent(name="test_agent", llm_client=llm_client)

        assert agent.name == "test_agent"
        assert agent.llm_client == llm_client

    def test_create_message(self):
        """Test creating agent message"""
        llm_client = Mock()
        agent = ConcreteAgent(name="test_agent", llm_client=llm_client)

        message = agent.create_message("Test content")

        assert isinstance(message, AgentMessage)
        assert message.agent == "test_agent"
        assert message.content == "Test content"
        assert isinstance(message.timestamp, datetime)
        assert message.metadata == {}

    def test_create_message_with_metadata(self):
        """Test creating message with metadata"""
        llm_client = Mock()
        agent = ConcreteAgent(name="test_agent", llm_client=llm_client)

        metadata = {"key": "value", "count": 42}
        message = agent.create_message("Test content", metadata=metadata)

        assert message.metadata == metadata

    def test_add_message_to_state(self):
        """Test adding message to state"""
        llm_client = Mock()
        agent = ConcreteAgent(name="test_agent", llm_client=llm_client)

        state = {}
        agent.add_message(state, "Test message")

        assert "messages" in state
        assert len(state["messages"]) == 1
        assert state["messages"][0].content == "Test message"

    def test_add_multiple_messages(self):
        """Test adding multiple messages"""
        llm_client = Mock()
        agent = ConcreteAgent(name="test_agent", llm_client=llm_client)

        state = {}
        agent.add_message(state, "Message 1")
        agent.add_message(state, "Message 2")
        agent.add_message(state, "Message 3")

        assert len(state["messages"]) == 3
        assert state["messages"][0].content == "Message 1"
        assert state["messages"][1].content == "Message 2"
        assert state["messages"][2].content == "Message 3"

    @pytest.mark.asyncio
    async def test_process_method(self):
        """Test process method can be called"""
        llm_client = Mock()
        agent = ConcreteAgent(name="test_agent", llm_client=llm_client)

        state = {}
        result = await agent.process(state)

        assert "messages" in result
        assert len(result["messages"]) == 1
        assert result["messages"][0].content == "Processing"
