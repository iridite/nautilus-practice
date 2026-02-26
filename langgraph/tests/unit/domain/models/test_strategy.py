"""
Unit tests for Strategy domain model.
"""

import pytest
from datetime import datetime
from uuid import UUID


class TestStrategyStatus:
    """Test StrategyStatus enum."""

    def test_strategy_status_values(self):
        """Test that all expected status values exist."""
        from langgraph.domain.models.strategy import StrategyStatus

        assert hasattr(StrategyStatus, "DRAFT")
        assert hasattr(StrategyStatus, "VALIDATED")
        assert hasattr(StrategyStatus, "TESTED")
        assert hasattr(StrategyStatus, "DEPLOYED")


class TestStrategyCreation:
    """Test Strategy entity creation."""

    def test_create_strategy_with_minimal_fields(self):
        """Test creating a strategy with minimal required fields."""
        from langgraph.domain.models.strategy import Strategy

        strategy = Strategy(
            name="TestStrategy",
            description="A test strategy",
            code="class TestStrategy(Strategy): pass",
            config={"param1": "value1"},
        )

        assert strategy.name == "TestStrategy"
        assert strategy.description == "A test strategy"
        assert strategy.code == "class TestStrategy(Strategy): pass"
        assert strategy.config == {"param1": "value1"}
        assert strategy.version == 1
        assert isinstance(strategy.created_at, datetime)
        assert isinstance(strategy.updated_at, datetime)

    def test_strategy_id_is_valid_uuid(self):
        """Test that strategy_id is a valid UUID."""
        from langgraph.domain.models.strategy import Strategy

        strategy = Strategy(
            name="TestStrategy",
            description="A test strategy",
            code="class TestStrategy(Strategy): pass",
            config={},
        )

        # Should be able to parse as UUID
        UUID(strategy.strategy_id)

    def test_strategy_default_status_is_draft(self):
        """Test that new strategies default to DRAFT status."""
        from langgraph.domain.models.strategy import Strategy, StrategyStatus

        strategy = Strategy(
            name="TestStrategy",
            description="A test strategy",
            code="class TestStrategy(Strategy): pass",
            config={},
        )

        assert strategy.status == StrategyStatus.DRAFT


class TestStrategyValidation:
    """Test strategy validation methods."""

    def test_validate_code_with_valid_code(self):
        """Test code validation with valid Python code."""
        from langgraph.domain.models.strategy import Strategy

        strategy = Strategy(
            name="TestStrategy",
            description="A test strategy",
            code="class TestStrategy(Strategy):\n    pass",
            config={},
        )

        # Should not raise exception
        strategy.validate_code()

    def test_validate_code_with_invalid_code(self):
        """Test code validation with invalid Python code."""
        from langgraph.domain.models.strategy import Strategy

        strategy = Strategy(
            name="TestStrategy",
            description="A test strategy",
            code="class TestStrategy(Strategy):\n    invalid syntax here!!!",
            config={},
        )

        with pytest.raises(ValueError, match="Invalid Python code"):
            strategy.validate_code()

    def test_validate_config_with_valid_config(self):
        """Test config validation with valid configuration."""
        from langgraph.domain.models.strategy import Strategy

        strategy = Strategy(
            name="TestStrategy",
            description="A test strategy",
            code="class TestStrategy(Strategy): pass",
            config={"param1": "value1", "param2": 123},
        )

        # Should not raise exception
        strategy.validate_config()

    def test_validate_config_with_empty_config(self):
        """Test config validation with empty configuration."""
        from langgraph.domain.models.strategy import Strategy

        strategy = Strategy(
            name="TestStrategy",
            description="A test strategy",
            code="class TestStrategy(Strategy): pass",
            config={},
        )

        # Should not raise exception for empty config
        strategy.validate_config()


class TestStrategyStatusTransitions:
    """Test strategy status transition methods."""

    def test_mark_as_validated(self):
        """Test marking strategy as validated."""
        from langgraph.domain.models.strategy import Strategy, StrategyStatus

        strategy = Strategy(
            name="TestStrategy",
            description="A test strategy",
            code="class TestStrategy(Strategy): pass",
            config={},
        )

        initial_updated_at = strategy.updated_at
        strategy.mark_as_validated()

        assert strategy.status == StrategyStatus.VALIDATED
        assert strategy.updated_at > initial_updated_at

    def test_mark_as_tested(self):
        """Test marking strategy as tested."""
        from langgraph.domain.models.strategy import Strategy, StrategyStatus

        strategy = Strategy(
            name="TestStrategy",
            description="A test strategy",
            code="class TestStrategy(Strategy): pass",
            config={},
        )

        strategy.mark_as_validated()
        strategy.mark_as_tested()

        assert strategy.status == StrategyStatus.TESTED

    def test_mark_as_deployed(self):
        """Test marking strategy as deployed."""
        from langgraph.domain.models.strategy import Strategy, StrategyStatus

        strategy = Strategy(
            name="TestStrategy",
            description="A test strategy",
            code="class TestStrategy(Strategy): pass",
            config={},
        )

        strategy.mark_as_validated()
        strategy.mark_as_tested()
        strategy.mark_as_deployed()

        assert strategy.status == StrategyStatus.DEPLOYED

    def test_invalid_status_transition(self):
        """Test that invalid status transitions are prevented."""
        from langgraph.domain.models.strategy import Strategy

        strategy = Strategy(
            name="TestStrategy",
            description="A test strategy",
            code="class TestStrategy(Strategy): pass",
            config={},
        )

        # Cannot deploy directly from DRAFT
        with pytest.raises(ValueError, match="Cannot transition"):
            strategy.mark_as_deployed()


class TestStrategyVersioning:
    """Test strategy version tracking."""

    def test_initial_version_is_one(self):
        """Test that initial version is 1."""
        from langgraph.domain.models.strategy import Strategy

        strategy = Strategy(
            name="TestStrategy",
            description="A test strategy",
            code="class TestStrategy(Strategy): pass",
            config={},
        )

        assert strategy.version == 1

    def test_version_increments_on_update(self):
        """Test that version increments when strategy is updated."""
        from langgraph.domain.models.strategy import Strategy

        strategy = Strategy(
            name="TestStrategy",
            description="A test strategy",
            code="class TestStrategy(Strategy): pass",
            config={},
        )

        initial_version = strategy.version
        strategy.mark_as_validated()

        assert strategy.version == initial_version + 1
