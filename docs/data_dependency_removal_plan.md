# 数据依赖系统删除计划

## 现状分析

### 代码分布
- **DataDependency 类**: 63行 (base.py:14-63)
- **BaseStrategyConfig 中的方法**: 约80行
  - `add_data_dependency()`: 35行
  - `get_required_dependencies()`: 3行
  - `get_optional_dependencies()`: 3行
  - `has_oi_dependency()`: 3行
  - `has_funding_dependency()`: 3行
  - `get_dependency_by_type()`: 3行
  - 配置参数: 4个字段
- **BaseStrategy 中的方法**: 约80行
  - `_check_data_dependencies()`: 30行
  - `_is_dependency_satisfied()`: 18行
  - `get_data_requirements()`: 32行

**总计**: 约 223 行代码

### 核心问题

1. **占位实现**: `_is_dependency_satisfied()` 永远返回 True
2. **无实际价值**: 所有检查都是形式化的，不产生实际效果
3. **职责错位**: 数据依赖检查应该在 main.py 的回测引擎中，而非策略基类
4. **过度设计**: 完整的类和方法体系，但实际只需要简单的配置列表

## 删除方案

### 第一步：删除 DataDependency 类
- 删除整个类定义（63行）
- 删除相关 import

### 第二步：简化 BaseStrategyConfig
删除以下内容：
```python
# 删除字段
data_dependencies: List[DataDependency] = []
enable_auto_data_fetch: bool = True
default_data_exchange: Optional[str] = None
default_data_period: str = "1h"

# 删除方法
add_data_dependency()
get_required_dependencies()
get_optional_dependencies()
has_oi_dependency()
has_funding_dependency()
get_dependency_by_type()
```

**保留**：
```python
# 简化为简单的字符串列表（如果真的需要）
data_types: List[str] = []  # 例如: ["ohlcv", "oi"]
```

### 第三步：删除 BaseStrategy 中的方法
删除以下方法：
- `_check_data_dependencies()` (30行)
- `_is_dependency_satisfied()` (18行)
- `get_data_requirements()` (32行)

从 `on_start()` 中删除调用：
```python
# 删除这一行
self._check_data_dependencies()
```

### 第四步：迁移到 main.py（如果需要）
在 main.py 的回测引擎中添加简单的数据检查：
```python
def check_required_data(strategy_config, data_path):
    """检查策略所需的数据文件是否存在"""
    if hasattr(strategy_config, 'data_types'):
        for data_type in strategy_config.data_types:
            # 简单的文件存在性检查
            if not os.path.exists(f"{data_path}/{data_type}.parquet"):
                raise FileNotFoundError(f"Missing {data_type} data")
```

## 预期收益

1. **代码减少**: 约 223 行 → 0 行（或保留 10 行简化版）
2. **复杂度降低**: 删除 1 个类 + 9 个方法
3. **职责清晰**: 数据检查移到正确的位置（main.py）
4. **维护性提升**: 更少的代码，更少的抽象

## 风险评估

**低风险**：
- 当前实现是占位符，无实际功能
- 没有外部依赖这些方法
- 策略子类不使用这些功能

## 实施步骤

1. 搜索所有使用 DataDependency 的地方
2. 确认没有策略子类依赖这些方法
3. 删除 DataDependency 类
4. 删除 BaseStrategyConfig 中的相关方法和字段
5. 删除 BaseStrategy 中的相关方法
6. 更新 on_start() 方法
7. 测试确保没有破坏现有功能
8. 提交更改

## 最终目标

base.py 从 698 行减少到约 475 行（减少 32%）
