"""
数据加载缓存模块

提供 LRU 缓存机制，减少重复数据加载时间。
"""

import hashlib
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


class DataCache:
    """数据加载缓存管理器"""

    def __init__(self, max_size: int = 100):
        self._cache = {}
        self.max_size = max_size
        self.hits = 0
        self.misses = 0

    def _get_cache_key(self, path: Path, start_date: str, end_date: str) -> str:
        """生成缓存键"""
        mtime = path.stat().st_mtime if path.exists() else 0
        key_str = f"{path}_{start_date}_{end_date}_{mtime}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, path: Path, start_date: str, end_date: str) -> pd.DataFrame | None:
        """从缓存获取数据"""
        cache_key = self._get_cache_key(path, start_date, end_date)

        if cache_key in self._cache:
            self.hits += 1
            logger.debug(f"缓存命中: {path.name}")
            return self._cache[cache_key].copy()

        self.misses += 1
        return None

    def put(self, path: Path, start_date: str, end_date: str, df: pd.DataFrame):
        """将数据放入缓存"""
        cache_key = self._get_cache_key(path, start_date, end_date)

        # LRU 淘汰
        if len(self._cache) >= self.max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            logger.debug("缓存已满，淘汰最旧数据")

        self._cache[cache_key] = df.copy()
        logger.debug(f"数据已缓存: {path.name}")

    def clear(self):
        """清空缓存"""
        self._cache.clear()
        self.hits = 0
        self.misses = 0
        logger.info("缓存已清空")

    def get_stats(self) -> dict:
        """获取缓存统计"""
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{hit_rate:.1%}",
            "cached_items": len(self._cache),
            "max_size": self.max_size,
        }


# 全局缓存实例
_data_cache = DataCache(max_size=100)


def get_cache() -> DataCache:
    """获取全局缓存实例"""
    return _data_cache
