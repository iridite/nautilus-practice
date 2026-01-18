import json
import os
from typing import Literal

from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from state import AgentState  # 引用之前定义的 state.py

# 初始化 DeepSeek-V3
model_parameter_adjust = ChatOpenAI(
    model="deepseek-ai/DeepSeek-V3.2",  # 官方 V3 的模型名通常是这个
    api_key=lambda: os.getenv("SF_API_KEY") or "",
    base_url=os.getenv("SF_BASE_URL"),
    temperature=0.3,  # 量化调参建议低采样，逻辑重写建议 0.7
)

model_logic_rewrite = ChatOpenAI(
    model="deepseek-ai/DeepSeek-V3.2",  # 官方 V3 的模型名通常是这个
    api_key=lambda: os.getenv("SF_API_KEY") or "",
    base_url=os.getenv("SF_BASE_URL"),
    temperature=0.7,  # 量化调参建议低采样，逻辑重写建议 0.7
)


# --- 节点 1: 策略分析与生成 (Researcher) ---
def researcher_node(state: AgentState):
    """DeepSeek 读取回测历史，判断是否需要回溯或突变"""

    # 提取最新的回测报表
    last_report = state["backtest_history"][-1] if state["backtest_history"] else "无"

    system_msg = """你是一个量化系统架构师。你的任务是通过回测数据优化 RS-Squeeze 策略。
    规则：
    1. 如果 Sharpe 连续下降，说明方向错了，必须【回溯】到历史最佳参数。
    2. 如果 Sharpe > 2.0 但交易次数 < 50，说明太严苛了，必须【放宽】滤网。
    3. 如果 Sharpe < 1.0 且交易次数多，说明是【假突破】受害者，必须增加过滤。
    4. 始终输出完整的 Python 代码。"""

    user_msg = f"当前最高Sharpe: {state['best_sharpe']}\n最新回测结果: {last_report}\n当前代码: {state['strategy_code']}"

    # 这里我们让 DeepSeek 决定是微调还是突变
    model = None
    if state["fail_count"] < 3:
        print("Model selected: model_parameter_adjust")
        model = model_parameter_adjust
    else:
        print("Model selected: model_logic_rewrite")
        model = model_logic_rewrite

    response = model.invoke(
        [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]
    )

    return {
        "strategy_code": response.content,
        "current_direction": "微调参数" if state["fail_count"] < 3 else "逻辑重构",
    }


# --- 节点 2: 自动化回测执行 (Backtester) ---
def backtester_node(state: AgentState):
    """将代码写入本地并执行终端命令"""
    # 写入文件
    with open("strategy/rs_squeeze.py", "w") as f:
        f.write(state["strategy_code"])

    print("--- 启动本地回测引擎 ---")
    # 执行你的回测脚本 (需确保脚本输出可解析的 JSON)
    # 示例：stream = os.popen("uv run python run_backtest.py --json")
    # report = json.loads(stream.read())

    _ = os.popen("uv run main.py backtest --type high")

    import glob

    # 获取最新的结果文件
    files = glob.glob("log/backtest/result/RSSqueezeStrategy_*.json")
    latest_file = max(files, key=os.path.getmtime)
    with open(latest_file, "r") as f:
        report: dict = json.load(f)

    # 读取并标准化关键指标 (处理动态键名和深层嵌套)
    sharpe: float = next(
        (v for k, v in report.get("returns", {}).items() if "Sharpe Ratio" in k), 0.0
    )
    total_trades = (
        report.get("trade_metrics", {}).get("analysis", {}).get("total_trades", 0)
    )

    # 将提取出的指标注入 report，确保后续路由逻辑 (maze_router) 能够统一访问
    report["sharpe"] = sharpe
    report["total_trades"] = total_trades

    if sharpe == 0:
        print("⚠️ 回测结果异常，Sharpe Ratio 为 0。")

    # 更新历史最佳
    best = max(state["best_sharpe"], sharpe)
    fail_inc = 1 if sharpe < state["best_sharpe"] else 0

    return {
        "backtest_history": state["backtest_history"] + [report],
        "best_sharpe": best,
        "fail_count": state["fail_count"] + fail_inc if fail_inc else 0,
    }


# --- 路由逻辑：迷宫出口或回溯 ---
def maze_router(state: AgentState) -> Literal["researcher", "end"]:
    last_report = state["backtest_history"][-1]

    # 出口条件：支撑生活的指标
    if last_report["sharpe"] > 2.5 and last_report["total_trades"] > 150:
        print("🎉 找到黄金参数！停止搜索。")
        return "end"

    # 如果失败次数太多，LangGraph Studio 的 Time Travel 会让你手动回溯
    # 这里我们允许它继续尝试，直到用户在 UI 中手动中断
    return "researcher"


# --- 构建图 ---
workflow = StateGraph(AgentState)
workflow.add_node("researcher", researcher_node)
workflow.add_node("backtester", backtester_node)

workflow.set_entry_point("researcher")
workflow.add_edge("researcher", "backtester")
workflow.add_conditional_edges(
    "backtester", maze_router, {"researcher": "researcher", "end": END}
)

# 编译，并在修改代码前设置人工审查断点
graph = workflow.compile(interrupt_before=["backtester"])
