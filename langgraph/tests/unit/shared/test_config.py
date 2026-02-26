"""Unit tests for configuration management."""

import os
import tempfile
from pathlib import Path

import pytest

from langgraph.shared.config import LangGraphConfig


class TestLangGraphConfig:
    """Test suite for LangGraphConfig."""

    def test_config_from_env_variables(self, monkeypatch):
        """Test loading configuration from environment variables."""
        # Set environment variables
        monkeypatch.setenv("LANGGRAPH_CLAUDE_API_KEY", "sk-ant-test-key-1234567890")
        monkeypatch.setenv("LANGGRAPH_MAX_PARALLEL_BACKTESTS", "8")
        monkeypatch.setenv("LANGGRAPH_LOG_LEVEL", "DEBUG")

        config = LangGraphConfig()

        assert config.claude_api_key == "sk-ant-test-key-1234567890"
        assert config.max_parallel_backtests == 8
        assert config.log_level == "DEBUG"

    def test_config_missing_api_key_raises_error(self, monkeypatch):
        """Test that missing API key raises validation error."""
        # Ensure API key is not set
        monkeypatch.delenv("LANGGRAPH_CLAUDE_API_KEY", raising=False)

        with pytest.raises(ValueError, match="claude_api_key"):
            LangGraphConfig()

    def test_config_creates_output_directory(self, monkeypatch):
        """Test that output directory is created automatically."""
        monkeypatch.setenv("LANGGRAPH_CLAUDE_API_KEY", "sk-ant-test-key-1234567890")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "test_output"
            monkeypatch.setenv("LANGGRAPH_OUTPUT_DIR", str(output_dir))

            config = LangGraphConfig()

            assert config.output_dir.exists()
            assert config.output_dir.is_dir()

    def test_config_max_parallel_backtests_boundary(self, monkeypatch):
        """Test max_parallel_backtests boundary validation."""
        monkeypatch.setenv("LANGGRAPH_CLAUDE_API_KEY", "sk-ant-test-key-1234567890")

        # Test lower boundary (0 should fail)
        monkeypatch.setenv("LANGGRAPH_MAX_PARALLEL_BACKTESTS", "0")
        with pytest.raises(ValueError):
            LangGraphConfig()

        # Test upper boundary (17 should fail)
        monkeypatch.setenv("LANGGRAPH_MAX_PARALLEL_BACKTESTS", "17")
        with pytest.raises(ValueError):
            LangGraphConfig()

        # Test valid boundaries
        monkeypatch.setenv("LANGGRAPH_MAX_PARALLEL_BACKTESTS", "1")
        config = LangGraphConfig()
        assert config.max_parallel_backtests == 1

        monkeypatch.setenv("LANGGRAPH_MAX_PARALLEL_BACKTESTS", "16")
        config = LangGraphConfig()
        assert config.max_parallel_backtests == 16

    def test_config_invalid_log_level(self, monkeypatch):
        """Test that invalid log level raises validation error."""
        monkeypatch.setenv("LANGGRAPH_CLAUDE_API_KEY", "sk-ant-test-key-1234567890")
        monkeypatch.setenv("LANGGRAPH_LOG_LEVEL", "INVALID")

        with pytest.raises(ValueError):
            LangGraphConfig()

    def test_config_backtest_timeout_boundary(self, monkeypatch):
        """Test backtest_timeout minimum validation."""
        monkeypatch.setenv("LANGGRAPH_CLAUDE_API_KEY", "sk-ant-test-key-1234567890")
        monkeypatch.setenv("LANGGRAPH_BACKTEST_TIMEOUT", "30")

        with pytest.raises(ValueError):
            LangGraphConfig()

    def test_config_api_key_format_validation(self, monkeypatch):
        """Test API key format validation."""
        # Test invalid format (not starting with sk-ant-)
        monkeypatch.setenv("LANGGRAPH_CLAUDE_API_KEY", "invalid-key")
        with pytest.raises(ValueError, match="must start with 'sk-ant-'"):
            LangGraphConfig()

        # Test too short
        monkeypatch.setenv("LANGGRAPH_CLAUDE_API_KEY", "sk-ant-short")
        with pytest.raises(ValueError, match="too short"):
            LangGraphConfig()

        # Test whitespace handling
        monkeypatch.setenv("LANGGRAPH_CLAUDE_API_KEY", "  sk-ant-test-key-1234567890  ")
        config = LangGraphConfig()
        assert config.claude_api_key == "sk-ant-test-key-1234567890"
