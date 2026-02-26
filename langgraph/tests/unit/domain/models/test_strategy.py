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

        # Should raise exception for empty config
        with pytest.raises(ValueError, match="cannot be empty"):
            strategy.validate_config()

    def test_validate_code_requires_class_definition(self):
        """Test that validate_code requires at least one class."""
        from langgraph.domain.models.strategy import Strategy

        strategy = Strategy(
            name="TestStrategy",
            description="A test strategy",
            code="x = 1\ny = 2",  # No class definition
            config={"param": "value"},
        )

        with pytest.raises(ValueError, match="must define at least one class"):
            strategy.validate_code()


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
            config={"param": "value"},
        )

        strategy.mark_as_validated()
        strategy.mark_as_tested()

        assert strategy.status == StrategyStatus.TESTED

    def test_mark_as_tested_idempotent(self):
        """Test that mark_as_tested is idempotent."""
        from langgraph.domain.models.strategy import Strategy, StrategyStatus

        strategy = Strategy(
            name="TestStrategy",
            description="A test strategy",
            code="class TestStrategy(Strategy): pass",
            config={"param": "value"},
        )

        strategy.mark_as_validated()
        strategy.mark_as_tested()

        # Should not raise error when called again
        strategy.mark_as_tested()
        assert strategy.status == StrategyStatus.TESTED

    def test_mark_as_deployed(self):
        """Test marking strategy as deployed."""
        from langgraph.domain.models.strategy import Strategy, StrategyStatus

        strategy = Strategy(
            name="TestStrategy",
            description="A test strategy",
            code="class TestStrategy(Strategy): pass",
            config={"param": "value"},
        )

        strategy.mark_as_validated()
        strategy.mark_as_tested()
        strategy.mark_as_deployed()

        assert strategy.status == StrategyStatus.DEPLOYED

    def test_mark_as_deployed_idempotent(self):
        """Test that mark_as_deployed is idempotent."""
        from langgraph.domain.models.strategy import Strategy, StrategyStatus

        strategy = Strategy(
            name="TestStrategy",
            description="A test strategy",
            code="class TestStrategy(Strategy): pass",
            config={"param": "value"},
        )

        strategy.mark_as_validated()
        strategy.mark_as_tested()
        strategy.mark_as_deployed()

        # Should not raise error when called again
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
        """Test that version increments when strategy code/config is updated."""
        from langgraph.domain.models.strategy import Strategy

        strategy = Strategy(
            name="TestStrategy",
            description="A test strategy",
            code="class TestStrategy(Strategy): pass",
            config={"param": "value"},
        )

        initial_version = strategy.version
        strategy.update_code("class NewStrategy(Strategy): pass")

        assert strategy.version == initial_version + 1

    def test_version_not_incremented_on_status_change(self):
        """Test that version does not change on status transitions."""
        from langgraph.domain.models.strategy import Strategy

        strategy = Strategy(
            name="TestStrategy",
            description="A test strategy",
            code="class TestStrategy(Strategy): pass",
            config={"param": "value"},
        )

        initial_version = strategy.version
        strategy.mark_as_validated()
        assert strategy.version == initial_version

        strategy.mark_as_tested()
        assert strategy.version == initial_version

        strategy.mark_as_deployed()
        assert strategy.version == initial_version

    def test_update_code_resets_status_to_draft(self):
        """Test that updating code resets status to DRAFT."""
        from langgraph.domain.models.strategy import Strategy, StrategyStatus

        strategy = Strategy(
            name="TestStrategy",
            description="A test strategy",
            code="class TestStrategy(Strategy): pass",
            config={"param": "value"},
        )

        strategy.mark_as_validated()
        strategy.update_code("class NewStrategy(Strategy): pass")

        assert strategy.status == StrategyStatus.DRAFT

    def test_update_config_resets_status_to_draft(self):
        """Test that updating config resets status to DRAFT."""
        from langgraph.domain.models.strategy import Strategy, StrategyStatus

        strategy = Strategy(
            name="TestStrategy",
            description="A test strategy",
            code="class TestStrategy(Strategy): pass",
            config={"param": "value"},
        )

        strategy.mark_as_validated()
        strategy.update_config({"new_param": "new_value"})

        assert strategy.status == StrategyStatus.DRAFT
