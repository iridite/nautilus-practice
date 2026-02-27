"""Graph configuration models."""

from pydantic import BaseModel, ConfigDict, Field


class GraphConfig(BaseModel):
    """Configuration for graph execution.

    Attributes:
        research_node_timeout: Timeout for research node execution in seconds
        optimization_node_timeout: Timeout for optimization node execution in seconds
        max_retries: Maximum number of retry attempts
        retry_base_delay: Base delay between retries in seconds
        retry_max_delay: Maximum delay between retries in seconds
        retry_exponential_base: Exponential base for retry backoff
        log_execution_time: Whether to log execution time
        log_decision_rationale: Whether to log decision rationale
    """

    # Timeout settings
    research_node_timeout: float = Field(default=30.0, ge=10.0, le=300.0)
    optimization_node_timeout: float = Field(default=60.0, ge=30.0, le=600.0)

    # Retry settings
    max_retries: int = Field(default=3, ge=1, le=10)
    retry_base_delay: float = Field(default=1.0, ge=0.1, le=10.0)
    retry_max_delay: float = Field(default=10.0, ge=1.0, le=60.0)
    retry_exponential_base: float = Field(default=2.0, ge=1.1, le=3.0)

    # Logging settings
    log_execution_time: bool = Field(default=True)
    log_decision_rationale: bool = Field(default=True)

    model_config = ConfigDict(frozen=True)
