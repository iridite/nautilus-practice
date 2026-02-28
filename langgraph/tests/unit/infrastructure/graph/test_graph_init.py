"""Tests for graph module lazy imports"""

import pytest
from langgraph.infrastructure.graph import (
    ResearchGraph,
    OptimizationGraph,
    AgentMessage,
    ResearchState,
    OptimizationState,
    GraphConfig,
)


class TestLazyImports:
    """Test lazy import mechanism"""

    def test_research_graph_import(self):
        """Test that ResearchGraph can be imported"""
        assert ResearchGraph is not None
        assert hasattr(ResearchGraph, "__name__")
        assert ResearchGraph.__name__ == "ResearchGraph"

    def test_optimization_graph_import(self):
        """Test that OptimizationGraph can be imported"""
        assert OptimizationGraph is not None
        assert hasattr(OptimizationGraph, "__name__")
        assert OptimizationGraph.__name__ == "OptimizationGraph"

    def test_agent_message_import(self):
        """Test that AgentMessage can be imported"""
        assert AgentMessage is not None
        assert hasattr(AgentMessage, "__name__")

    def test_research_state_import(self):
        """Test that ResearchState can be imported"""
        assert ResearchState is not None
        assert hasattr(ResearchState, "__name__")

    def test_optimization_state_import(self):
        """Test that OptimizationState can be imported"""
        assert OptimizationState is not None
        assert hasattr(OptimizationState, "__name__")

    def test_graph_config_import(self):
        """Test that GraphConfig can be imported"""
        assert GraphConfig is not None
        assert hasattr(GraphConfig, "__name__")

    def test_invalid_attribute_raises_error(self):
        """Test that accessing invalid attribute raises AttributeError"""
        import langgraph.infrastructure.graph as graph_module

        with pytest.raises(AttributeError, match="has no attribute 'NonExistentClass'"):
            _ = graph_module.NonExistentClass

    def test_all_exports(self):
        """Test that __all__ contains expected exports"""
        import langgraph.infrastructure.graph as graph_module

        expected = [
            "ResearchGraph",
            "OptimizationGraph",
            "AgentMessage",
            "ResearchState",
            "OptimizationState",
            "GraphConfig",
        ]
        assert graph_module.__all__ == expected


class TestGraphInstantiation:
    """Test that graph classes can be instantiated"""

    def test_research_graph_class_exists(self):
        """Test that ResearchGraph class exists and is callable"""
        assert callable(ResearchGraph)
        assert hasattr(ResearchGraph, "__init__")

    def test_optimization_graph_class_exists(self):
        """Test that OptimizationGraph class exists and is callable"""
        assert callable(OptimizationGraph)
        assert hasattr(OptimizationGraph, "__init__")
