# 策略性能分析工具

用于计算和对比策略回测结果的性能指标。

## 📦 模块组成

### 1. PerformanceMetrics（性能指标计算器）

计算单个策略的各项性能指标。

**主要功能**：
- 收益率指标：总收益、年化收益
- 风险指标：最大回撤、波动率、下行波动率
- 风险调整收益指标：夏普率、索提诺比率、卡玛比率
- 交易统计：胜率、盈亏比、平均盈亏、交易次数

**使用示例**：
```python
from utils.performance import PerformanceMetrics
import pandas as pd

# 准备权益曲线数据
equity_curve = pd.Series([100000, 101000, 102500, ...], index=dates)

# 准备交易记录（可选）
trades = pd.DataFrame({
    'pnl': [500, -200, 800, -150, ...]
})

# 创建指标计算器
metrics = PerformanceMetrics(equity_curve, trades)

# 计算所有指标
all_metrics = metrics.get_all_metrics(
    risk_free_rate=2.0,  # 无风险利率 2%
    trading_days=365
)

# 访问具体指标
print(f"总收益率: {all_metrics['total_return']:.2f}%")
print(f"夏普比率: {all_metrics['sharpe_ratio']:.2f}")
print(f"最大回撤: {all_metrics['max_drawdown']:.2f}%")
print(f"胜率: {all_metrics['win_rate']:.2f}%")
```

### 2. StrategyAnalyzer（策略分析器）

用于对比和分析多个策略的回测结果。

**主要功能**：
- 添加多个策略的回测数据
- 计算和对比所有策略的指标
- 按指定指标排名策略
- 筛选符合条件的策略
- 计算策略收益率相关性

**使用示例**：
```python
from utils.performance import StrategyAnalyzer

# 创建分析器
analyzer = StrategyAnalyzer()

# 添加策略
analyzer.add_strategy("策略A", equity_curve_a, trades_a)
analyzer.add_strategy("策略B", equity_curve_b, trades_b)
analyzer.add_strategy("策略C", equity_curve_c, trades_c)

# 对比所有策略
comparison = analyzer.compare_strategies()
print(comparison)

# 按夏普率排名
ranked = analyzer.rank_strategies(by="sharpe_ratio")
print(ranked)

# 获取最佳策略
best_name, best_metrics = analyzer.get_best_strategy(by="sharpe_ratio")
print(f"最佳策略: {best_name}")

# 筛选策略（夏普率 > 1.5，最大回撤 < 15%）
filtered = analyzer.filter_strategies(
    min_sharpe=1.5,
    max_drawdown=15.0
)
print(f"符合条件的策略: {filtered}")

# 计算相关性矩阵
correlation = analyzer.get_correlation_matrix()
print(correlation)
```

### 3. ReportGenerator（报告生成器）

生成格式化的分析报告。

**主要功能**：
- 生成文本格式报告
- 生成 Markdown 格式报告
- 导出 CSV/Excel 文件
- 生成汇总表格

**使用示例**：
```python
from utils.performance import ReportGenerator

# 创建报告生成器
generator = ReportGenerator(analyzer)

# 生成单个策略的文本报告
report = generator.generate_text_report("策略A")
print(report)

# 生成多策略对比报告
comparison_report = generator.generate_text_report()
print(comparison_report)

# 生成 Markdown 报告
md_report = generator.generate_markdown_report()
with open("report.md", "w") as f:
    f.write(md_report)

# 导出 CSV
generator.export_to_csv("comparison.csv")

# 导出 Excel（包含多个工作表）
generator.export_to_excel("comparison.xlsx")
```

## 📊 支持的性能指标

### 收益指标
- `total_return`: 总收益率（%）
- `annualized_return`: 年化收益率（%）

### 风险指标
- `max_drawdown`: 最大回撤（%）
- `max_drawdown_duration`: 最大回撤持续天数
- `volatility`: 波动率（年化，%）
- `downside_volatility`: 下行波动率（年化，%）

### 风险调整收益指标
- `sharpe_ratio`: 夏普比率
- `sortino_ratio`: 索提诺比率
- `calmar_ratio`: 卡玛比率

### 交易统计
- `total_trades`: 总交易次数
- `win_rate`: 胜率（%）
- `profit_factor`: 盈亏比
- `average_trade`: 平均每笔盈亏

### 时间信息
- `start_date`: 开始日期
- `end_date`: 结束日期
- `total_days`: 总天数

## 🎯 典型使用场景

### 场景 1：快速评估单个策略

```python
from utils.performance import PerformanceMetrics

metrics = PerformanceMetrics(equity_curve, trades)
all_metrics = metrics.get_all_metrics()

# 快速查看关键指标
print(f"年化收益: {all_metrics['annualized_return']:.2f}%")
print(f"最大回撤: {all_metrics['max_drawdown']:.2f}%")
print(f"夏普比率: {all_metrics['sharpe_ratio']:.2f}")
```

### 场景 2：对比多个策略并选择最佳

```python
from utils.performance import StrategyAnalyzer, ReportGenerator

analyzer = StrategyAnalyzer()

# 添加所有策略
for name, equity, trades in strategies:
    analyzer.add_strategy(name, equity, trades)

# 生成对比报告
generator = ReportGenerator(analyzer)
print(generator.generate_text_report())

# 找出最佳策略
best_name, _ = analyzer.get_best_strategy(by="sharpe_ratio")
print(f"推荐策略: {best_name}")
```

### 场景 3：筛选符合风险要求的策略

```python
# 筛选条件：
# - 夏普率 > 1.5
# - 最大回撤 < 15%
# - 胜率 > 60%
# - 至少 50 笔交易

filtered = analyzer.filter_strategies(
    min_sharpe=1.5,
    max_drawdown=15.0,
    min_win_rate=60.0,
    min_trades=50
)

print(f"符合风险要求的策略: {filtered}")
```

### 场景 4：分析策略相关性

```python
# 计算策略收益率相关性
correlation = analyzer.get_correlation_matrix()

# 找出低相关性的策略组合（用于分散风险）
print(correlation)
```

## 💡 注意事项

1. **权益曲线格式**：必须是 pandas Series，索引为日期时间
2. **交易记录格式**：必须是 pandas DataFrame，包含 `pnl` 列
3. **无风险利率**：默认为 0，可根据实际情况调整（如 2.0 表示 2%）
4. **交易天数**：默认 365 天，加密货币市场建议使用 365，股票市场使用 252

## 🚀 快速开始

```python
# 1. 导入模块
from utils.performance import PerformanceMetrics, StrategyAnalyzer, ReportGenerator
import pandas as pd

# 2. 准备数据
equity_curve = pd.Series([...], index=dates)
trades = pd.DataFrame({'pnl': [...]})

# 3. 计算指标
metrics = PerformanceMetrics(equity_curve, trades)
all_metrics = metrics.get_all_metrics()

# 4. 查看结果
print(all_metrics)
```

## 📈 与 NautilusTrader 集成

从 NautilusTrader 回测结果中提取数据：

```python
# 从回测引擎获取账户数据
account = engine.trader.generate_account_report(venue)

# 提取权益曲线
equity_curve = pd.Series(
    account.balances,
    index=account.timestamps
)

# 提取交易记录
trades = pd.DataFrame([
    {'pnl': trade.realized_pnl}
    for trade in engine.trader.generate_order_fills_report()
])

# 分析性能
metrics = PerformanceMetrics(equity_curve, trades)
```

## 🔧 扩展性

可以轻松添加自定义指标：

```python
class CustomMetrics(PerformanceMetrics):
    def custom_metric(self):
        # 实现自定义指标
        return ...
```

## 📝 输出示例

### 文本报告示例

```
================================================================================
策略分析报告: Keltner RS Breakout
================================================================================

生成时间: 2024-02-20 18:30:00

📊 收益指标
--------------------------------------------------------------------------------
  总收益率:                45.23%
  年化收益率:              38.67%

⚠️  风险指标
--------------------------------------------------------------------------------
  最大回撤:                12.45%
  回撤持续天数:                 23 天
  波动率 (年化):           18.34%
  下行波动率 (年化):       11.23%

📈 风险调整收益指标
--------------------------------------------------------------------------------
  夏普比率:                 2.11
  索提诺比率:               3.44
  卡玛比率:                 3.11

💼 交易统计
--------------------------------------------------------------------------------
  总交易次数:                 156
  胜率:                    65.38%
  盈亏比:                   2.34
  平均每笔盈亏:           234.56

📅 时间信息
--------------------------------------------------------------------------------
  开始日期:           2024-01-01
  结束日期:           2024-12-31
  总天数:             365 天

================================================================================
```

## 🎓 最佳实践

1. **始终使用真实的交易记录**：包含完整的盈亏数据
2. **对比多个策略时使用相同的时间段**：确保公平对比
3. **关注风险调整收益指标**：不要只看收益率
4. **定期更新分析**：随着数据增加重新计算指标
5. **结合相关性分析**：构建策略组合时考虑分散风险
