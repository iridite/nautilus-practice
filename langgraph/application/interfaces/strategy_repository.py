"""Strategy repository interface for persistence."""

from abc import ABC, abstractmethod
from langgraph.domain.models.strategy import Strategy


class StrategyRepository(ABC):
    """Interface for strategy persistence."""

    @abstractmethod
    async def save(self, strategy: Strategy) -> None:
        """Save a strategy.

        Args:
            strategy: Strategy entity to save

        Raises:
            Exception: If save fails
        """
        pass

    @abstractmethod
    async def get_by_id(self, strategy_id: str) -> Strategy | None:
        """Get a strategy by ID.

        Args:
            strategy_id: Strategy ID

        Returns:
            Strategy entity if found, None otherwise

        Raises:
            Exception: If retrieval fails
        """
        pass
