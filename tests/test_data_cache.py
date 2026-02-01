"""
Tests for Data Cache
"""
import unittest
from pathlib import Path

import pandas as pd

from utils.data_management.data_cache import DataCache, get_cache


class TestDataCache(unittest.TestCase):
    def setUp(self):
        self.cache = DataCache(max_size=5)

    def test_initialization(self):
        self.assertEqual(self.cache.max_size, 5)
        self.assertEqual(self.cache.hits, 0)
        self.assertEqual(self.cache.misses, 0)

    def test_cache_miss(self):
        path = Path("/tmp/test.csv")
        result = self.cache.get(path, "2024-01-01", "2024-12-31")
        self.assertIsNone(result)
        self.assertEqual(self.cache.misses, 1)

    def test_cache_put_and_get(self):
        path = Path("/tmp/test.csv")
        df = pd.DataFrame({"a": [1, 2, 3]})
        self.cache.put(path, "2024-01-01", "2024-12-31", df)
        self.assertEqual(len(self.cache._cache), 1)

    def test_cache_stats(self):
        stats = self.cache.get_stats()
        self.assertIn("hits", stats)
        self.assertIn("misses", stats)
        self.assertIn("hit_rate", stats)

    def test_global_cache(self):
        cache = get_cache()
        self.assertIsInstance(cache, DataCache)


if __name__ == "__main__":
    unittest.main()
