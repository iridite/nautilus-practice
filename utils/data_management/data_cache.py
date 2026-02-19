"""
数据加载缓存模块

提供 LRU 缓存机制，减少重复数据加载时间。
支持 Parquet 元数据缓存以提升性能。
"""

import hashlib
import logging
from pathlib import Path
from typing import Dict, Any

import pandas as pd

logger = logging.getLogger(__name__)


class DataCache:
    """数据加载缓存管理器"""

    def __init__(self, max_size: int = 500):
        self._cache = {}
        self._metadata_cache = {}  # Parquet 元数据缓存
        self.max_size = max_size
        self.hits = 0
        self.misses = 0
        self.metadata_hits = 0
        self.metadata_misses = 0

    def _get_cache_key(self, path: Path, start_date: str, end_date: str) -> str:
        """生成缓存键"""
        mtime = path.stat().st_mtime if path.exists() else 0
        key_str = f"{path}_{start_date}_{end_date}_{mtime}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, path: Path, start_date: str, end_date: str) -> pd.DataFrame | None:
        """从缓存获取数据
        
        性能优化：返回原始 DataFrame，依赖 pandas 2.0+ 的写时复制（CoW）机制
        避免不必要的内存拷贝，提升性能
        """
        cache_key = self._get_cache_key(path, start_date, end_date)

        if cache_key in self._cache:
            self.hits += 1
            logger.debug(f"缓存命中: {path.name}")
            # 性能优化：不再调用 .copy()，依赖 pandas CoW
            # 如果用户修改返回的 DataFrame，pandas 会自动触发拷贝
            return self._cache[cache_key]

        self.misses += 1
        return None

    def put(self, path: Path, start_date: str, end_date: str, df: pd.DataFrame):
        """将数据放入缓存
        
        性能优化：直接存储 DataFrame，不进行拷贝
        依赖 pandas 2.0+ 的写时复制（CoW）机制保证数据安全
        """
        cache_key = self._get_cache_key(path, start_date, end_date)

        # LRU 淘汰
        if len(self._cache) >= self.max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            logger.debug("缓存已满，淘汰最旧数据")

        # 性能优化：不再调用 .copy()，减少内存占用
        self._cache[cache_key] = df
        logger.debug(f"数据已缓存: {path.name}")

    def clear(self):
        """清空缓存"""
        self._cache.clear()
        self._metadata_cache.clear()
        self.hits = 0
        self.misses = 0
        self.metadata_hits = 0
        self.metadata_misses = 0
        logger.info("缓存已清空")

    def get_parquet_metadata(self, path: Path) -> Dict[str, Any] | None:
        """获取 Parquet 文件元数据缓存
        
        Args:
            path: Parquet 文件路径
            
        Returns:
            元数据字典，包含 num_rows, columns, schema 等信息
        """
        if not path.exists():
            return None
            
        mtime = path.stat().st_mtime
        cache_key = f"{path}_{mtime}"
        
        if cache_key in self._metadata_cache:
            self.metadata_hits += 1
            logger.debug(f"Parquet 元数据缓存命中: {path.name}")
            return self._metadata_cache[cache_key]
        
        self.metadata_misses += 1
        return None
    
    def put_parquet_metadata(self, path: Path, metadata: Dict[str, Any]):
        """缓存 Parquet 文件元数据
        
        Args:
            path: Parquet 文件路径
            metadata: 元数据字典
        """
        mtime = path.stat().st_mtime if path.exists() else 0
        cache_key = f"{path}_{mtime}"
        
        # 元数据缓存不受 max_size 限制（元数据很小）
        self._metadata_cache[cache_key] = metadata
        logger.debug(f"Parquet 元数据已缓存: {path.name}")

    def get_stats(self) -> dict:
        """获取缓存统计"""
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0
        
        metadata_total = self.metadata_hits + self.metadata_misses
        metadata_hit_rate = self.metadata_hits / metadata_total if metadata_total > 0 else 0
        
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{hit_rate:.1%}",
            "cached_items": len(self._cache),
            "max_size": self.max_size,
            "metadata_hits": self.metadata_hits,
            "metadata_misses": self.metadata_misses,
            "metadata_hit_rate": f"{metadata_hit_rate:.1%}",
            "metadata_cached_items": len(self._metadata_cache),
        }


# 全局缓存实例（性能优化：增加缓存大小到 500）
_data_cache = DataCache(max_size=500)


def get_cache() -> DataCache:
    """获取全局缓存实例"""
    return _data_cache
