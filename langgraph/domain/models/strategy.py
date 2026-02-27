"""
Strategy domain model.

Represents a trading strategy with its code, configuration, and lifecycle status.
"""

import ast
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class StrategyStatus(Enum):
    """Strategy lifecycle status."""

    DRAFT = "draft"
    VALIDATED = "validated"
    TESTED = "tested"
    DEPLOYED = "deployed"


@dataclass
class Strategy:
    """
    Strategy domain entity.

    Represents a trading strategy with its code, configuration, and metadata.
    """

    name: str
    description: str
    code: str
    config: dict[str, Any]
    strategy_id: str = field(default_factory=lambda: str(uuid4()))
    status: StrategyStatus = field(default=StrategyStatus.DRAFT)
    version: int = field(default=1)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def validate_code(self) -> None:
        """
        Validate that the strategy code is valid Python syntax and structure.

        Raises:
            ValueError: If the code contains syntax errors or missing class definition.
        """
        try:
            tree = ast.parse(self.code)
        except SyntaxError as e:
            raise ValueError(f"Invalid Python code: {e}")

        # Check if code defines at least one class
        has_class = any(
            isinstance(node, ast.ClassDef)
            for node in ast.walk(tree)
        )
        if not has_class:
            raise ValueError("Strategy code must define at least one class")

    def validate_config(self) -> None:
        """
        Validate that the strategy configuration is valid.

        Raises:
            ValueError: If config is not a dictionary or is empty.
        """
        if not isinstance(self.config, dict):
            raise ValueError("Config must be a dictionary")

        if not self.config:
            raise ValueError("Config cannot be empty")

    def mark_as_validated(self) -> None:
        """
        Mark the strategy as validated.

        Updates status to VALIDATED.
        """
        self.status = StrategyStatus.VALIDATED
        self.updated_at = datetime.now(timezone.utc)

    def mark_as_tested(self) -> None:
        """
        Mark the strategy as tested.

        Updates status to TESTED. Idempotent operation.

        Raises:
            ValueError: If strategy is not in VALIDATED status.
        """
        if self.status == StrategyStatus.TESTED:
            return  # Already tested, idempotent

        if self.status != StrategyStatus.VALIDATED:
            raise ValueError(
                f"Cannot transition from {self.status.value} to tested. "
                "Strategy must be validated first."
            )
        self.status = StrategyStatus.TESTED
        self.updated_at = datetime.now(timezone.utc)

    def mark_as_deployed(self) -> None:
        """
        Mark the strategy as deployed.

        Updates status to DEPLOYED. Idempotent operation.

        Raises:
            ValueError: If strategy is not in TESTED status.
        """
        if self.status == StrategyStatus.DEPLOYED:
            return  # Already deployed, idempotent

        if self.status != StrategyStatus.TESTED:
            raise ValueError(
                f"Cannot transition from {self.status.value} to deployed. "
                "Strategy must be tested first."
            )
        self.status = StrategyStatus.DEPLOYED
        self.updated_at = datetime.now(timezone.utc)

    def update_code(self, new_code: str) -> None:
        """
        Update strategy code and increment version.

        Args:
            new_code: The new strategy code.
        """
        self.code = new_code
        self.version += 1
        self.updated_at = datetime.now(timezone.utc)
        self.status = StrategyStatus.DRAFT  # Reset to draft on code change

    def update_config(self, new_config: dict[str, Any]) -> None:
        """
        Update strategy config and increment version.

        Args:
            new_config: The new strategy configuration.
        """
        self.config = new_config
        self.version += 1
        self.updated_at = datetime.now(timezone.utc)
        self.status = StrategyStatus.DRAFT  # Reset to draft on config change
