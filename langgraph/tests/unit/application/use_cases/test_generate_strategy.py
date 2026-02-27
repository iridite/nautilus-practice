"""Tests for GenerateStrategyUseCase."""

import pytest
from unittest.mock import AsyncMock, Mock
from langgraph.application.use_cases.generate_strategy import GenerateStrategyUseCase
from langgraph.application.interfaces.llm_service import LLMService
from langgraph.application.interfaces.strategy_repository import StrategyRepository
from langgraph.domain.models.strategy import Strategy, StrategyStatus
from langgraph.shared.exceptions import LLMError, ParameterValidationError


@pytest.fixture
def mock_llm_service():
    """Create mock LLM service."""
    service = Mock(spec=LLMService)
    service.generate_strategy = AsyncMock()
    return service


@pytest.fixture
def mock_strategy_repository():
    """Create mock strategy repository."""
    repo = Mock(spec=StrategyRepository)
    repo.save = AsyncMock()
    repo.get_by_id = AsyncMock()
    return repo


@pytest.fixture
def use_case(mock_llm_service, mock_strategy_repository):
    """Create use case instance."""
    return GenerateStrategyUseCase(
        llm_service=mock_llm_service,
        strategy_repository=mock_strategy_repository,
    )


@pytest.fixture
def valid_llm_response():
    """Valid LLM response."""
    return {
        "name": "test_strategy",
        "description": "A test strategy",
        "code": "class TestStrategy:\n    pass",
        "config": {
            "timeframe": "1h",
            "parameters": {"param1": 10}
        }
    }


@pytest.mark.asyncio
async def test_use_case_initialization(mock_llm_service, mock_strategy_repository):
    """Test use case can be initialized with dependencies."""
    use_case = GenerateStrategyUseCase(
        llm_service=mock_llm_service,
        strategy_repository=mock_strategy_repository,
    )

    assert use_case.llm_service is mock_llm_service
    assert use_case.strategy_repository is mock_strategy_repository


@pytest.mark.asyncio
async def test_execute_success(use_case, mock_llm_service, mock_strategy_repository, valid_llm_response):
    """Test successful strategy generation."""
    # Arrange
    requirements = "Create a momentum strategy"
    mock_llm_service.generate_strategy.return_value = valid_llm_response

    # Act
    result = await use_case.execute(requirements)

    # Assert
    assert isinstance(result, Strategy)
    assert result.name == "test_strategy"
    assert result.description == "A test strategy"
    assert result.code == "class TestStrategy:\n    pass"
    assert result.config == {"timeframe": "1h", "parameters": {"param1": 10}}
    assert result.status == StrategyStatus.DRAFT

    # Verify LLM was called
    mock_llm_service.generate_strategy.assert_called_once_with(requirements)

    # Verify strategy was saved
    mock_strategy_repository.save.assert_called_once()
    saved_strategy = mock_strategy_repository.save.call_args[0][0]
    assert saved_strategy.name == "test_strategy"


@pytest.mark.asyncio
async def test_execute_llm_failure(use_case, mock_llm_service):
    """Test LLM generation failure."""
    # Arrange
    requirements = "Create a strategy"
    mock_llm_service.generate_strategy.side_effect = Exception("LLM API error")

    # Act & Assert
    with pytest.raises(LLMError, match="Failed to generate strategy"):
        await use_case.execute(requirements)


@pytest.mark.asyncio
async def test_execute_invalid_code(use_case, mock_llm_service, valid_llm_response):
    """Test validation failure for invalid code."""
    # Arrange
    requirements = "Create a strategy"
    invalid_response = valid_llm_response.copy()
    invalid_response["code"] = "invalid python syntax {"
    mock_llm_service.generate_strategy.return_value = invalid_response

    # Act & Assert
    with pytest.raises(ParameterValidationError, match="Invalid strategy"):
        await use_case.execute(requirements)


@pytest.mark.asyncio
async def test_execute_invalid_config(use_case, mock_llm_service, valid_llm_response):
    """Test validation failure for invalid config."""
    # Arrange
    requirements = "Create a strategy"
    invalid_response = valid_llm_response.copy()
    invalid_response["config"] = {}  # Empty config
    mock_llm_service.generate_strategy.return_value = invalid_response

    # Act & Assert
    with pytest.raises(ParameterValidationError, match="Invalid strategy"):
        await use_case.execute(requirements)


@pytest.mark.asyncio
async def test_execute_creates_strategy_with_correct_status(use_case, mock_llm_service, mock_strategy_repository, valid_llm_response):
    """Test that generated strategy has DRAFT status."""
    # Arrange
    requirements = "Create a strategy"
    mock_llm_service.generate_strategy.return_value = valid_llm_response

    # Act
    result = await use_case.execute(requirements)

    # Assert
    assert result.status == StrategyStatus.DRAFT


@pytest.mark.asyncio
async def test_execute_repository_not_called_on_validation_failure(use_case, mock_llm_service, mock_strategy_repository, valid_llm_response):
    """Test that repository save is not called if validation fails."""
    # Arrange
    requirements = "Create a strategy"
    invalid_response = valid_llm_response.copy()
    invalid_response["code"] = "invalid syntax {"
    mock_llm_service.generate_strategy.return_value = invalid_response

    # Act & Assert
    with pytest.raises(ParameterValidationError):
        await use_case.execute(requirements)

    # Verify save was not called
    mock_strategy_repository.save.assert_not_called()
