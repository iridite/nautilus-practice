"""Tests for Claude API client"""

import pytest
from unittest.mock import Mock, patch
from infrastructure.llm.claude_client import ClaudeClient
from shared.exceptions import LLMError


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client"""
    with patch("infrastructure.llm.claude_client.Anthropic") as mock:
        client = Mock()
        mock.return_value = client
        yield client


def test_client_initialization(mock_anthropic_client):
    """测试客户端初始化"""
    with patch("infrastructure.llm.claude_client.Anthropic") as mock_cls:
        mock_cls.return_value = Mock()
        client = ClaudeClient(api_key="test-key", model="claude-opus-4-6")

        assert client.model == "claude-opus-4-6"
        assert client.max_tokens == 4096
        mock_cls.assert_called_once_with(api_key="test-key")


def test_client_initialization_with_custom_params(mock_anthropic_client):
    """测试自定义参数初始化"""
    client = ClaudeClient(
        api_key="test-key", model="claude-sonnet-4-6", max_tokens=8192, temperature=0.5
    )

    assert client.model == "claude-sonnet-4-6"
    assert client.max_tokens == 8192
    assert client.temperature == 0.5


def test_generate_success(mock_anthropic_client):
    """测试成功生成响应"""
    # Mock response
    mock_response = Mock()
    mock_response.content = [Mock(text="Generated response")]
    mock_anthropic_client.messages.create.return_value = mock_response

    client = ClaudeClient(api_key="test-key")
    result = client.generate("Test prompt")

    assert result == "Generated response"
    mock_anthropic_client.messages.create.assert_called_once()


def test_generate_with_system_prompt(mock_anthropic_client):
    """测试带系统提示词的生成"""
    mock_response = Mock()
    mock_response.content = [Mock(text="Response")]
    mock_anthropic_client.messages.create.return_value = mock_response

    client = ClaudeClient(api_key="test-key")
    result = client.generate("User prompt", system="System prompt")

    assert result == "Response"
    call_args = mock_anthropic_client.messages.create.call_args
    assert call_args.kwargs["system"] == "System prompt"


def test_generate_api_error(mock_anthropic_client):
    """测试 API 错误处理"""
    mock_anthropic_client.messages.create.side_effect = Exception("API Error")

    client = ClaudeClient(api_key="test-key", max_retries=1, enable_cache=False)

    with pytest.raises(LLMError) as exc_info:
        client.generate("Test prompt")

    assert "Claude API error" in str(exc_info.value)
    assert mock_anthropic_client.messages.create.call_count == 1


def test_generate_empty_response(mock_anthropic_client):
    """测试空响应处理"""
    mock_response = Mock()
    mock_response.content = []
    mock_anthropic_client.messages.create.return_value = mock_response

    client = ClaudeClient(api_key="test-key", max_retries=1, enable_cache=False)

    with pytest.raises(LLMError) as exc_info:
        client.generate("Test prompt")

    assert "Empty response" in str(exc_info.value)
    assert mock_anthropic_client.messages.create.call_count == 1


def test_generate_with_max_retries(mock_anthropic_client):
    """测试重试机制"""
    # First call fails, second succeeds
    mock_response = Mock()
    mock_response.content = [Mock(text="Success")]
    mock_anthropic_client.messages.create.side_effect = [
        Exception("Temporary error"),
        mock_response,
    ]

    client = ClaudeClient(api_key="test-key", max_retries=2)
    result = client.generate("Test prompt")

    assert result == "Success"
    assert mock_anthropic_client.messages.create.call_count == 2


def test_generate_exceeds_max_retries(mock_anthropic_client):
    """测试超过最大重试次数"""
    mock_anthropic_client.messages.create.side_effect = Exception("Persistent error")

    client = ClaudeClient(api_key="test-key", max_retries=2, enable_cache=False)

    with pytest.raises(LLMError) as exc_info:
        client.generate("Test prompt")

    assert "Claude API error after 2 retries" in str(exc_info.value)
    assert mock_anthropic_client.messages.create.call_count == 2


def test_count_tokens():
    """测试 token 计数（简单估算）"""
    client = ClaudeClient(api_key="test-key")

    # 简单的 token 估算：约 4 字符 = 1 token
    text = "This is a test message"
    tokens = client.count_tokens(text)

    assert tokens > 0
    assert tokens == len(text) // 4
