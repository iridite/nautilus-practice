"""Configuration management for LangGraph strategy automation."""

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LangGraphConfig(BaseSettings):
    """Configuration for LangGraph strategy automation system.

    Loads configuration from environment variables with LANGGRAPH_ prefix.
    """

    model_config = SettingsConfigDict(
        env_prefix="LANGGRAPH_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM Configuration
    claude_api_key: str = Field(
        ...,
        description="Anthropic Claude API key (required)",
    )
    llm_provider: Literal["anthropic"] = Field(
        default="anthropic",
        description="LLM provider (currently only Anthropic supported)",
    )
    claude_model: str = Field(
        default="claude-3-5-sonnet-20241022",
        description="Claude model to use for strategy generation",
    )

    # Backtest Configuration
    max_parallel_backtests: int = Field(
        default=4,
        ge=1,
        le=16,
        description="Maximum number of parallel backtests",
    )
    backtest_timeout: int = Field(
        default=300,
        ge=60,
        description="Backtest timeout in seconds",
    )

    # Database Configuration
    database_url: str = Field(
        default="sqlite:///langgraph_state.db",
        description="Database URL for LangGraph state persistence",
    )

    # Logging Configuration
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
    )
    log_file: Path = Field(
        default=Path("logs/langgraph.log"),
        description="Log file path",
    )

    # Output Configuration
    output_dir: Path = Field(
        default=Path("output/langgraph"),
        description="Output directory for generated strategies and results",
    )

    @field_validator("claude_api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Validate API key format."""
        if not v or not v.strip():
            raise ValueError("claude_api_key cannot be empty")

        v = v.strip()

        # Basic format validation (Anthropic keys start with 'sk-ant-')
        if not v.startswith("sk-ant-"):
            raise ValueError(
                "claude_api_key must start with 'sk-ant-'. "
                "Please check your API key format."
            )

        if len(v) < 20:  # Reasonable minimum length
            raise ValueError("claude_api_key appears to be too short")

        return v

    @model_validator(mode="after")
    def create_directories(self) -> "LangGraphConfig":
        """Create output and log directories if they don't exist."""
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            raise ValueError(
                f"Cannot create directories due to permission error: {e}. "
                f"Please check write permissions for {self.output_dir} and {self.log_file.parent}"
            ) from e
        except OSError as e:
            raise ValueError(
                f"Failed to create directories: {e}"
            ) from e

        return self
