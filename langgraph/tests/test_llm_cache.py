"""Tests for LLM cache"""
import tempfile
from pathlib import Path

import pytest

from langgraph.infrastructure.cache.llm_cache import LLMCache


class TestLLMCache:
    """LLM 缓存测试"""

    def test_memory_cache_hit(self):
        """测试内存缓存命中"""
        cache = LLMCache(use_memory=True)

        prompt = "What is the capital of France?"
        response = "Paris"

        # 保存到缓存
        cache.set(prompt=prompt, response=response)

        # 从缓存获取
        cached_response = cache.get(prompt=prompt)

        assert cached_response == response

    def test_memory_cache_miss(self):
        """测试内存缓存未命中"""
        cache = LLMCache(use_memory=True)

        prompt = "What is the capital of France?"

        # 缓存中没有数据
        cached_response = cache.get(prompt=prompt)

        assert cached_response is None

    def test_file_cache_hit(self):
        """测试文件缓存命中"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            cache = LLMCache(cache_dir=cache_dir, use_memory=False)

            prompt = "What is the capital of France?"
            response = "Paris"

            # 保存到缓存
            cache.set(prompt=prompt, response=response)

            # 创建新的缓存实例（模拟重启）
            cache2 = LLMCache(cache_dir=cache_dir, use_memory=False)

            # 从缓存获取
            cached_response = cache2.get(prompt=prompt)

            assert cached_response == response

    def test_cache_key_generation(self):
        """测试缓存键生成"""
        cache = LLMCache(use_memory=True)

        prompt = "What is the capital of France?"
        response = "Paris"

        # 相同参数应该生成相同的键
        cache.set(prompt=prompt, response=response, temperature=0.7)
        cached_response = cache.get(prompt=prompt, temperature=0.7)

        assert cached_response == response

        # 不同参数应该生成不同的键
        cached_response = cache.get(prompt=prompt, temperature=0.5)

        assert cached_response is None

    def test_cache_clear(self):
        """测试清空缓存"""
        cache = LLMCache(use_memory=True)

        prompt = "What is the capital of France?"
        response = "Paris"

        # 保存到缓存
        cache.set(prompt=prompt, response=response)

        # 清空缓存
        cache.clear()

        # 缓存应该为空
        cached_response = cache.get(prompt=prompt)

        assert cached_response is None

    def test_cache_stats(self):
        """测试缓存统计"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            cache = LLMCache(cache_dir=cache_dir, use_memory=True)

            # 初始状态
            stats = cache.get_stats()
            assert stats["memory_entries"] == 0
            assert stats["file_entries"] == 0

            # 添加缓存
            cache.set(prompt="test1", response="response1")
            cache.set(prompt="test2", response="response2")

            stats = cache.get_stats()
            assert stats["memory_entries"] == 2
            assert stats["file_entries"] == 2

    def test_system_prompt_affects_cache_key(self):
        """测试系统提示词影响缓存键"""
        cache = LLMCache(use_memory=True)

        prompt = "What is the capital of France?"
        response1 = "Paris"
        response2 = "The capital is Paris"

        # 不同的系统提示词
        cache.set(prompt=prompt, response=response1, system="You are a helpful assistant")
        cache.set(prompt=prompt, response=response2, system="You are a geography expert")

        # 应该返回对应的响应
        cached1 = cache.get(prompt=prompt, system="You are a helpful assistant")
        cached2 = cache.get(prompt=prompt, system="You are a geography expert")

        assert cached1 == response1
        assert cached2 == response2
