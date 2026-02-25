# 问题三：数据一致性验证场景说明

## 验证对象

**比较对象**: CSV 文件 ↔️ Parquet 数据

- **CSV 文件**: 原始数据源（`data/raw/` 目录）
- **Parquet 数据**: 导入后的高性能存储（`data/parquet/` 目录）

## 验证时机

**时机**: 回测开始前的数据准备阶段

**具体位置**: `_import_data_to_catalog()` 函数中

```
回测流程：
1. 加载交易标的 ✅
2. 准备数据 ← 在这里进行验证
   ├─ 检查 Parquet 是否存在
   ├─ 检查 CSV 是否存在
   ├─ 验证数据一致性 ← _verify_data_consistency()
   └─ 决定是否重新导入
3. 运行回测引擎
4. 输出结果
```

## 验证场景

### 场景 1: Parquet 存在 + CSV 存在 ✅

**这是验证函数的主要使用场景**

```python
def _handle_parquet_exists(...):
    csv_exists = csv_path.exists()
    
    if csv_exists:
        # 调用验证函数
        is_consistent = _verify_data_consistency(csv_path, catalog, bar_type)
        
        if not is_consistent:
            # CSV 更新了，重新导入
            _update_parquet_from_csv(...)
        else:
            # 数据一致，跳过导入（性能优化）
            return "⏩ Verified"
```

**决策逻辑**:
- ✅ **一致** → 跳过导入，直接使用 Parquet（快速）
- ❌ **不一致** → 重新从 CSV 导入到 Parquet（确保最新）

### 场景 2: Parquet 存在 + CSV 不存在

不调用验证函数，直接使用 Parquet 数据

### 场景 3: Parquet 不存在

不调用验证函数，直接导入 CSV 或下载数据

## 验证目的

### ���心问题

**判断 Parquet 数据是否是从当前 CSV ���件导入的？**

### 为什么需要验证？

1. **性能优化**: 避免重复导入大文件
   - CSV 解析很慢（特别是大文件）
   - Parquet 读取很快（列式存储）
   - 如果数据一致，直接用 Parquet 可以节省大量时间

2. **数据更新检测**: 及时发现 CSV 更新
   - 用户可能修正了 CSV 中的错误数据
   - 用户可能下载了更完整的数据
   - 需要确保回测使用最新数据

### 实际案例

**案例 1: 数据修正**
```
1. 用户发现 CSV 数据有错误（如价格异常）
2. 用户修正 CSV 文件
3. 再次运行回测
4. 验证函数检测到不一致
5. 重新导入 CSV → Parquet
6. 回测使用修正后的数据 ✅
```

**案例 2: 数据未变**
```
1. 用户多次运行回测（调整策略参数）
2. CSV 文件未变化
3. 验证函数检测到一致
4. 跳过导入，直接使用 Parquet
5. 节省数据加载时间 ✅
```

## 当前验证方法的问题

### 方法 1: 文件修改时间比较

```python
csv_mtime = csv_path.stat().st_mtime
parquet_mtime = _get_parquet_mtime(catalog, bar_type)
if csv_mtime - parquet_mtime > 3600:  # 超过1小时
    return False  # 不一致
```

**问题**:
- ❌ 文件复制会改变修改时间
- ❌ 文件移动可能保留原时间
- ❌ 网络传输可能改变时间戳
- ❌ 不同文件系统的时间精度不同

**误判案例**:
```
1. 用户从备份恢复 CSV 文件
2. 文件内容相同，但修改时间变了
3. 验证函数误判为"不一致"
4. 触发不必要的重新导入 ❌
```

### 方法 2: 行数估算

```python
csv_line_count = _count_csv_lines(csv_path)
estimated_parquet_count = _estimate_parquet_count(existing_intervals)
# 假设1小时数据，估算数据点数量
```

**问题**:
- ❌ 假设数据是 1 小时周期（可能不对）
- ❌ 只使用第一个间隔进行估算
- ❌ 忽略了数据可能有缺失

**误判案例**:
```
1. CSV 有 1000 行数据
2. 估算 Parquet 有 950 行（估算不准）
3. 差异 5%，在 20% 容忍度内
4. 判断为"一致"
5. 但实际 CSV 已更新，只是行数变化不大 ❌
```

### 方法 3: 允许 20% 差异

```python
diff_ratio = abs(csv_line_count - estimated_parquet_count) / csv_line_count
return diff_ratio <= 0.2  # 允许 20% 差异
```

**问题**:
- ❌ 20% 的差异意味着可能缺失大量数据
- ❌ 对于关键回测数据，这个容忍度太高

**误判案例**:
```
1. CSV 有 1000 行数据
2. Parquet 只有 850 行（缺失 15%）
3. 在 20% 容忍度内，判断为"一致"
4. 回测使用不完整的数据 ❌
```

## 修复方案：文件哈希校验

### 核心思路

**计算 CSV 文件的哈希值，与上次导入时的哈希值比较**

```python
def _verify_data_consistency_strict(csv_path, catalog, bar_type, cache_file):
    # 1. 计算当前 CSV 文件哈希
    current_hash = _calculate_csv_hash(csv_path)  # MD5
    
    # 2. 从缓存获取上次导入时的哈希
    cached_hash = _get_cached_hash(csv_path, cache_file)
    
    # 3. 比较哈希值
    if current_hash == cached_hash:
        return True  # 一致，跳过导入
    else:
        return False  # 不一致，重新导入
```

### 优点

✅ **最可靠**: 任何内容变化都能检测（即使一个字节）
✅ **不依赖文件系统**: 不受修改时间、文件系统影响
✅ **行业标准**: Git、Docker 等都使用哈希校验
✅ **性能可接受**: 使用缓存后，只在首次计算时较慢

### 工作流程

```
首次导入：
1. 计算 CSV 哈希: a1b2c3d4...
2. 导入 CSV → Parquet
3. 保存哈希到缓存: {csv_path: "a1b2c3d4..."}

后续运行（CSV 未变）：
1. 计算 CSV 哈希: a1b2c3d4...
2. 从缓存读取: a1b2c3d4...
3. 比较: 一致 ✅
4. 跳过导入，使用 Parquet

后续运行（CSV 已更新）：
1. 计算 CSV 哈希: e5f6g7h8...
2. 从缓存读取: a1b2c3d4...
3. 比较: 不一致 ❌
4. 重新导入 CSV → Parquet
5. 更新缓存: {csv_path: "e5f6g7h8..."}
```

### 性能分析

**哈希计算时间**（MD5）:
- 小文件 (< 1MB): < 10ms
- 中等文件 (1-10MB): 10-100ms
- 大文件 (10-100MB): 100ms-1s

**优化策略**:
1. 使用缓存避免重复计算
2. 分块读取处理大文件
3. 提供快速模式作为备选

## 总结

### 验证对象
CSV 文件 ↔️ Parquet 数据

### 验证时机
回测开始前，数据准备阶段

### 验证目的
判断 Parquet 是否需要从 CSV 重新导入

### 当前问题
- 文件时间不可靠
- 行数估算不精确
- 容忍度太宽松

### 修复方案
使用文件哈希校验（MD5）+ 缓存机制

### 预期效果
- ✅ 准确检测 CSV 更新
- ✅ 避免不必要的重新导入
- ✅ 确保回测使用最新数据
- ✅ 性能开销可接受
