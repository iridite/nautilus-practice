#!/usr/bin/env python
"""
性能优化基准测试

测试优化前后的性能对比：
1. 缓存大小从 100 增加到 500
2. 移除 CSV 行数统计
3. Parquet 元数据缓存
4. DataFrame 拷贝优化
"""

import time
from pathlib import Path
import sys

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.data_management.data_cache import get_cache


def benchmark_cache_stats():
    """测试缓存统计功能"""
    print("=" * 60)
    print("缓存配置测试")
    print("=" * 60)
    
    cache = get_cache()
    stats = cache.get_stats()
    
    print(f"✅ 缓存大小: {stats['max_size']}")
    print(f"✅ 当前缓存项: {stats['cached_items']}")
    print(f"✅ 命中率: {stats['hit_rate']}")
    print(f"✅ Parquet 元数据缓存项: {stats['metadata_cached_items']}")
    print(f"✅ Parquet 元数据命中率: {stats['metadata_hit_rate']}")
    print()


def benchmark_csv_loading():
    """测试 CSV 加载性能"""
    print("=" * 60)
    print("CSV 加载性能测试")
    print("=" * 60)
    
    # 查找测试数据文件
    data_dir = project_root / "data" / "csv"
    if not data_dir.exists():
        print("⚠️  未找到测试数据目录")
        return
    
    csv_files = list(data_dir.glob("*.csv"))
    if not csv_files:
        print("⚠️  未找到 CSV 测试文件")
        return
    
    test_file = csv_files[0]
    print(f"测试文件: {test_file.name}")
    
    from utils.data_management.data_loader import load_ohlcv_csv
    
    # 首次加载（无缓存）
    cache = get_cache()
    cache.clear()
    
    start = time.time()
    df1 = load_ohlcv_csv(test_file, use_cache=True)
    first_load_time = time.time() - start
    
    print(f"✅ 首次加载: {first_load_time:.3f}s ({len(df1)} 行)")
    
    # 第二次加载（有缓存）
    start = time.time()
    df2 = load_ohlcv_csv(test_file, use_cache=True)
    cached_load_time = time.time() - start
    
    print(f"✅ 缓存加载: {cached_load_time:.3f}s ({len(df2)} 行)")
    
    if cached_load_time > 0:
        speedup = first_load_time / cached_load_time
        print(f"✅ 加速比: {speedup:.1f}x")
    
    print()


def benchmark_parquet_loading():
    """测试 Parquet 加载性能"""
    print("=" * 60)
    print("Parquet 加载性能测试")
    print("=" * 60)
    
    # 查找 Parquet 文件
    parquet_dir = project_root / "data" / "parquet"
    if not parquet_dir.exists():
        print("⚠️  未找到 Parquet 数据目录")
        return
    
    parquet_files = list(parquet_dir.rglob("*.parquet"))
    if not parquet_files:
        print("⚠️  未找到 Parquet 测试文件")
        return
    
    test_file = parquet_files[0]
    print(f"测试文件: {test_file.name}")
    
    try:
        from utils.data_management.data_loader import load_ohlcv_parquet
        
        # 清空缓存
        cache = get_cache()
        cache.clear()
        
        # 首次加载（无缓存）
        start = time.time()
        df1 = load_ohlcv_parquet(test_file, use_cache=True)
        first_load_time = time.time() - start
        
        print(f"✅ 首次加载: {first_load_time:.3f}s ({len(df1)} 行)")
        
        # 第二次加载（有缓存）
        start = time.time()
        df2 = load_ohlcv_parquet(test_file, use_cache=True)
        cached_load_time = time.time() - start
        
        print(f"✅ 缓存加载: {cached_load_time:.3f}s ({len(df2)} 行)")
        
        if cached_load_time > 0:
            speedup = first_load_time / cached_load_time
            print(f"✅ 加速比: {speedup:.1f}x")
        
        # 测试元数据缓存
        stats = cache.get_stats()
        print(f"✅ 元数据缓存命中: {stats['metadata_hits']}")
        
    except ImportError as e:
        print(f"⚠️  Parquet 支持未安装: {e}")
    
    print()


def main():
    """运行所有基准测试"""
    print("\n" + "=" * 60)
    print("Nautilus Practice 性能优化基准测试")
    print("=" * 60)
    print()
    
    benchmark_cache_stats()
    benchmark_csv_loading()
    benchmark_parquet_loading()
    
    print("=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
