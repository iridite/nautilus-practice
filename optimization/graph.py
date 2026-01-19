### 13. `optimization/graph.py` - **完整版**

"""
Graph 定义和构建
"""

from typing import Literal

from langgraph.graph import END, StateGraph

from .config import MAX_ITERATIONS
from .nodes import backtester_node, researcher_node
from .state import AgentState


def should_continue_router(state: AgentState) -> Literal["backtester", "end"]:
    """
    决定是否继续优化
    """
    # 检查是否达成目标
    if state.get("goal_achieved", False):
        print("\n" + "=" * 80)
        print("🎉🎉🎉 优化目标已达成！")
        print("=" * 80)
        return "end"

    # 检查是否需要初始回测
    if state.get("needs_initial_backtest", False):
        print("\n需要先进行初始回测")
        return "backtester"

    # 安全阀：最大迭代次数
    iteration = state.get("iteration", 0)
    if iteration >= MAX_ITERATIONS:
        print(f"\n⚠️ 达到最大迭代次数 ({iteration})，停止优化")
        return "end"

    # 继续优化
    return "backtester"


def create_optimization_graph():
    """
    创建优化 Graph

    流程:
    1. 研究节点 (researcher)
       - 评估目标达成度
       - 分析回测结果 / Debug 信息
       - 生成优化后的策略代码

    2. 判断是否继续
       - 达成目标 → 结束
       - 需要回测 → 回测节点
       - 超过最大迭代 → 结束

    3. 回测节点 (backtester)
       - 执行回测
       - 自动修复错误（最多3次）
       - 返回结果或回滚

    4. 循环回到研究节点
    """
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("researcher", researcher_node)
    workflow.add_node("backtester", backtester_node)

    # 设置入口点
    workflow.set_entry_point("researcher")

    # 添加边
    # 研究节点 → 判断是否继续 → 回测节点 or 结束
    workflow.add_conditional_edges(
        "researcher",
        should_continue_router,
        {
            "backtester": "backtester",
            "end": END,
        },
    )

    # 回测节点 → 研究节点（继续循环）
    workflow.add_edge("backtester", "researcher")

    # 编译，设置人工审查点
    graph = workflow.compile(
        # interrupt_before=["researcher"],  # 在研究节点前暂停，允许人工审查
    )

    return graph


# 创建全局 graph 实例
graph = create_optimization_graph()
