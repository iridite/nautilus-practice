"""
优化系统运行脚本
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from optimization import graph
from optimization.config import DEFAULT_OPTIMIZATION_TARGET
from optimization.state import AgentState, OptimizationTarget


def run_optimization(
    target: OptimizationTarget = None,
    initial_code: str = None,
):
    """
    运行优化流程

    Args:
        target: 优化目标配置（不提供则使用默认值）
        initial_code: 初始策略代码（可选，不提供则从文件读取）

    Returns:
        final_state: 最终的状态
    """

    if target is None:
        target = DEFAULT_OPTIMIZATION_TARGET
        print("⚠️ 未提供优化目标，使用默认配置")

    # 初始化状态
    initial_state: AgentState = {
        # 用户输入
        "optimization_target": target,
        "initial_strategy_code": initial_code,
        # 策略状态
        "strategy_code": initial_code or "",
        "previous_strategy_code": "",
        "code_run_successful": True,
        # 回测结果
        "current_backtest_result": None,
        "backtest_history": [],
        # 最佳记录
        "best_metrics": None,
        "best_strategy_code": "",
        # 优化状态
        "optimization_mode": "parameter_tuning",
        "last_optimization_mode": "",
        "fail_count": 0,
        "iteration": 0,
        # 调试信息
        "debug_record": None,
        "debug_history": [],
        # 分析报告
        "evaluation_report": "",
        "optimization_analysis": "",
        # 控制标志
        "goal_achieved": False,
        "needs_initial_backtest": False,
    }

    config = {
        "recursion_limit": 200,  # 最大递归深度
    }

    print("\n" + "=" * 80)
    print("🚀 策略优化系统启动")
    print("=" * 80)
    print("\n优化目标:")
    for key, value in target.items():
        if value is not None:
            print(f"  - {key}: {value}")
    print("\n")

    # 运行 graph
    final_state = None
    try:
        for output in graph.stream(initial_state, config=config):
            node_name = list(output.keys())[0]
            print(f"\n{'=' * 80}")
            print(f"📍 当前节点: {node_name}")
            print(f"{'=' * 80}")

            final_state = output[node_name]
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断优化流程")
    except Exception as e:
        print(f"\n\n❌ 优化流程发生错误: {e}")
        import traceback

        traceback.print_exc()

    # 输出最终结果
    print("\n" + "=" * 80)
    print("🏁 优化流程结束")
    print("=" * 80)

    if final_state:
        if final_state.get("goal_achieved"):
            best = final_state.get("best_metrics")
            print("\n✅ 成功达成目标！")
            if best:
                print(f"  最终 Sharpe: {best['sharpe']:.3f}")
                print(f"  交易次数: {best['total_trades']}")
                print(f"  胜率: {best['win_rate']:.2%}")
                print(f"  盈亏比: {best['profit_loss_ratio']:.2f}")
                print(f"  预期值: {best['expectancy']:.4f}")
            print(f"  迭代次数: {final_state.get('iteration')}")
        else:
            print("\n⚠️ 未达成目标")
            best = final_state.get("best_metrics")
            if best:
                print(f"  当前最佳 Sharpe: {best['sharpe']:.3f}")
                print(f"  交易次数: {best['total_trades']}")
                print(f"  胜率: {best['win_rate']:.2%}")
            print(f"  迭代次数: {final_state.get('iteration', 0)}")

    return final_state


def main():
    """
    主函数：从命令行运行
    """
    # 可以从命令行参数或配置文件读取目标
    # 这里使用自定义目标
    custom_target: OptimizationTarget = {
        "target_sharpe": 2.5,
        "min_trades": 150,
        "max_trades": 500,
        "target_win_rate": 0.55,
        "target_profit_loss_ratio": 2.0,
    }

    # 运行优化
    final_state = run_optimization(target=custom_target)

    # 可以在这里保存结果到文件
    if final_state and final_state.get("best_strategy_code"):
        print("\n💾 最佳策略已保存在 strategy/rs_squeeze.py")


if __name__ == "__main__":
    main()
