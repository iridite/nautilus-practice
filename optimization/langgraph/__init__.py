"""
策略优化系统
使用 LangGraph 自动优化量化交易策略
"""

from .config import (
    DEFAULT_OPTIMIZATION_TARGET,
    MAX_DEBUG_ATTEMPTS,
    MAX_ITERATIONS,
    STRATEGY_FILE_PATH,
)
from .graph import create_optimization_graph, graph
from .state import AgentState, BacktestMetrics, DebugRecord, OptimizationTarget

__version__ = "1.0.0"

__all__ = [
    # Graph
    "create_optimization_graph",
    "graph",
    # State
    "AgentState",
    "OptimizationTarget",
    "BacktestMetrics",
    "DebugRecord",
    # Config
    "DEFAULT_OPTIMIZATION_TARGET",
    "MAX_ITERATIONS",
    "MAX_DEBUG_ATTEMPTS",
    "STRATEGY_FILE_PATH",
]
