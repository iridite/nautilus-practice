"""
研究节点：评估目标、分析结果、生成优化策略
"""

import json
from typing import Optional

from langchain_anthropic import ChatAnthropic

from ..config import (
    FAIL_COUNT_THRESHOLD_FOR_REWRITE,
    MODEL_EVALUATOR,
    MODEL_LOGIC_REWRITE,
    MODEL_PARAMETER_TUNING,
    TEMPERATURE_EVALUATOR,
    TEMPERATURE_LOGIC_REWRITE,
    TEMPERATURE_PARAMETER_TUNING,
)
from ..prompts.researcher import (
    get_evaluator_system_prompt,
    get_logic_rewrite_system_prompt,
    get_parameter_tuning_system_prompt,
)
from ..state import AgentState, BacktestMetrics, OptimizationTarget
from ..utils.code_parser import extract_code
from ..utils.file_handler import read_strategy_file

# 初始化模型
model_parameter_tuning = ChatAnthropic(
    model=MODEL_PARAMETER_TUNING["name"],
    anthropic_api_key=MODEL_PARAMETER_TUNING["api_key"],
    anthropic_api_url=MODEL_PARAMETER_TUNING["base_url"],
    temperature=TEMPERATURE_PARAMETER_TUNING,
)

model_logic_rewrite = ChatAnthropic(
    model=MODEL_LOGIC_REWRITE["name"],
    anthropic_api_key=MODEL_LOGIC_REWRITE["api_key"],
    anthropic_api_url=MODEL_LOGIC_REWRITE["base_url"],
    temperature=TEMPERATURE_LOGIC_REWRITE,
)

model_evaluator = ChatAnthropic(
    model=MODEL_EVALUATOR["name"],
    anthropic_api_key=MODEL_EVALUATOR["api_key"],
    anthropic_api_url=MODEL_EVALUATOR["base_url"],
    temperature=TEMPERATURE_EVALUATOR,
)


def researcher_node(state: AgentState) -> dict:
    """
    研究节点主函数
    """
    print("\n" + "=" * 80)
    print("🔬 研究节点启动")
    print("=" * 80)

    iteration = state.get("iteration", 0) + 1

    # 步骤 1: 评估目标
    evaluation_result = evaluate_goals(state)

    if evaluation_result["goal_achieved"]:
        print("\n🎉 目标已达成！")
        return {
            "goal_achieved": True,
            "evaluation_report": evaluation_result["report"],
            "iteration": iteration,
        }

    # 步骤 2: 判断是否需要初始回测
    code_run_successful = state.get("code_run_successful", True)
    current_result = state.get("current_backtest_result")

    if not code_run_successful:
        print("⚠️ 上次代码运行失败，专注于 Debug 分析")
        backtest_data = None
    elif current_result is None:
        print("📋 首次运行，需要先进行回测获取基准数据")
        return {
            "needs_initial_backtest": True,
            "iteration": iteration,
            "evaluation_report": evaluation_result["report"],
        }
    else:
        backtest_data = current_result

    # 步骤 3: 失败判定
    should_increment_fail = should_count_as_failure(state)
    new_fail_count = state.get("fail_count", 0) + (1 if should_increment_fail else 0)

    if should_increment_fail:
        print(f"📉 本次优化未改善目标，失败计数 +1 (当前: {new_fail_count})")
    else:
        print(f"📈 本次优化在某些维度有改善，失败计数重置为 {new_fail_count}")

    # 步骤 4: 决定优化模式
    optimization_mode = decide_optimization_mode(state, new_fail_count)

    # 步骤 5: 生成优化策略
    new_strategy_code = generate_optimized_strategy(
        state=state,
        backtest_data=backtest_data,
        evaluation_report=evaluation_result["report"],
        optimization_mode=optimization_mode,
        fail_count=new_fail_count,
    )

    return {
        "strategy_code": new_strategy_code,
        "optimization_mode": optimization_mode,
        "last_optimization_mode": state.get("optimization_mode", "parameter_tuning"),
        "fail_count": new_fail_count,
        "iteration": iteration,
        "evaluation_report": evaluation_result["report"],
        "goal_achieved": False,
        "needs_initial_backtest": False,
    }


def evaluate_goals(state: AgentState) -> dict:
    """
    评估是否达成优化目标
    返回: {"goal_achieved": bool, "report": str}
    """
    target = state.get("optimization_target", {})
    current_result = state.get("current_backtest_result")

    # 如果没有目标或没有结果，返回未达成
    if not target or not current_result:
        return {"goal_achieved": False, "report": "无优化目标或无回测结果"}

    # 准备评估数据
    evaluation_data = {
        "target": target,
        "current": {
            "sharpe": current_result.get("sharpe", 0),
            "trades": current_result.get("total_trades", 0),
            "profit_pct": current_result.get("profit_pct", 0),
            "profit_loss_ratio": current_result.get("profit_loss_ratio", 0),
            "win_rate": current_result.get("win_rate", 0),
            "expectancy": current_result.get("expectancy", 0),
        },
    }

    system_msg = get_evaluator_system_prompt()

    user_msg = f"""
请评估以下结果是否达成目标：

{json.dumps(evaluation_data, indent=2, ensure_ascii=False)}
"""

    response = model_evaluator.invoke(
        [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]
    )

    result_text = str(response.content)

    # 解析结果
    lines = result_text.strip().split("\n")
    goal_achieved = lines[0].strip() == "ACHIEVED"
    report = "\n".join(lines[1:]).strip()

    print(f"\n{'=' * 80}")
    print("📊 目标评估报告:")
    print(report)
    print(f"{'=' * 80}\n")

    return {
        "goal_achieved": goal_achieved,
        "report": report,
    }


def should_count_as_failure(state: AgentState) -> bool:
    """
    多维度判定是否应该增加失败计数
    如果在任何一个目标维度上有改善，就不算失败
    """
    target = state.get("optimization_target", {})
    current_result = state.get("current_backtest_result")
    best_metrics = state.get("best_metrics")

    # 如果代码运行失败，肯定算失败
    if not state.get("code_run_successful", True):
        return True

    # 如果没有当前结果，算失败
    if not current_result:
        return True

    # 如果没有历史最佳，这是第一次成功运行，不算失败
    if not best_metrics:
        return False

    # 检查各个维度是否有改善
    improvements = []

    # 只检查用户设定的目标维度
    if target.get("target_sharpe") is not None:
        if current_result["sharpe"] > best_metrics["sharpe"]:
            improvements.append("sharpe")

    if target.get("target_trades") is not None or target.get("min_trades") is not None:
        # 计算与目标的距离
        target_trades = target.get("target_trades", target.get("min_trades", 0))
        current_distance = abs(current_result["total_trades"] - target_trades)
        best_distance = abs(best_metrics["total_trades"] - target_trades)
        if current_distance < best_distance:
            improvements.append("trades")

    if target.get("target_profit_pct") is not None:
        if current_result["profit_pct"] > best_metrics["profit_pct"]:
            improvements.append("profit_pct")

    if target.get("target_profit_loss_ratio") is not None:
        if current_result["profit_loss_ratio"] > best_metrics["profit_loss_ratio"]:
            improvements.append("profit_loss_ratio")

    if target.get("target_win_rate") is not None:
        if current_result["win_rate"] > best_metrics["win_rate"]:
            improvements.append("win_rate")

    if target.get("target_expectancy") is not None:
        if current_result["expectancy"] > best_metrics["expectancy"]:
            improvements.append("expectancy")

    # 如果有任何维度改善，就不算失败
    if improvements:
        print(f"✨ 改善的维度: {', '.join(improvements)}")
        return False
    else:
        print("❌ 所有维度均无改善")
        return True


def decide_optimization_mode(state: AgentState, fail_count: int) -> str:
    """
    决定优化模式：参数微调 or 逻辑重构
    """
    # 失败次数少，用微调
    if fail_count < FAIL_COUNT_THRESHOLD_FOR_REWRITE:
        return "parameter_tuning"

    # 失败次数多，用逻辑重构
    return "logic_rewrite"


def generate_optimized_strategy(
    state: AgentState,
    backtest_data: Optional[BacktestMetrics],
    evaluation_report: str,
    optimization_mode: str,
    fail_count: int,
) -> str:
    """
    生成优化后的策略代码
    """
    current_code = state.get("strategy_code", "")
    best_code = state.get("best_strategy_code", "")
    debug_record = state.get("debug_record")
    code_run_successful = state.get("code_run_successful", True)
    target = state.get("optimization_target", {})

    # 读取当前代码
    if not current_code:
        current_code = state.get("initial_strategy_code", "")

    if not current_code:
        current_code = read_strategy_file()

    # 选择模型
    if optimization_mode == "parameter_tuning":
        model = model_parameter_tuning
        system_msg = get_parameter_tuning_system_prompt()
        mode_desc = "参数微调"
        print(f"🔧 优化模式: {mode_desc}")
    else:
        model = model_logic_rewrite
        system_msg = get_logic_rewrite_system_prompt()
        mode_desc = "逻辑重构"
        print(f"🔄 优化模式: {mode_desc}")

    # 构建用户消息
    user_msg_parts = [
        "--- 优化目标 ---",
        json.dumps(target, indent=2, ensure_ascii=False),
        "",
        "--- 目标达成度评估 ---",
        evaluation_report,
        "",
    ]

    # 如果代码运行成功，包含回测数据
    if code_run_successful and backtest_data:
        user_msg_parts.extend(
            [
                "--- 当前回测结果 ---",
                json.dumps(
                    {
                        "sharpe": backtest_data["sharpe"],
                        "total_trades": backtest_data["total_trades"],
                        "profit_pct": backtest_data["profit_pct"],
                        "profit_loss_ratio": backtest_data["profit_loss_ratio"],
                        "win_rate": backtest_data["win_rate"],
                        "expectancy": backtest_data["expectancy"],
                        "max_drawdown": backtest_data["max_drawdown"],
                        "filtered_signals": backtest_data["filtered_signals"],
                        "total_signals": backtest_data["total_signals"],
                        "strategy_parameters": backtest_data["strategy_parameters"],
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                "",
            ]
        )

    # 如果代码运行失败，专注于 Debug 信息
    if not code_run_successful and debug_record:
        user_msg_parts.extend(
            [
                "--- ⚠️ 上次代码运行失败 ---",
                "**错误类型**: " + debug_record["error_type"],
                "**错误信息**: " + debug_record["error_message"],
                "",
                "--- Debug 修复总结 ---",
                debug_record["fix_summary"],
                "",
                "**请特别注意**: 生成的代码必须避免上述错误，确保语法正确、逻辑完整。",
                "",
            ]
        )

    user_msg_parts.extend(
        [
            "--- 当前策略代码 ---",
            "```python",
            current_code,
            "```",
            "",
        ]
    )

    # 如果是逻辑重构，提供历史最佳代码参考
    if optimization_mode == "logic_rewrite" and best_code:
        user_msg_parts.extend(
            [
                "--- 历史最佳策略（供参考）---",
                "```python",
                best_code,
                "```",
                "",
            ]
        )

    user_msg_parts.append("请生成优化后的完整策略代码。")

    user_msg = "\n".join(user_msg_parts)

    # 调用 LLM
    response = model.invoke(
        [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]
    )

    new_code = extract_code(str(response.content))

    print(f"\n✅ 新策略代码已生成 ({len(new_code)} 字符)\n")

    return new_code
