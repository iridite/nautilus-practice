"""LLM response caching implementation"""

import hashlib
import json
import pickle
from pathlib import Path
from typing import Any, Optional

from shared.logging import get_logger

logger = get_logger(__name__)


class LLMCache:
    """LLM 响应缓存"""

    def __init__(self, cache_dir: Optional[Path] = None, use_memory: bool = True):
        """
        初始化缓存

        Args:
            cache_dir: 缓存目录（文件缓存）
            use_memory: 是否使用内存缓存
        """
        self.use_memory = use_memory
        self.cache_dir = cache_dir
        self._memory_cache: dict[str, str] = {}

        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info("LLM cache initialized", cache_dir=str(cache_dir), use_memory=use_memory)
        else:
            logger.info("LLM cache initialized (memory only)")

    def _generate_key(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: str = "claude-opus-4-6",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """
        生成缓存键

        Args:
            prompt: 用户提示词
            system: 系统提示词
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数

        Returns:
            缓存键（SHA256 哈希）
        """
        cache_input = {
            "prompt": prompt,
            "system": system,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        cache_str = json.dumps(cache_input, sort_keys=True)
        return hashlib.sha256(cache_str.encode()).hexdigest()

    def get(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: str = "claude-opus-4-6",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Optional[str]:
        """
        从缓存获取响应

        Args:
            prompt: 用户提示词
            system: 系统提示词
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数

        Returns:
            缓存的响应，如果不存在则返回 None
        """
        key = self._generate_key(prompt, system, model, temperature, max_tokens)

        # 先查内存缓存
        if self.use_memory and key in self._memory_cache:
            logger.debug("Cache hit (memory)", key=key[:16])
            return self._memory_cache[key]

        # 再查文件缓存
        if self.cache_dir:
            cache_file = self.cache_dir / f"{key}.pkl"
            if cache_file.exists():
                try:
                    with open(cache_file, "rb") as f:
                        response = pickle.load(f)
                    logger.debug("Cache hit (file)", key=key[:16])

                    # 加载到内存缓存
                    if self.use_memory:
                        self._memory_cache[key] = response

                    return response
                except Exception as e:
                    logger.warning("Failed to load cache file", key=key[:16], error=str(e))

        logger.debug("Cache miss", key=key[:16])
        return None

    def set(
        self,
        prompt: str,
        response: str,
        system: Optional[str] = None,
        model: str = "claude-opus-4-6",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> None:
        """
        保存响应到缓存

        Args:
            prompt: 用户提示词
            response: LLM 响应
            system: 系统提示词
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
        """
        key = self._generate_key(prompt, system, model, temperature, max_tokens)

        # 保存到内存缓存
        if self.use_memory:
            self._memory_cache[key] = response

        # 保存到文件缓存
        if self.cache_dir:
            cache_file = self.cache_dir / f"{key}.pkl"
            try:
                with open(cache_file, "wb") as f:
                    pickle.dump(response, f)
                logger.debug("Cache saved", key=key[:16])
            except Exception as e:
                logger.warning("Failed to save cache file", key=key[:16], error=str(e))

    def clear(self) -> None:
        """清空缓存"""
        # 清空内存缓存
        if self.use_memory:
            self._memory_cache.clear()

        # 清空文件缓存
        if self.cache_dir and self.cache_dir.exists():
            for cache_file in self.cache_dir.glob("*.pkl"):
                try:
                    cache_file.unlink()
                except Exception as e:
                    logger.warning(
                        "Failed to delete cache file", file=str(cache_file), error=str(e)
                    )

        logger.info("Cache cleared")

    def get_stats(self) -> dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            缓存统计信息
        """
        stats: dict[str, Any] = {
            "memory_entries": len(self._memory_cache) if self.use_memory else 0,
            "file_entries": 0,
            "total_size_bytes": 0,
        }

        if self.cache_dir and self.cache_dir.exists():
            cache_files = list(self.cache_dir.glob("*.pkl"))
            stats["file_entries"] = len(cache_files)
            stats["total_size_bytes"] = sum(f.stat().st_size for f in cache_files)

        return stats
