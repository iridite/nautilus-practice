import os

from langchain_anthropic import ChatAnthropic
from langgraph.graph import END, StateGraph

from state import AgentState

# 初始化 Claude 3.5 Sonnet
model = ChatAnthropic(model="claude-3-5-sonnet-20241022")


# --- 节点 1: 研究员 (Researcher) ---
def researcher_node(state: AgentState):
    """Claude 分析历史，提出新代码或调整方向"""
    print("\n[Node: Researcher] Claude 正在推演迷宫路径...")

    # 构建 Prompt：包含历史失败和当前 Sharpe
    prompt = f"""你是一位天才量化研究员。
    当前最佳夏普: {state["best_sharpe"]}
    历史回测记录: {state["backtest_history"][-3:]}
    当前代码: {state["strategy_code"]}

    请分析原因并给出改进方案。如果是死胡同，请尝试切换思路（如从 RS 加速切换到 均值回归）。
    输出必须是一个有效的 Python 策略类。"""

    response = model.invoke(prompt)
    # 模拟更新代码逻辑
    return {
        "strategy_code": response.content,
        "thought_process": state["thought_process"] + ["提出了新的优化方向"],
    }


# --- 节点 2: 回测执行器 (Backtester) ---
def backtester_node(state: AgentState):
    """在本地运行 NautilusTrader 回测"""
    print("\n[Node: Backtester] 正在执行本地回测命令...")

    # 1. 将 state['strategy_code'] 写入本地文件 strategies/evolved_strategy.py
    with open("strategies/evolved_strategy.py", "w") as f:
        f.write(state["strategy_code"])

    # 2. 调用终端运行回测 (这里需要你现有的回测运行脚本)
    # result = os.popen("uv run python run_backtest.py").read()

    # 模拟一个结果
    new_result = {"sharpe": 2.1, "win_rate": 0.45, "avg_winner": 5.2}
    return {"backtest_history": state["backtest_history"] + [new_result]}


# --- 逻辑路由: 判断是否走进死胡同 ---
def router(state: AgentState):
    last_sharpe = state["backtest_history"][-1]["sharpe"]

    if last_sharpe > state["best_sharpe"]:
        print("--- 进步了！继续深入探索 ---")
        return "continue"

    if state["fail_count"] > 3:
        print("--- 撞墙了！执行逻辑回溯 ---")
        return "backtrack"

    return "try_again"


# --- 构建图逻辑 ---
workflow = StateGraph(AgentState)

workflow.add_node("researcher", researcher_node)
workflow.add_node("backtester", backtester_node)

workflow.set_entry_point("researcher")
workflow.add_edge("researcher", "backtester")

# 设置条件路由
workflow.add_conditional_edges(
    "backtester",
    router,
    {
        "continue": "researcher",  # 继续优化
        "backtrack": "researcher",  # 改变方向重新开始
        "try_again": "researcher",  # 微调参数
    },
)

# --- 关键：人工干预与防烧钱设置 ---
# 强制在“调用 Claude API 节点”之前暂停，让你在 Web UI 审核它打算怎么改
graph = workflow.compile(interrupt_before=["researcher"])
