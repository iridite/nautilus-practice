"""LLM service interface for strategy generation."""

from abc import ABC, abstractmethod


class LLMService(ABC):
    """Interface for LLM-based strategy generation."""

    @abstractmethod
    async def generate_strategy(self, requirements: str) -> dict:
        """Generate strategy code and config from requirements.

        Args:
            requirements: Natural language strategy requirements

        Returns:
            Dictionary containing:
                - name: Strategy name
                - description: Strategy description
                - code: Python code as string
                - config: Configuration dictionary

        Raises:
            Exception: If generation fails
        """
        pass
