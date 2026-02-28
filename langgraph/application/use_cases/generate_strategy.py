"""Use case for generating trading strategies."""

from langgraph.domain.models.strategy import Strategy
from langgraph.application.interfaces.llm_service import LLMService
from langgraph.application.interfaces.strategy_repository import StrategyRepository
from langgraph.shared.exceptions import LLMError, ParameterValidationError


class GenerateStrategyUseCase:
    """Use case for generating strategies from natural language requirements."""

    def __init__(
        self,
        llm_service: LLMService,
        strategy_repository: StrategyRepository,
    ):
        """Initialize use case with dependencies.

        Args:
            llm_service: Service for LLM-based generation
            strategy_repository: Repository for strategy persistence
        """
        self.llm_service = llm_service
        self.strategy_repository = strategy_repository

    async def execute(self, requirements: str) -> Strategy:
        """Generate strategy from requirements.

        Args:
            requirements: Natural language strategy requirements

        Returns:
            Generated strategy entity

        Raises:
            LLMError: If LLM generation fails
            ParameterValidationError: If generated strategy is invalid
        """
        # 1. Call LLM to generate strategy
        try:
            result = await self.llm_service.generate_strategy(requirements)
        except Exception as e:
            raise LLMError(f"Failed to generate strategy: {e}")

        # 2. Create strategy entity
        strategy = Strategy(
            name=result["name"],
            description=result["description"],
            code=result["code"],
            config=result["config"],
        )

        # 3. Validate strategy
        try:
            strategy.validate_code()
            strategy.validate_config()
        except ValueError as e:
            raise ParameterValidationError(f"Invalid strategy: {e}")

        # 4. Save strategy
        await self.strategy_repository.save(strategy)

        return strategy
