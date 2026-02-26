"""Unit tests for Optimization domain model."""

import math
from datetime import datetime, timezone
from uuid import UUID

import pytest

from langgraph.domain.models.optimization import (
    Optimization,
    OptimizationStatus,
    OptimizationTrial,
)


class TestOptimizationTrial:
    """Test OptimizationTrial dataclass."""

    def test_create_trial(self):
        """Test creating an optimization trial."""
        params = {"keltner_period": 20, "keltner_atr_multiplier": 2.0}
        score = 0.85
        timestamp = datetime.now(timezone.utc)

        trial = OptimizationTrial(
            params=params,
            score=score,
            timestamp=timestamp,
        )

        assert trial.params == params
        assert trial.score == score
        assert trial.timestamp == timestamp

    def test_trial_immutability(self):
        """Test that trial is immutable (frozen dataclass)."""
        trial = OptimizationTrial(
            params={"param1": 10},
            score=0.5,
            timestamp=datetime.now(timezone.utc),
        )

        with pytest.raises(AttributeError):
            trial.score = 0.9


class TestOptimizationStatus:
    """Test OptimizationStatus enum."""

    def test_status_values(self):
        """Test all status values exist."""
        assert OptimizationStatus.PENDING.value == "pending"
        assert OptimizationStatus.RUNNING.value == "running"
        assert OptimizationStatus.COMPLETED.value == "completed"
        assert OptimizationStatus.FAILED.value == "failed"


class TestOptimization:
    """Test Optimization entity."""

    def test_create_optimization(self):
        """Test creating a new optimization."""
        strategy_id = "strategy-123"
        parameter_space = {
            "keltner_period": [10, 20, 30],
            "keltner_atr_multiplier": [1.5, 2.0, 2.5],
        }

        optimization = Optimization(
            strategy_id=strategy_id,
            parameter_space=parameter_space,
        )

        # Verify UUID format
        UUID(optimization.optimization_id)

        assert optimization.strategy_id == strategy_id
        assert optimization.parameter_space == parameter_space
        assert optimization.status == OptimizationStatus.PENDING
        assert optimization.best_params is None
        assert optimization.best_score is None
        assert optimization.trials == []
        assert optimization.error_message is None
        assert isinstance(optimization.created_at, datetime)
        assert isinstance(optimization.updated_at, datetime)
        assert optimization.started_at is None
        assert optimization.completed_at is None

    def test_create_with_custom_id(self):
        """Test creating optimization with custom ID."""
        custom_id = "opt-custom-123"
        optimization = Optimization(
            optimization_id=custom_id,
            strategy_id="strategy-123",
            parameter_space={"param1": [1, 2, 3]},
        )

        assert optimization.optimization_id == custom_id

    def test_start_optimization(self):
        """Test starting an optimization."""
        optimization = Optimization(
            strategy_id="strategy-123",
            parameter_space={"param1": [1, 2, 3]},
        )

        assert optimization.status == OptimizationStatus.PENDING
        assert optimization.started_at is None

        optimization.start()

        assert optimization.status == OptimizationStatus.RUNNING
        assert isinstance(optimization.started_at, datetime)
        assert isinstance(optimization.updated_at, datetime)

    def test_start_already_running(self):
        """Test starting an already running optimization raises error."""
        optimization = Optimization(
            strategy_id="strategy-123",
            parameter_space={"param1": [1, 2, 3]},
        )
        optimization.start()

        with pytest.raises(ValueError, match="PENDING"):
            optimization.start()

    def test_complete_optimization(self):
        """Test completing an optimization."""
        optimization = Optimization(
            strategy_id="strategy-123",
            parameter_space={"param1": [1, 2, 3]},
        )
        optimization.start()

        best_params = {"param1": 2}
        best_score = 0.95

        optimization.complete(best_params=best_params, best_score=best_score)

        assert optimization.status == OptimizationStatus.COMPLETED
        assert optimization.best_params == best_params
        assert optimization.best_score == best_score
        assert isinstance(optimization.completed_at, datetime)

    def test_complete_not_running(self):
        """Test completing a non-running optimization raises error."""
        optimization = Optimization(
            strategy_id="strategy-123",
            parameter_space={"param1": [1, 2, 3]},
        )

        with pytest.raises(ValueError, match="not running"):
            optimization.complete(best_params={"param1": 1}, best_score=0.5)

    def test_fail_optimization(self):
        """Test failing an optimization."""
        optimization = Optimization(
            strategy_id="strategy-123",
            parameter_space={"param1": [1, 2, 3]},
        )
        optimization.start()

        error_message = "Optimization failed due to timeout"
        optimization.fail(error_message=error_message)

        assert optimization.status == OptimizationStatus.FAILED
        assert optimization.error_message == error_message
        assert isinstance(optimization.completed_at, datetime)
        assert isinstance(optimization.updated_at, datetime)

    def test_fail_not_running(self):
        """Test failing a non-running optimization raises error."""
        optimization = Optimization(
            strategy_id="strategy-123",
            parameter_space={"param1": [1, 2, 3]},
        )

        with pytest.raises(ValueError, match="not running"):
            optimization.fail(error_message="Some error")

    def test_add_trial(self):
        """Test adding a trial to optimization."""
        optimization = Optimization(
            strategy_id="strategy-123",
            parameter_space={"param1": [1, 2, 3]},
        )
        optimization.start()

        params = {"param1": 2}
        score = 0.85

        optimization.add_trial(params=params, score=score)

        assert len(optimization.trials) == 1
        assert optimization.trials[0].params == params
        assert optimization.trials[0].score == score
        assert isinstance(optimization.trials[0].timestamp, datetime)

    def test_add_multiple_trials(self):
        """Test adding multiple trials."""
        optimization = Optimization(
            strategy_id="strategy-123",
            parameter_space={"param1": [1, 2, 3]},
        )
        optimization.start()

        optimization.add_trial(params={"param1": 1}, score=0.7)
        optimization.add_trial(params={"param1": 2}, score=0.85)
        optimization.add_trial(params={"param1": 3}, score=0.6)

        assert len(optimization.trials) == 3
        assert optimization.trials[0].score == 0.7
        assert optimization.trials[1].score == 0.85
        assert optimization.trials[2].score == 0.6

    def test_add_trial_not_running(self):
        """Test adding trial to non-running optimization raises error."""
        optimization = Optimization(
            strategy_id="strategy-123",
            parameter_space={"param1": [1, 2, 3]},
        )

        with pytest.raises(ValueError, match="not running"):
            optimization.add_trial(params={"param1": 1}, score=0.5)

    def test_optimization_lifecycle(self):
        """Test complete optimization lifecycle."""
        # Create
        optimization = Optimization(
            strategy_id="strategy-123",
            parameter_space={
                "keltner_period": [10, 20, 30],
                "keltner_atr_multiplier": [1.5, 2.0, 2.5],
            },
        )
        assert optimization.status == OptimizationStatus.PENDING

        # Start
        optimization.start()
        assert optimization.status == OptimizationStatus.RUNNING

        # Add trials
        optimization.add_trial(
            params={"keltner_period": 10, "keltner_atr_multiplier": 1.5},
            score=0.65,
        )
        optimization.add_trial(
            params={"keltner_period": 20, "keltner_atr_multiplier": 2.0},
            score=0.85,
        )
        optimization.add_trial(
            params={"keltner_period": 30, "keltner_atr_multiplier": 2.5},
            score=0.72,
        )

        assert len(optimization.trials) == 3

        # Complete
        best_params = {"keltner_period": 20, "keltner_atr_multiplier": 2.0}
        best_score = 0.85
        optimization.complete(best_params=best_params, best_score=best_score)

        assert optimization.status == OptimizationStatus.COMPLETED
        assert optimization.best_params == best_params
        assert optimization.best_score == best_score
        assert optimization.completed_at is not None

    def test_optimization_failure_lifecycle(self):
        """Test optimization failure lifecycle."""
        optimization = Optimization(
            strategy_id="strategy-123",
            parameter_space={"param1": [1, 2, 3]},
        )

        optimization.start()
        optimization.add_trial(params={"param1": 1}, score=0.5)

        optimization.fail(error_message="Timeout exceeded")

        assert optimization.status == OptimizationStatus.FAILED
        assert optimization.error_message == "Timeout exceeded"
        assert len(optimization.trials) == 1
        assert optimization.completed_at is not None

    def test_start_from_completed_status(self):
        """Test starting a completed optimization raises error."""
        optimization = Optimization(
            strategy_id="strategy-123",
            parameter_space={"param1": [1, 2, 3]},
        )
        optimization.start()
        optimization.complete(best_params={"param1": 2}, best_score=0.9)

        with pytest.raises(ValueError, match="PENDING"):
            optimization.start()

    def test_start_from_failed_status(self):
        """Test starting a failed optimization raises error."""
        optimization = Optimization(
            strategy_id="strategy-123",
            parameter_space={"param1": [1, 2, 3]},
        )
        optimization.start()
        optimization.fail("Test error")

        with pytest.raises(ValueError, match="PENDING"):
            optimization.start()

    def test_complete_with_nan_score(self):
        """Test completing with NaN score raises error."""
        optimization = Optimization(
            strategy_id="strategy-123",
            parameter_space={"param1": [1, 2, 3]},
        )
        optimization.start()

        with pytest.raises(ValueError, match="Invalid best_score"):
            optimization.complete(best_params={"param1": 1}, best_score=float("nan"))

    def test_complete_with_invalid_params(self):
        """Test completing with params not in parameter_space raises error."""
        optimization = Optimization(
            strategy_id="strategy-123",
            parameter_space={"param1": [1, 2, 3]},
        )
        optimization.start()

        with pytest.raises(ValueError, match="not in parameter_space"):
            optimization.complete(best_params={"invalid_param": 1}, best_score=0.9)

    def test_fail_stores_error_message(self):
        """Test that fail() stores the error message."""
        optimization = Optimization(
            strategy_id="strategy-123",
            parameter_space={"param1": [1, 2, 3]},
        )
        optimization.start()

        error_msg = "Connection timeout"
        optimization.fail(error_msg)

        assert optimization.error_message == error_msg
        assert optimization.status == OptimizationStatus.FAILED

    def test_updated_at_changes_on_state_transitions(self):
        """Test that updated_at is updated on all state transitions."""
        optimization = Optimization(
            strategy_id="strategy-123",
            parameter_space={"param1": [1, 2, 3]},
        )

        created_time = optimization.updated_at

        # Start should update updated_at
        optimization.start()
        start_time = optimization.updated_at
        assert start_time > created_time

        # Add trial should update updated_at
        optimization.add_trial(params={"param1": 1}, score=0.5)
        trial_time = optimization.updated_at
        assert trial_time >= start_time

        # Complete should update updated_at
        optimization.complete(best_params={"param1": 2}, best_score=0.9)
        complete_time = optimization.updated_at
        assert complete_time >= trial_time
