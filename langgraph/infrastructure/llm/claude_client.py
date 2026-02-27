"""Claude API client implementation"""
import time
from pathlib import Path
from typing import Optional

from anthropic import Anthropic

from infrastructure.cache.llm_cache import LLMCache
from shared.exceptions import LLMError
from shared.logging import get_logger

logger = get_logger(__name__)


class ClaudeClient:
    """Claude API 客户端实现"""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-opus-4-6",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        cache_dir: Optional[Path] = None,
        enable_cache: bool = True,
    ):
        """
        初始化 Claude 客户端

        Args:
            api_key: Claude API key
            model: 模型名称
            max_tokens: 最大生成 token 数
            temperature: 温度参数（0-1）
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
            cache_dir: 缓存目录（可选）
            enable_cache: 是否启用缓存
        """
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        self._client = Anthropic(api_key=api_key)
        self._cache = LLMCache(cache_dir=cache_dir, use_memory=True) if enable_cache else None

        logger.info(
            "Claude client initialized",
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            cache_enabled=enable_cache,
        )

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        use_cache: bool = True,
    ) -> str:
        """
        生成响应

        Args:
            prompt: 用户提示词
            system: 系统提示词（可选）
            temperature: 温度参数（可选，覆盖默认值）
            max_tokens: 最大 token 数（可选，覆盖默认值）
            use_cache: 是否使用缓存

        Returns:
            生成的文本响应

        Raises:
            LLMError: API 调用失败或响应无效
        """
        temp = temperature if temperature is not None else self.temperature
        tokens = max_tokens if max_tokens is not None else self.max_tokens

        # 尝试从缓存获取
        if use_cache and self._cache:
            cached_response = self._cache.get(
                prompt=prompt,
                system=system,
                model=self.model,
                temperature=temp,
                max_tokens=tokens,
            )
            if cached_response:
                logger.info("Using cached response", prompt_length=len(prompt))
                return cached_response

        for attempt in range(self.max_retries):
            try:
                logger.debug(
                    "Calling Claude API",
                    model=self.model,
                    attempt=attempt + 1,
                    prompt_length=len(prompt),
                )

                # 构建消息
                messages = [{"role": "user", "content": prompt}]

                # 调用 API
                kwargs = {
                    "model": self.model,
                    "max_tokens": tokens,
                    "temperature": temp,
                    "messages": messages,
                }

                if system:
                    kwargs["system"] = system

                response = self._client.messages.create(**kwargs)

                # 提取响应文本
                if not response.content:
                    raise LLMError("Empty response from Claude API")

                result = response.content[0].text

                logger.info(
                    "Claude API call successful",
                    model=self.model,
                    response_length=len(result),
                )

                # 保存到缓存
                if use_cache and self._cache:
                    self._cache.set(
                        prompt=prompt,
                        response=result,
                        system=system,
                        model=self.model,
                        temperature=temp,
                        max_tokens=tokens,
                    )

                return result

            except Exception as e:
                logger.warning(
                    "Claude API call failed",
                    model=self.model,
                    attempt=attempt + 1,
                    error=str(e),
                )

                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    raise LLMError(f"Claude API error after {self.max_retries} retries: {e}") from e

        # 不应该到达这里
        raise LLMError("Unexpected error in generate method")

    def clear_cache(self) -> None:
        """清空缓存"""
        if self._cache:
            self._cache.clear()
            logger.info("Cache cleared")

    def get_cache_stats(self) -> dict:
        """获取缓存统计信息"""
        if self._cache:
            return self._cache.get_stats()
        return {"cache_enabled": False}

    def count_tokens(self, text: str) -> int:
        """
        估算文本的 token 数量

        Args:
            text: 输入文本

        Returns:
            估算的 token 数量

        Note:
            这是一个简单的估算方法（约 4 字符 = 1 token）
            实际应用中可以使用 tiktoken 或 Anthropic 的 token 计数 API
        """
        # 简单估算：英文约 4 字符 = 1 token
        return len(text) // 4
