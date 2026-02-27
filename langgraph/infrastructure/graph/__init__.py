"""Graph workflow"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langgraph.infrastructure.graph.optimize_graph import OptimizationGraph
    from langgraph.infrastructure.graph.research_graph import ResearchGraph

from langgraph.infrastructure.graph.state import AgentMessage, OptimizationState, ResearchState


def __getattr__(name: str):
    """Lazy import to avoid circular dependencies"""
    if name == "ResearchGraph":
        from langgraph.infrastructure.graph.research_graph import ResearchGraph

        return ResearchGraph
    elif name == "OptimizationGraph":
        from langgraph.infrastructure.graph.optimize_graph import OptimizationGraph

        return OptimizationGraph
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ResearchGraph",
    "OptimizationGraph",
    "AgentMessage",
    "ResearchState",
    "OptimizationState",
]


