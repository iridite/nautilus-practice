"""
数据加载缓存性能基准测试
"""
import time
from pathlib import Path

from utils.data_management.data_cache import get_cache
from utils.data_management.data_loader import load_ohlcv_csv

# 测试文件路径
test_file = Path("data/raw/BTCUSDT/binance-BTCUSDT-1h-2024-01-01_2025-12-31.csv")

if not test_file.exists():
    print(f"测试文件不存在: {test_file}")
    exit(1)

# 清空缓存
cache = get_cache()
cache.clear()

print("=" * 60)
print("数据加载缓存性能基准测试")
print("=" * 60)

# 第1次加载（无缓存）
start = time.perf_counter()
df1 = load_ohlcv_csv(test_file, start_date="2024-01-01", end_date="2025-12-31", use_cache=True)
time1 = time.perf_counter() - start

# 第2次加载（有缓存）
start = time.perf_counter()
df2 = load_ohlcv_csv(test_file, start_date="2024-01-01", end_date="2025-12-31", use_cache=True)
time2 = time.perf_counter() - start

# 第3次加载（有缓存）
start = time.perf_counter()
df3 = load_ohlcv_csv(test_file, start_date="2024-01-01", end_date="2025-12-31", use_cache=True)
time3 = time.perf_counter() - start

# 计算性能提升
speedup = time1 / time2 if time2 > 0 else 0
time_saved = time1 - time2

print(f"\n文件: {test_file.name}")
print(f"数据行数: {len(df1)}")
print(f"\n第1次加载（无缓存）: {time1*1000:.2f} ms")
print(f"第2次加载（有缓存）: {time2*1000:.2f} ms")
print(f"第3次加载（有缓存）: {time3*1000:.2f} ms")
print(f"\n性能提升: {speedup:.1f}x")
print(f"节省时间: {time_saved*1000:.2f} ms ({time_saved/time1*100:.1f}%)")

# 缓存统计
stats = cache.get_stats()
print("\n缓存统计:")
print(f"  命中: {stats['hits']}")
print(f"  未命中: {stats['misses']}")
print(f"  命中率: {stats['hit_rate']}")
print(f"  缓存项: {stats['cached_items']}/{stats['max_size']}")

print("\n" + "=" * 60)
print("测试完成！")
print("=" * 60)
