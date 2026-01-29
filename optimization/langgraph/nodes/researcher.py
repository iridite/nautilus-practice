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
from ..state import AgentState, BacktestMetrics
from ..utils.code_parser import extract_code, validate_strategy_code
from ..utils.file_handler import read_strategy_file

# 初始化模型
model_parameter_tuning = ChatAnthropic(  # type: ignore
    model=MODEL_PARAMETER_TUNING["name"],
    anthropic_api_key=MODEL_PARAMETER_TUNING["api_key"],
    anthropic_api_url=MODEL_PARAMETER_TUNING["base_url"],
    temperature=TEMPERATURE_PARAMETER_TUNING,
)

model_logic_rewrite = ChatAnthropic(  # type: ignore
    model=MODEL_LOGIC_REWRITE["name"],
    anthropic_api_key=MODEL_LOGIC_REWRITE["api_key"],
    anthropic_api_url=MODEL_LOGIC_REWRITE["base_url"],
    temperature=TEMPERATURE_LOGIC_REWRITE,
)

model_evaluator = ChatAnthropic(  # type: ignore
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

        # 读取现有策略代码
        current_code = state.get("strategy_code", "")
        if not current_code:
            current_code = state.get("initial_strategy_code", "")
        if not current_code:
            current_code = read_strategy_file()
            print(f"📋 从文件读取现有策略代码 ({len(current_code)} 字符)")

        return {
            "needs_initial_backtest": True,
            "iteration": iteration,
            "evaluation_report": evaluation_result["report"],
            "strategy_code": current_code,
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
        target_trades = target.get("target_trades") or target.get("min_trades") or 0
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
        # 获取完整的回测报告
        full_report = state.get("current_backtest_report")

        # 首先提供简化版指标（快速查看）
        summary_data = {
            "核心绩效": {
                "sharpe": backtest_data["sharpe"],
                "total_trades": backtest_data["total_trades"],
                "profit_pct": backtest_data["profit_pct"],
                "win_rate": backtest_data["win_rate"],
                "profit_loss_ratio": backtest_data["profit_loss_ratio"],
                "expectancy": backtest_data["expectancy"],
                "max_drawdown": backtest_data["max_drawdown"],
                "profit_factor": backtest_data.get("profit_factor", 0),
            },
            "信号统计": {
                "total_signals": backtest_data["total_signals"],
                "filtered_signals": backtest_data["filtered_signals"],
                "signal_pass_rate": (
                    backtest_data["filtered_signals"] / backtest_data["total_signals"]
                    if backtest_data["total_signals"] > 0
                    else 0.0
                ),
            },
            "策略参数数量": len(backtest_data.get("strategy_parameters", {})),
        }

        user_msg_parts.extend(
            [
                "--- 回测结果摘要（快速查看）---",
                json.dumps(summary_data, indent=2, ensure_ascii=False),
                "",
            ]
        )

        # 然后提供关键信息提取（重点分析）
        if full_report:
            # 提取关键洞察
            insights = {}

            # 1. 信号过滤分析
            filter_stats = full_report.get("filter_stats", {})
            if filter_stats:
                filter_rates = filter_stats.get("rates", {})
                insights["信号过滤分析"] = {
                    "通过率": filter_rates.get("pass_rate", 0),
                    "过滤率": filter_rates.get("filter_rate", 0),
                    "主要过滤原因": {
                        "趋势不符": filter_rates.get("fail_trend_rate", 0),
                        "挤压条件": filter_rates.get("fail_squeeze_rate", 0),
                        "相对强度": filter_rates.get("fail_rs_rate", 0),
                        "突破条件": filter_rates.get("fail_breakout_rate", 0),
                        "成交量": filter_rates.get("fail_volume_rate", 0),
                        "BTC趋势": filter_rates.get("fail_btc_bear_rate", 0),
                    },
                    "标的数量": filter_stats.get("instrument_count", 0),
                }

            # 2. 赢家 vs 输家对比
            trade_metrics = full_report.get("trade_metrics", {})
            detailed = trade_metrics.get("detailed_analysis", {})
            if detailed:
                winners = detailed.get("winners", {})
                losers = detailed.get("losers", {})
                insights["赢家输家对比"] = {
                    "赢家": {
                        "数量": winners.get("count", 0),
                        "平均盈利%": winners.get("avg_pnl_pct", 0),
                        "平均RS评分": winners.get("avg_rs_score", 0),
                        "平均BB宽度%": winners.get("avg_bb_width_pct", 0),
                        "平均成交量倍数": winners.get("avg_volume_mult", 0),
                    },
                    "输家": {
                        "数量": losers.get("count", 0),
                        "平均亏损%": losers.get("avg_pnl_pct", 0),
                        "平均RS评分": losers.get("avg_rs_score", 0),
                        "平均BB宽度%": losers.get("avg_bb_width_pct", 0),
                        "平均成交量倍数": losers.get("avg_volume_mult", 0),
                    },
                    "关键差异": {
                        "RS评分差": winners.get("avg_rs_score", 0)
                        - losers.get("avg_rs_score", 0),
                        "BB宽度差": winners.get("avg_bb_width_pct", 0)
                        - losers.get("avg_bb_width_pct", 0),
                        "成交量倍数差": winners.get("avg_volume_mult", 0)
                        - losers.get("avg_volume_mult", 0),
                    },
                }

            # 3. 性能摘要
            performance = full_report.get("performance", {})
            if performance:
                insights["性能摘要"] = {
                    "总交易数": performance.get("total_trades", 0),
                    "总订单数": performance.get("total_orders", 0),
                    "夏普率": performance.get("sharpe_ratio", 0),
                    "胜率": performance.get("win_rate", 0),
                    "盈亏比": performance.get("profit_loss_ratio", 0),
                    "总收益%": performance.get("total_pnl_pct", 0),
                    "信号通过率": performance.get("signal_pass_rate", 0),
                }

            # 4. 策略配置关键参数
            strategy_config = full_report.get("strategy_config", {})
            if strategy_config:
                key_params = {
                    "技术指标": {
                        "BB周期": strategy_config.get("bb_period", 20),
                        "BB标准差": strategy_config.get("bb_std", 2.0),
                        "KC周期": strategy_config.get("kc_period_ema", 20),
                        "KC倍数": strategy_config.get("kc_mult", 1.4),
                        "ATR周期": strategy_config.get("atr_period", 20),
                    },
                    "相对强度": {
                        "RS回溯6h": strategy_config.get("rs_lookback_6h", 6),
                        "RS回溯12h": strategy_config.get("rs_lookback_12h", 12),
                        "RS回溯24h": strategy_config.get("rs_lookback_24h", 24),
                        "RS加速差": strategy_config.get("rs_acceleration_gap", 0.03),
                        "RS差6h": strategy_config.get("rs_gap_6h", 0.03),
                        "RS差12h": strategy_config.get("rs_gap_12h", 0.05),
                        "RS差24h": strategy_config.get("rs_gap_24h", 0.07),
                    },
                    "过滤条件": {
                        "BB宽度周期": strategy_config.get("bb_width_period", 100),
                        "BB宽度百分位": strategy_config.get("bb_width_percentile", 0.5),
                        "挤压成熟K线": strategy_config.get("squeeze_maturity_bars", 2),
                        "成交量倍数": strategy_config.get("volume_filter_mult", 1.6),
                    },
                    "风险管理": {
                        "每笔风险": strategy_config.get("risk_per_trade", 0.05),
                        "最大杠杆": strategy_config.get("max_leverage", 3.0),
                        "止损倍数": strategy_config.get("stop_loss_mult", 1.5),
                        "保本倍数": strategy_config.get("breakeven_mult", 4.0),
                        "最大持仓时间": strategy_config.get("max_holding_hours", 72),
                        "最大并发仓位": strategy_config.get(
                            "max_concurrent_positions", 5
                        ),
                        "冷却期小时": strategy_config.get("cooldown_period_hours", 24),
                    },
                }
                insights["当前策略关键参数"] = key_params

            user_msg_parts.extend(
                [
                    "--- 关键信息提取（重点分析）---",
                    json.dumps(insights, indent=2, ensure_ascii=False),
                    "",
                    "**优化建议方向**:",
                    "1. 如果信号过滤率过高，考虑放宽过滤条件（如降低RS阈值、BB宽度要求等）",
                    "2. 如果胜率低但盈亏比高，考虑优化入场时机，提高成功率",
                    "3. 如果盈亏比低，考虑优化止损止盈策略，扩大盈利空间",
                    "4. 根据赢家输家对比，调整RS评分、BB宽度、成交量等过滤条件",
                    "5. 如果交易次数不足，降低过滤严格度；如果过多，提高过滤严格度",
                    "",
                ]
            )

            # 最后提供完整的 JSON 报告（供深度分析）
            user_msg_parts.extend(
                [
                    "--- 完整回测报告（详细数据，供深度分析）---",
                    "以下是完整的回测 JSON 报告，包含所有原始数据：",
                    "- strategy_config: 完整策略配置（62个参数）",
                    "- trade_metrics.trades: 所有交易明细（包含入场指标）",
                    "- filter_stats.by_instrument: 每个标的的过滤统计",
                    "- returns: 收益率相关指标",
                    "",
                    "```json",
                    json.dumps(full_report, indent=2, ensure_ascii=False),
                    "```",
                    "",
                    "**注意**: 请根据上述关键信息提取和优化建议，结合完整报告进行精准优化。",
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

    # 添加明确的长度和完整性要求
    user_msg_parts.extend(
        [
            "",
            "--- 重要提示 ---",
            f"原始策略代码长度: {len(current_code)} 字符",
            f"原始策略代码行数: {len(current_code.split(chr(10)))} 行",
            "",
            "请生成优化后的**完整策略代码**，要求：",
            "1. 代码长度应该与原始代码相近（至少8000字符）",
            "2. 必须包含所有方法的完整实现，不能省略或使用占位符",
            "3. 每个方法都要有实际的逻辑代码，不能只有 pass 或 ...",
            "4. 必须使用 ```python 代码块包裹",
            "5. 开头注释要简洁（不超过10行）",
            "",
        ]
    )

    user_msg = "\n".join(user_msg_parts)

    # 调用 LLM
    max_retries = 3
    for attempt in range(max_retries):
        print(f"\n🤖 调用 AI 生成策略代码 (尝试 {attempt + 1}/{max_retries})...")

        response = model.invoke(
            [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ]
        )

        response_content = str(response.content)

        # 预处理响应内容：处理可能的转义字符
        # AI 有时会返回字面的 \n 而不是真正的换行符
        if "\\n" in response_content:
            actual_newlines = response_content.count("\n")
            escaped_newlines = response_content.count("\\n")

            # 如果转义换行符远多于实际换行符，说明需要修复
            if escaped_newlines > actual_newlines * 2:
                print("⚠️ 检测到 AI 返回内容包含转义字符，正在修复...")
                response_content = response_content.replace("\\n", "\n")
                response_content = response_content.replace("\\t", "    ")
                print("✅ 已修复转义字符")

        # 尝试提取代码
        try:
            new_code = extract_code(response_content)

            # 额外验证代码完整性
            is_valid, error_msg = validate_strategy_code(new_code)
            if not is_valid:
                print(f"⚠️ 代码验证失败: {error_msg}")
                print(f"   代码长度: {len(new_code)} 字符")
                print(f"   代码行数: {len(new_code.split(chr(10)))} 行")

                if attempt < max_retries - 1:
                    print("🔄 重试中...")
                    # 修改用户消息，强调完整性要求
                    user_msg_parts.append(
                        f"\n⚠️ 上次生成失败，原因: {error_msg}\n"
                        f"生成的代码长度: {len(new_code)} 字符，行数: {len(new_code.split(chr(10)))} 行\n"
                        "\n**请务必返回完整的策略代码**，包括：\n"
                        "1. 所有必要的 import 语句（至少10个import）\n"
                        "2. 完整的 Config 类定义（包含所有60+个参数）\n"
                        "3. 完整的 Strategy 类定义（包含所有10+个方法的完整实现）\n"
                        "4. 每个方法必须有完整的逻辑实现，不能只有 pass 或 ...\n"
                        "5. __init__ 方法需要初始化所有指标和状态变量\n"
                        "6. on_bar 方法需要包含完整的交易逻辑\n"
                        "7. 代码总长度应该在8000-15000字符之间\n"
                        "8. 代码开头的注释要简洁（不超过10行）\n"
                        "9. 使用 ```python 代码块包裹完整代码\n"
                        "\n**不要做的事情**：\n"
                        "- 不要省略任何方法的实现\n"
                        "- 不要使用 '# ... 其他代码 ...' 这样的占位符\n"
                        "- 不要只返回改动的部分，必须返回完整文件\n"
                        "- 不要简化或压缩代码，保持原有的完整性\n"
                    )
                    user_msg = "\n".join(user_msg_parts)
                    continue
                else:
                    raise ValueError(f"多次尝试后仍无法生成有效代码: {error_msg}")

            # 验证通过 - 显示详细信息
            code_lines = new_code.split("\n")
            method_count = new_code.count("def ")
            class_count = new_code.count("class ")
            import_count = new_code.count("import ")

            print(f"\n✅ 新策略代码已生成并验证通过")
            print(f"   - 代码长度: {len(new_code)} 字符")
            print(f"   - 代码行数: {len(code_lines)} 行")
            print(f"   - 类定义数: {class_count} 个")
            print(f"   - 方法数量: {method_count} 个")
            print(f"   - Import语句: {import_count} 个")
            print("   - 包含 Config 类: ✓")
            print("   - 包含 Strategy 类: ✓")
            print("   - 包含关键方法: ✓")
            print("   - 代码完整性检查: ✓\n")

            return new_code

        except ValueError as e:
            print(f"❌ 代码提取失败: {str(e)}")

            if attempt < max_retries - 1:
                print("🔄 重试中...")
                # 修改用户消息，强调完整性要求
                user_msg_parts.append(
                    f"\n⚠️ 上次生成失败，原因: {str(e)}\n"
                    "\n**请务必返回完整的策略代码**，包括：\n"
                    "1. 所有必要的 import 语句\n"
                    "2. 完整的 Config 类定义\n"
                    "3. 完整的 Strategy 类定义\n"
                    "4. 每个方法必须有完整的逻辑实现，不能只有 pass 或 ...\n"
                    "5. __init__, on_start, on_bar 等核心方法必须包含完整实现\n"
                    "6. 使用 ```python 代码块包裹完整代码\n"
                    "\n**参考原始代码的完整性**：\n"
                    f"原始代码长度: {len(current_code)} 字符\n"
                    f"原始代码行数: {len(current_code.split(chr(10)))} 行\n"
                    "\n**不要做的事情**：\n"
                    "- 不要省略任何方法的实现\n"
                    "- 不要使用 '# ... 其他代码 ...' 这样的占位符\n"
                    "- 不要只返回改动的部分，必须返回完整文件\n"
                    "- 不要只返回注释说明或改动总结\n"
                )
                user_msg = "\n".join(user_msg_parts)
            else:
                # 最后一次尝试也失败了
                print(f"\n❌ 经过 {max_retries} 次尝试，AI 仍未能生成有效的策略代码")
                print(f"错误信息: {str(e)}")
                print(f"原始代码长度: {len(current_code)} 字符")
                print("\n⚠️ 返回原始策略代码，避免覆盖")

                # 返回当前代码，避免覆盖为无效内容
                return current_code

    # 理论上不会到达这里，但为了安全起见
    return current_code
