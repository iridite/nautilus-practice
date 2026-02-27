"""Graph workflow"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from infrastructure.graph.optimize_graph import OptimizationGraph
    from infrastructure.graph.research_graph import ResearchGraph

from infrastructure.graph._config import GraphConfig
from infrastructure.graph.state import AgentMessage, OptimizationState, ResearchState


def __getattr__(name: str):
    """Lazy import to avoid circular dependencies"""
    if name == "ResearchGraph":
        from infrastructure.graph.research_graph import ResearchGraph

        return ResearchGraph
    elif name == "OptimizationGraph":
        from infrastructure.graph.optimize_graph import OptimizationGraph

        return OptimizationGraph
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ResearchGraph",
    "OptimizationGraph",
    "AgentMessage",
    "ResearchState",
    "OptimizationState",
    "GraphConfig",
]



