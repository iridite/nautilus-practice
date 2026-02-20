# 性能分析工具

用于分析回测引擎和策略的性能瓶颈。

## 📦 模块组成

### 1. BacktestProfiler（性能分析器）

使用 cProfile 分析代码性能。

**主要功能**：
- 分析单个函数的性能
- 使用上下文管理器分析代码块
- 保存性能数据到文件
- 生成性能摘要

**使用示例**：
```python
from utils.profiling import BacktestProfiler

# 创建分析器
profiler = BacktestProfiler()

# 方法 1：分析函数
result, stats = profiler.profile_function(my_function, arg1, arg2)
profiler.print_summary(top_n=20)

# 方法 2：使用上下文管理器
with profiler.profile_with_context("my_analysis"):
    # 要分析的代码
    run_backtest()

profiler.print_summary()
```

### 2. ProfileAnalyzer（分析结果分析器）

加载和分析 cProfile 生成的性能数据。

**主要功能**：
- 加载性能数据文件
- 识别性能热点
- 查找性能瓶颈
- 分析 I/O 操��
- 对比多次运行
- 导出分析结果

**使用示例**：
```python
from utils.profiling import ProfileAnalyzer

# 加载性能数据
analyzer = ProfileAnalyzer("output/profiling/my_backtest.prof")

# 打印摘要
analyzer.print_summary(top_n=20)

# 获取性能热点
hotspots = analyzer.get_hotspots(20)
for hotspot in hotspots:
    print(f"{hotspot['function']}: {hotspot['cumulative_time']:.4f}s")

# 查找瓶颈（占用时间 > 5%）
bottlenecks = analyzer.find_bottlenecks(threshold_pct=5.0)

# 分析 I/O 操作
io_operations = analyzer.get_io_operations()

# 导出到 JSON
analyzer.export_to_json("output/profiling/analysis.json")
```

### 3. ProfileReporter（报告生成器）

生成格式化的性能分析报告。

**主要功能**：
- 生成文本格式报告
- 生成 Markdown 格式报告
- 保存报告到文件

**使用示例**：
```python
from utils.profiling import ProfileAnalyzer, ProfileReporter

# 分析性能数据
analyzer = ProfileAnalyzer("output/profiling/my_backtest.prof")
hotspots = analyzer.get_hotspots(20)
bottlenecks = analyzer.find_bottlenecks(threshold_pct=5.0)
io_operations = analyzer.get_io_operations()

# 生成报告
reporter = ProfileReporter()

# 文本报告
text_report = reporter.generate_text_report(
    hotspots=hotspots,
    bottlenecks=bottlenecks,
    io_operations=io_operations,
)
print(text_report)

# 保存报告
reporter.save_report(text_report, "my_backtest_report", format="txt")

# Markdown 报告
md_report = reporter.generate_markdown_report(
    hotspots=hotspots,
    bottlenecks=bottlenecks,
    io_operations=io_operations,
)
reporter.save_report(md_report, "my_backtest_report", format="md")
```

## 🎯 典型使用场景

### 场景 1：分析回测引擎性能

```python
from pathlib import Path
from utils.profiling import BacktestProfiler
from backtest.engine_high import run_high_level
from core.schemas import BacktestConfig

# 创建性能分析器
profiler = BacktestProfiler()

# 加载回测配置
cfg = BacktestConfig.from_yaml("config/backtest/my_strategy.yaml")

# 使用上下文管理器分析回测
with profiler.profile_with_context("my_strategy_backtest"):
    run_high_level(cfg, Path.cwd())

# 打印摘要
profiler.print_summary(top_n=30)
```

### 场景 2：找出性能瓶颈

```python
from utils.profiling import ProfileAnalyzer, ProfileReporter

# 加载性能数据
analyzer = ProfileAnalyzer("output/profiling/my_strategy_backtest.prof")

# 查找瓶颈（占用时间 > 3%）
bottlenecks = analyzer.find_bottlenecks(threshold_pct=3.0)

print(f"发现 {len(bottlenecks)} 个性能瓶颈:")
for bottleneck in bottlenecks:
    print(f"  {bottleneck['function']}: {bottleneck['percentage']:.2f}%")
```

### 场景 3：对比优化前后的性能

```python
from utils.profiling import ProfileAnalyzer

# 加载优化前的性能数据
analyzer_before = ProfileAnalyzer("output/profiling/before.prof")

# 加载优化后的性能数据
analyzer_after = ProfileAnalyzer("output/profiling/after.prof")

# 对比
comparison = analyzer_before.compare_with(analyzer_after)

print(f"共同函数数量: {comparison['common_functions']}")
print("\n性能变化最大的函数:")
for item in comparison['comparison'][:10]:
    print(f"  {item['function']}: {item['time_diff_pct']:+.2f}%")
```

### 场景 4：分析 I/O 操作

```python
from utils.profiling import ProfileAnalyzer

analyzer = ProfileAnalyzer("output/profiling/my_backtest.prof")

# 获取 I/O 操作
io_operations = analyzer.get_io_operations()

print("I/O 操作耗时:")
for op in io_operations[:10]:
    print(f"  {op['function']}: {op['cumulative_time']:.4f}s ({op['calls']} 次)")
```

### 场景 5：生成完整的性能报告

```python
from utils.profiling import ProfileAnalyzer, ProfileReporter

# 分析性能数据
analyzer = ProfileAnalyzer("output/profiling/my_backtest.prof")

# 收集分析结果
hotspots = analyzer.get_hotspots(30)
bottlenecks = analyzer.find_bottlenecks(threshold_pct=3.0)
io_operations = analyzer.get_io_operations()

# 生成报告
reporter = ProfileReporter()

# 生成并保存文本报告
text_report = reporter.generate_text_report(
    hotspots=hotspots,
    bottlenecks=bottlenecks,
    io_operations=io_operations,
)
reporter.save_report(text_report, "performance_report", format="txt")

# 生成并保存 Markdown 报告
md_report = reporter.generate_markdown_report(
    hotspots=hotspots,
    bottlenecks=bottlenecks,
    io_operations=io_operations,
)
reporter.save_report(md_report, "performance_report", format="md")

print("报告已生成！")
```

## 📊 报告示例

### 文本报告示例

```
================================================================================
性能分析报告
================================================================================

生成时间: 2024-02-20 18:30:00

📊 总体统计
--------------------------------------------------------------------------------
总耗时:           45.2341 秒
总调用次数:       1,234,567
唯一函数数量:     456

🔥 性能热点（前 20 个最耗时的函数）
--------------------------------------------------------------------------------
函数名                                       调用次数     累计时间       占比
--------------------------------------------------------------------------------
_import_data_to_catalog                        1,234     12.3456    27.32%
catalog_loader                                   456      8.9012    19.68%
_verify_data_consistency                       1,234      5.6789    12.56%
_count_csv_lines                               1,234      3.4567     7.64%
...

⚠️  性能瓶颈（占用时间 > 5%）
--------------------------------------------------------------------------------
  _import_data_to_catalog                      27.32% (12.3456s)
  catalog_loader                               19.68% (8.9012s)
  _verify_data_consistency                     12.56% (5.6789s)
  _count_csv_lines                              7.64% (3.4567s)

💾 I/O 操作（前 10 个）
--------------------------------------------------------------------------------
  read_csv                                      234 次 (4.5678s)
  load_ohlcv_csv                                123 次 (2.3456s)
  open                                        1,234 次 (1.2345s)
  ...

================================================================================
```

## 💡 性能优化建议

根据性能分析结果，可以采取以下优化措施：

### 1. 数据加载优化

如果发现 `read_csv` 或 `load_ohlcv_csv` 耗时较长：
- 使用 Parquet 格式代替 CSV（快 5-10 倍）
- 添加数据缓存机制
- 并行加载多个文件

### 2. 数据验证优化

如果发现 `_verify_data_consistency` 耗时较长：
- 简化验证逻辑
- 只在必要时验证
- 使用文件哈希代替逐行比较

### 3. 计算优化

如果发现策略计算函数耗时较长：
- 使用向量化操作代替循环
- 缓存重复计算的结果
- 使用 NumPy/Pandas 的优化函数

### 4. I/O 优化

如果发现大量 I/O 操作：
- 批量读写代替频繁的小文件操作
- 使用内存缓存
- 异步 I/O

## 🔧 高级用法

### 自定义分析

```python
from utils.profiling import ProfileAnalyzer

analyzer = ProfileAnalyzer("output/profiling/my_backtest.prof")

# 获取特定函数的调用树
call_tree = analyzer.get_call_tree("_import_data_to_catalog", max_depth=3)
print(call_tree)

# 自定义瓶颈阈值
bottlenecks = analyzer.find_bottlenecks(threshold_pct=2.0)
```

### 批量分析

```python
from pathlib import Path
from utils.profiling import ProfileAnalyzer

# 分析多个性能数据文件
profile_dir = Path("output/profiling")
for profile_file in profile_dir.glob("*.prof"):
    print(f"\n分析: {profile_file.name}")
    analyzer = ProfileAnalyzer(profile_file)
    analyzer.print_summary(top_n=10)
```

## 📝 注意事项

1. **性能开销**：性能分析会增加 10-30% 的运行时间
2. **文件大小**：性能数据文件可能较大（几 MB 到几十 MB）
3. **准确性**：多次运行取平均值更准确
4. **解读**：关注累计时间（cumulative time）而非总时间（total time）

## 🚀 快速开始

```python
# 1. 导入模块
from utils.profiling import BacktestProfiler

# 2. 创建分析器
profiler = BacktestProfiler()

# 3. 分析代码
with profiler.profile_with_context("my_analysis"):
    # 你的代码
    pass

# 4. 查看结果
profiler.print_summary()
```

## 📈 与回测引擎集成

性能分析工具可以无缝集成到现有的回测流程中，无需修改回测引擎代码：

```python
# 在回测脚本中添加性能分析
from utils.profiling import BacktestProfiler

profiler = BacktestProfiler()

with profiler.profile_with_context("backtest"):
    # 原有的回测代码
    run_high_level(cfg, base_dir)

# 自动生成性能报告
profiler.print_summary(top_n=30)
```

这样就可以在不修改回测引擎的情况下，找出性能瓶颈！
