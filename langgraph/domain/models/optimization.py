"""Optimization domain model.

This module defines the Optimization entity for parameter optimization tasks.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


class OptimizationStatus(Enum):
    """Optimization status enumeration."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class OptimizationTrial:
    """Represents a single optimization trial.

    Attributes:
        params: Parameter values tested in this trial
        score: Performance score achieved
        timestamp: When the trial was executed
    """

    params: dict
    score: float
    timestamp: datetime


@dataclass
class Optimization:
    """Optimization entity representing a parameter optimization task.

    Attributes:
        optimization_id: Unique identifier for the optimization
        strategy_id: ID of the strategy being optimized
        parameter_space: Parameter search space definition
        status: Current optimization status
        best_params: Best parameters found (None until completed)
        best_score: Best score achieved (None until completed)
        trials: List of all optimization trials
        error_message: Error description if optimization failed
        created_at: When the optimization was created
        updated_at: When the optimization was last updated
        started_at: When the optimization started running
        completed_at: When the optimization finished (completed or failed)
    """

    strategy_id: str
    parameter_space: dict
    optimization_id: str = field(default_factory=lambda: str(uuid4()))
    status: OptimizationStatus = field(default=OptimizationStatus.PENDING)
    best_params: dict | None = field(default=None)
    best_score: float | None = field(default=None)
    trials: list[OptimizationTrial] = field(default_factory=list)
    error_message: str | None = field(default=None)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = field(default=None)
    completed_at: datetime | None = field(default=None)

    def start(self) -> None:
        """Start the optimization.

        Raises:
            ValueError: If optimization is not in PENDING status
        """
        if self.status != OptimizationStatus.PENDING:
            raise ValueError(
                f"Cannot start optimization in {self.status.value} status. "
                "Only PENDING optimizations can be started."
            )

        self.status = OptimizationStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    def complete(self, best_params: dict, best_score: float) -> None:
        """Complete the optimization with results.

        Args:
            best_params: Best parameters found
            best_score: Best score achieved

        Raises:
            ValueError: If optimization is not running or results are invalid
        """
        if self.status != OptimizationStatus.RUNNING:
            raise ValueError("Optimization is not running")

        # Validate best_score
        if not isinstance(best_score, (int, float)) or math.isnan(best_score):
            raise ValueError(f"Invalid best_score: {best_score}")

        # Validate best_params keys are in parameter_space
        if not set(best_params.keys()).issubset(set(self.parameter_space.keys())):
            raise ValueError(
                f"best_params keys {set(best_params.keys())} "
                f"not in parameter_space {set(self.parameter_space.keys())}"
            )

        self.status = OptimizationStatus.COMPLETED
        self.best_params = best_params
        self.best_score = best_score
        self.completed_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    def fail(self, error_message: str) -> None:
        """Mark the optimization as failed.

        Args:
            error_message: Description of the failure

        Raises:
            ValueError: If optimization is not running
        """
        if self.status != OptimizationStatus.RUNNING:
            raise ValueError("Optimization is not running")

        self.status = OptimizationStatus.FAILED
        self.error_message = error_message
        self.completed_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    def add_trial(self, params: dict, score: float) -> None:
        """Add a trial result to the optimization.

        Args:
            params: Parameter values tested
            score: Performance score achieved

        Raises:
            ValueError: If optimization is not running
        """
        if self.status != OptimizationStatus.RUNNING:
            raise ValueError("Cannot add trial: optimization is not running")

        trial = OptimizationTrial(
            params=params,
            score=score,
            timestamp=datetime.now(timezone.utc),
        )
        self.trials.append(trial)
        self.updated_at = datetime.now(timezone.utc)
