"""Tests for structured logging system."""

import json
import logging
import tempfile
from pathlib import Path

import pytest
import structlog

from langgraph.shared.config import LangGraphConfig
from langgraph.shared.logging import get_logger, setup_logging


class TestLoggingSetup:
    """Test logging system initialization."""

    def test_setup_logging_with_console_output(self):
        """Test logging setup with console output."""
        config = LangGraphConfig(
            claude_api_key="sk-ant-test-key-12345678901234567890",
            log_level="INFO",
        )

        setup_logging(config)
        logger = get_logger("test")

        assert logger is not None
        # Logger can be either BoundLogger or BoundLoggerLazyProxy
        assert hasattr(logger, "info")
        assert hasattr(logger, "bind")

    def test_setup_logging_with_file_output(self):
        """Test logging setup with file output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"

            config = LangGraphConfig(
                claude_api_key="sk-ant-test-key-12345678901234567890",
                log_level="DEBUG",
                log_file=log_file,
            )

            setup_logging(config)
            logger = get_logger("test")

            logger.info("test message", key="value")

            # Verify log file was created and contains JSON
            assert log_file.exists()
            content = log_file.read_text()
            assert len(content) > 0

            # Parse first line as JSON
            first_line = content.strip().split("\n")[0]
            log_entry = json.loads(first_line)
            assert log_entry["event"] == "test message"
            assert log_entry["key"] == "value"

    def test_setup_logging_with_different_levels(self):
        """Test logging with different log levels."""
        config = LangGraphConfig(
            claude_api_key="sk-ant-test-key-12345678901234567890",
            log_level="WARNING",
        )

        setup_logging(config)
        logger = get_logger("test")

        # Should be able to log at WARNING and above
        logger.warning("warning message")
        logger.error("error message")

        # DEBUG and INFO should be filtered (no exception raised)
        logger.debug("debug message")
        logger.info("info message")


class TestLoggerUsage:
    """Test logger usage and features."""

    def test_get_logger_returns_bound_logger(self):
        """Test that get_logger returns a bound logger."""
        config = LangGraphConfig(
            claude_api_key="sk-ant-test-key-12345678901234567890",
            log_level="INFO",
        )
        setup_logging(config)

        logger = get_logger("my_module")
        # Verify logger has required methods
        assert hasattr(logger, "info")
        assert hasattr(logger, "bind")
        assert hasattr(logger, "debug")
        assert hasattr(logger, "warning")
        assert hasattr(logger, "error")

    def test_logger_context_binding(self):
        """Test logger context binding."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"

            config = LangGraphConfig(
                claude_api_key="sk-ant-test-key-12345678901234567890",
                log_level="INFO",
                log_file=log_file,
            )

            setup_logging(config)
            logger = get_logger("test")

            # Bind context
            bound_logger = logger.bind(strategy_name="test_strategy", optimization_id="opt_123")
            bound_logger.info("test event")

            # Verify context is in log file
            content = log_file.read_text()
            log_entry = json.loads(content.strip().split("\n")[0])

            assert log_entry["strategy_name"] == "test_strategy"
            assert log_entry["optimization_id"] == "opt_123"
            assert log_entry["event"] == "test event"

    def test_logger_different_levels(self):
        """Test logging at different levels."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"

            config = LangGraphConfig(
                claude_api_key="sk-ant-test-key-12345678901234567890",
                log_level="DEBUG",
                log_file=log_file,
            )

            setup_logging(config)
            logger = get_logger("test")

            logger.debug("debug message")
            logger.info("info message")
            logger.warning("warning message")
            logger.error("error message")

            # Verify all levels are logged
            content = log_file.read_text()
            lines = content.strip().split("\n")
            assert len(lines) == 4

            levels = [json.loads(line)["level"] for line in lines]
            assert "debug" in levels
            assert "info" in levels
            assert "warning" in levels
            assert "error" in levels

    def test_logger_with_exception(self):
        """Test logging with exception information."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"

            config = LangGraphConfig(
                claude_api_key="sk-ant-test-key-12345678901234567890",
                log_level="ERROR",
                log_file=log_file,
            )

            setup_logging(config)
            logger = get_logger("test")

            try:
                raise ValueError("test error")
            except ValueError:
                logger.exception("error occurred")

            # Verify exception info is in log
            content = log_file.read_text()
            log_entry = json.loads(content.strip())

            assert log_entry["event"] == "error occurred"
            assert "exception" in log_entry or "exc_info" in log_entry


class TestLoggingFormats:
    """Test different logging formats."""

    def test_json_format_in_file(self):
        """Test JSON format output to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"

            config = LangGraphConfig(
                claude_api_key="sk-ant-test-key-12345678901234567890",
                log_level="INFO",
                log_file=log_file,
            )

            setup_logging(config)
            logger = get_logger("test")

            logger.info("test message", key1="value1", key2=42)

            content = log_file.read_text()
            log_entry = json.loads(content.strip())

            # Verify JSON structure
            assert "event" in log_entry
            assert "level" in log_entry
            assert "timestamp" in log_entry
            assert log_entry["key1"] == "value1"
            assert log_entry["key2"] == 42

    def test_console_format(self):
        """Test console format output (human-readable)."""
        config = LangGraphConfig(
            claude_api_key="sk-ant-test-key-12345678901234567890",
            log_level="INFO",
        )

        setup_logging(config)
        logger = get_logger("test")

        # Should not raise exception
        logger.info("test message", key="value")
