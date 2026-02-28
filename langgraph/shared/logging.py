"""Structured logging system using structlog."""

import logging
import sys

import structlog
from structlog.types import EventDict, FilteringBoundLogger, WrappedLogger

from shared.config import LangGraphConfig


def _add_trace_context(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """Processor to add trace context to log events.

    This processor checks for an active trace context and adds
    correlation_id, span_id, and parent_span_id to the log event.
    """
    # Import here to avoid circular dependency
    try:
        from infrastructure.observability.tracing import get_trace_context

        trace_ctx = get_trace_context()
        if trace_ctx:
            event_dict["correlation_id"] = trace_ctx.correlation_id
            event_dict["span_id"] = trace_ctx.span_id
            if trace_ctx.parent_span_id:
                event_dict["parent_span_id"] = trace_ctx.parent_span_id
            event_dict["workflow_name"] = trace_ctx.workflow_name
    except ImportError:
        # Observability module not available, skip trace context
        pass

    return event_dict


def setup_logging(config: LangGraphConfig) -> None:
    """Setup structured logging with console and file output.

    Args:
        config: LangGraph configuration containing logging settings

    The logging system uses:
    - Console output: Colored, human-readable format for development
    - File output: JSON format for production and analysis
    - Context binding: Support for strategy_name, optimization_id, etc.
    """
    # Convert log level string to logging constant
    log_level = getattr(logging, config.log_level.upper())

    # Clear any existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    # Shared processors for both console and file
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        _add_trace_context,  # Add trace context to all logs
    ]

    # Configure console formatter (colored, human-readable)
    console_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        foreign_pre_chain=shared_processors,
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    root_logger.setLevel(log_level)

    # File handler with JSON format
    if config.log_file:
        file_formatter = structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
            foreign_pre_chain=shared_processors,
        )

        file_handler = logging.FileHandler(config.log_file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # Configure structlog
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> FilteringBoundLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name (typically __name__ of the module)

    Returns:
        A bound logger that supports context binding and structured logging

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("processing strategy", strategy_name="keltner_breakout")
        >>> bound_logger = logger.bind(optimization_id="opt_123")
        >>> bound_logger.info("backtest started")
    """
    return structlog.get_logger(name)
