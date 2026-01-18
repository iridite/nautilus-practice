import glob
import json
import os
import subprocess
import time
from typing import Literal, Optional

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
    history = state.get("backtest_history", [])
    last_report: dict | None = history[-1] if history else None

    if last_report is None:
        print("No report available, loading actual json file...")
        last_report = get_latest_json_report()

    best_sharpe = state.get("best_sharpe", 0.0)
    best_strategy_code = state.get("best_code", "")
    strategy_code = state.get("strategy_code", "")

    if best_strategy_code == "":
        best_strategy_code = strategy_code

    if not strategy_code:
        print("Strategy code not in state, reading from file...")
        try:
            with open("strategy/rs_squeeze.py", "r") as f:
                strategy_code = f.read()
        except FileNotFoundError:
            strategy_code = "# No strategy code found"

    system_msg = """你是一个量化系统架构师。你的任务是通过回测数据优化 RS-Squeeze 策略.
    规则：
    1. 如果 Sharpe 连续下降，说明方向错了，必须【回溯】到历史最佳参数。
    2. 如果 Sharpe > 2.0 但交易次数 < 50，说明太严苛了，必须【放宽】滤网。
    3. 如果 Sharpe < 1.0 且交易次数多，说明是【假突破】受害者，必须增加过滤。
    4. 始终输出完整的 Python 代码。"""

    fail_count = state.get("fail_count", 0)

    user_msg = f"""
    --- 任务目标 ---
    当前最高Sharpe: {best_sharpe}
    历史上表现最好的代码参考: {best_strategy_code}

    --- 最新反馈 ---
    最新回测结果: {last_report}
    刚才尝试的代码（表现一般）: {strategy_code}
    连续失败次数: {fail_count}

    --- 规则 ---
    如果连续失败，请务必参考【历史上表现最好的代码】重新进行逻辑突变。
    """
    # 这里我们让 DeepSeek 决定是微调还是突变
    model = None
    if fail_count < 3:
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
        "strategy_code": extract_code(str(response.content)),
        "current_direction": "微调参数" if fail_count < 3 else "逻辑重构",
    }


# --- 节点 2: 自动化回测执行 (Backtester) ---
def backtester_node(state: AgentState):
    run_time = time.time()  # 记录开始时间
    """将代码写入本地并执行终端命令"""
    # 写入文件
    strategy_code = state.get("strategy_code", "")
    with open("strategy/rs_squeeze.py", "w") as f:
        f.write(strategy_code)

    print("--- 启动本地回测引擎 ---")
    try:
        # 使用 subprocess.run 强制等待回测完成
        _ = subprocess.run(
            ["uv", "run", "main.py", "backtest", "--type", "high"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"❌ 回测运行崩溃: {e.stderr}")
        # 注入一个极差的结果，强制触发失败逻辑
        report = {"sharpe": -1.0, "total_trades": 0, "returns": {}}
        return {
            "backtest_history": state.get("backtest_history", []) + [report],
            "fail_count": state.get("fail_count", 0) + 1,
        }

    report = get_latest_json_report(run_time)

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
    best_sharpe = state.get("best_sharpe", 0.0)
    fail_count = state.get("fail_count", 0)
    history = state.get("backtest_history", [])

    new_best_sharpe = max(best_sharpe, sharpe)

    update = {
        "backtest_history": history + [report],
        "best_sharpe": new_best_sharpe,
    }

    if sharpe > best_sharpe:
        # 破了新高，重置失败计数，更新最佳代码
        update["best_strategy_code"] = state.get("strategy_code")
        update["fail_count"] = 0
    else:
        # 没破新高，累加失败计数
        update["fail_count"] = fail_count + 1

    return update


def extract_code(text: str) -> str:
    """提取 Markdown 格式中的纯代码内容"""
    if "```python" in text:
        return text.split("```python")[1].split("```")[0].strip()
    elif "```" in text:
        return text.split("```")[1].split("```")[0].strip()
    return text.strip()


def get_latest_json_report(run_time: Optional[float] = None) -> dict:
    # 获取最新的结果文件
    files = glob.glob("log/backtest/result/RSSqueezeStrategy_*.json")

    if run_time is not None:
        print(f"Filtering files modified after {run_time}")
        files = [file for file in files if os.path.getmtime(file) > run_time]
    else:
        print("No run_time provided")

    if not files and run_time:
        print(f"⚠️ No backtest result JSON files after {run_time} found.")
        return {
            "returns": {"Sharpe Ratio": 0.0},
            "trade_metrics": {"analysis": {"total_trades": 0}},
        }
    elif not files:
        print("⚠️ No backtest result JSON files found.")
        return {
            "returns": {"Sharpe Ratio": 0.0},
            "trade_metrics": {"analysis": {"total_trades": 0}},
        }

    latest_file = max(files, key=os.path.getmtime)
    with open(latest_file, "r") as f:
        report: dict = json.load(f)
        return report


# --- 路由逻辑：迷宫出口或回溯 ---
def maze_router(state: AgentState) -> Literal["researcher", "end"]:
    history = state.get("backtest_history", [])
    if not history:
        return "researcher"

    last_report = history[-1]

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
graph = workflow.compile(interrupt_before=["researcher"])
