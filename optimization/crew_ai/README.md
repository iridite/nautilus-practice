# CrewAI 量化策略自动化研究系统

基于 CrewAI 的自动化量化策略研究流水线，实现行情分析、选币、策略设计、参数优化与风控审计的闭环迭代。

## 系统架构

### 五个核心 Agent

1. **Market Sentinel (行情哨兵)**
   - 监控宏观市场环境（波动率、基差、持仓总量）
   - 输出市场状态报告（极度贪婪/流动性枯竭/正常）

2. **Asset Scout (资产球探)**
   - 根据市场环境筛选 Top 5 交易品种
   - 基于 OI 深度和流动性评分

3. **Strategy Architect (策略架构师)**
   - 动态调整策略参数（Z-Score 窗口、OI 阈值、资金费率）
   - 输出适配品种的策略配置

4. **Optimization Engineer (优化工程师)**
   - 调用 NautilusTrader 执行多组合回测
   - 输出参数敏感性分析和"参数平原"

5. **Risk Auditor (风控审计员)**
   - 检查过拟合、最大回撤、参数敏感性
   - 输出最终决策（Pass/Fail/Conditional Pass）

### 任务流水线（Context-Aware）

```
Market Analysis → Asset Selection → Strategy Design → Backtest Optimization → Risk Audit
     (任务1)          (任务2)           (任务3)              (任务4)              (任务5)
```

每个任务的输出作为下一个任务的 Context 输入，实现有机连接。

## 安装

```bash
cd /home/yixian/Projects/nautilus-practice
uv sync
```

## 使用方法

### 方式1: 命令行运行

```bash
python -m optimization.crew_ai.main \
    --symbol BTCUSDT \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --output-dir ./output
```

### 方式2: Python 脚本调用

```python
from optimization.crew_ai import run_strategy_research_pipeline

result = run_strategy_research_pipeline(
    symbol="SOLUSDT",
    start_date="2024-06-01",
    end_date="2024-12-31"
)
```

## NautilusTrader 桥接

系统通过 `tools.py` 中的 `@tool` 装饰器封装了三个核心工具：

1. **NautilusBacktest**: 执行回测并返回 Sharpe/Sortino/MaxDD
2. **MarketDataAnalyzer**: 分析市场波动率和持仓量
3. **AssetScreener**: 筛选高潜力交易品种

工具自动调用 `main.py backtest` 并解析结果。

## 输出结果

执行完成后，系统会在 `output/` 目录生成：

```
research_result_BTCUSDT_2024-01-01_2024-12-31.json
```

包含：
- 市场分析报告
- 推荐品种列表
- 策略参数配置
- 回测结果（多组参数）
- 风控审计意见

## 监控与日志

系统使用 `verbose=2` 模式，会输出详细的 Agent 决策过程：

```
[Market Sentinel] Analyzing market conditions...
[Asset Scout] Screening 150 symbols...
[Strategy Architect] Designing parameters for BTCUSDT...
[Optimization Engineer] Running backtest with params: {...}
[Risk Auditor] Checking for overfitting...
```

## 扩展开发

### 添加新的 Agent

在 `agents.py` 中定义：

```python
def create_new_agent() -> Agent:
    return Agent(
        role="New Role",
        goal="...",
        backstory="...",
        tools=[...],
        verbose=True
    )
```

### 添加新的 Tool

在 `tools.py` 中使用 `@tool` 装饰器：

```python
@tool("ToolName")
def new_tool(param: str) -> str:
    """工具描述"""
    # 实现逻辑
    return json.dumps(result)
```

## 注意事项

1. **数据依赖**: 确保 `data/csv/` 目录下有对应品种的 OI 和 Funding Rate 数据
2. **回测时间**: 单次回测约需 30-60 秒，多参数优化可能需要 5-10 分钟
3. **内存占用**: 建议至少 4GB 可用内存
4. **Python 版本**: 需要 Python 3.10+

## 故障排查

### 问题1: 找不到 crewai 模块

```bash
pip install crewai crewai-tools
```

### 问题2: NautilusTrader 回测失败

检查 `main.py` 路径和虚拟环境：

```python
# tools.py:21
cmd = [
    str(base_dir / ".venv/bin/python"),  # 确保路径正确
    str(base_dir / "main.py"),
    ...
]
```

### 问题3: 数据文件缺失

运行数据获取：

```bash
python main.py backtest --type high
```

系统会自动下载缺失的 OI 和 Funding Rate 数据。

## 版本历史

- **v1.0.0** (2026-01-29): 初始版本，实现五个核心 Agent 和任务流水线
