"""
测试脚本：快速验证 Graph 是否正常工作
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from optimization import graph
from optimization.state import AgentState


def test_graph_structure():
    """测试 Graph 结构"""
    print("=" * 60)
    print("测试 1: Graph 结构")
    print("=" * 60)

    # 检查节点
    nodes = list(graph.nodes.keys())
    print(f"节点列表: {nodes}")

    assert "researcher" in nodes, "缺少 researcher 节点"
    assert "backtester" in nodes, "缺少 backtester 节点"

    print("✅ Graph 结构正常\n")


def test_state_structure():
    """测试 State 结构"""
    print("=" * 60)
    print("测试 2: State 结构")
    print("=" * 60)

    test_state: AgentState = {
        "optimization_target": {"target_sharpe": 2.0},
        "initial_strategy_code": "# test code",
        "strategy_code": "# test code",
        "previous_strategy_code": "",
        "code_run_successful": True,
        "current_backtest_result": None,
        "backtest_history": [],
        "best_metrics": None,
        "best_strategy_code": "",
        "optimization_mode": "parameter_tuning",
        "last_optimization_mode": "",
        "fail_count": 0,
        "iteration": 0,
        "debug_record": None,
        "debug_history": [],
        "evaluation_report": "",
        "optimization_analysis": "",
        "goal_achieved": False,
        "needs_initial_backtest": False,
    }

    print(f"State 字段数: {len(test_state)}")
    print("✅ State 结构正常\n")


def test_imports():
    """测试所有导入是否正常"""
    print("=" * 60)
    print("测试 3: 模块导入")
    print("=" * 60)

    try:
        from optimization import (
            AgentState,
            BacktestMetrics,
            DebugRecord,
            OptimizationTarget,
            graph,
        )

        print("✅ optimization 主模块导入成功")

        from optimization.nodes import backtester_node, researcher_node

        print("✅ nodes 模块导入成功")

        from optimization.utils import (
            extract_code,
            extract_metrics_from_report,
            read_strategy_file,
        )

        print("✅ utils 模块导入成功")

        from optimization.prompts import (
            get_debugger_system_prompt,
            get_evaluator_system_prompt,
        )

        print("✅ prompts 模块导入成功")

        print("\n✅ 所有模块导入正常\n")

    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        raise


def test_config():
    """测试配置"""
    print("=" * 60)
    print("测试 4: 配置")
    print("=" * 60)

    from optimization.config import (
        MAX_DEBUG_ATTEMPTS,
        MAX_ITERATIONS,
        MODEL_NAME,
        STRATEGY_FILE_PATH,
    )

    print(f"模型名称: {MODEL_NAME}")
    print(f"策略文件路径: {STRATEGY_FILE_PATH}")
    print(f"最大 Debug 尝试: {MAX_DEBUG_ATTEMPTS}")
    print(f"最大迭代次数: {MAX_ITERATIONS}")

    print("\n✅ 配置加载正常\n")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("🧪 开始测试 LangGraph 优化系统")
    print("=" * 60 + "\n")

    try:
        test_imports()
        test_config()
        test_state_structure()
        test_graph_structure()

        print("=" * 60)
        print("✅ 所有测试通过！")
        print("=" * 60)
        print("\n系统已准备就绪，可以运行优化流程。")
        print("运行命令: python scripts/run_optimization.py\n")

    except Exception as e:
        print("\n" + "=" * 60)
        print(f"❌ 测试失败: {e}")
        print("=" * 60)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
