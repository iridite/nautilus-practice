"""LangGraph state definitions"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class AgentMessage:
    """Message from an agent"""
    agent: str
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchState:
    """State for strategy research workflow"""
    user_input: str
    messages: list[AgentMessage]
    strategy_code: str | None
    validation_result: dict[str, Any] | None
    backtest_result: dict[str, Any] | None


@dataclass
class OptimizationState:
    """State for parameter optimization workflow"""
    strategy_id: str
    parameter_space: dict[str, Any]
    messages: list[AgentMessage]
    current_iteration: int
    best_parameters: dict[str, Any] | None
    best_score: float | None
    should_continue: bool
