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
        Validate that the strategy code is valid Python syntax.

        Raises:
            ValueError: If the code contains syntax errors.
        """
        try:
            ast.parse(self.code)
        except SyntaxError as e:
            raise ValueError(f"Invalid Python code: {e}")

    def validate_config(self) -> None:
        """
        Validate that the strategy configuration is valid.

        Currently accepts any dict. Can be extended with schema validation.
        """
        if not isinstance(self.config, dict):
            raise ValueError("Config must be a dictionary")

    def mark_as_validated(self) -> None:
        """
        Mark the strategy as validated.

        Updates status to VALIDATED and increments version.
        """
        self.status = StrategyStatus.VALIDATED
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1

    def mark_as_tested(self) -> None:
        """
        Mark the strategy as tested.

        Updates status to TESTED and increments version.

        Raises:
            ValueError: If strategy is not in VALIDATED status.
        """
        if self.status not in [StrategyStatus.VALIDATED, StrategyStatus.TESTED]:
            raise ValueError(
                f"Cannot transition from {self.status.value} to tested. "
                "Strategy must be validated first."
            )
        self.status = StrategyStatus.TESTED
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1

    def mark_as_deployed(self) -> None:
        """
        Mark the strategy as deployed.

        Updates status to DEPLOYED and increments version.

        Raises:
            ValueError: If strategy is not in TESTED status.
        """
        if self.status != StrategyStatus.TESTED:
            raise ValueError(
                f"Cannot transition from {self.status.value} to deployed. "
                "Strategy must be tested first."
            )
        self.status = StrategyStatus.DEPLOYED
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1
