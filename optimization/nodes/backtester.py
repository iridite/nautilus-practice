"""
回测节点：执行回测、捕获错误、自动修复
"""

import subprocess
import time
import traceback
from datetime import datetime
from typing import Optional, Tuple

from langchain_anthropic import ChatAnthropic

from ..config import (
    BACKTEST_TIMEOUT,
    MAX_DEBUG_ATTEMPTS,
    MODEL_DEBUGGER,
    STRATEGY_FILE_PATH,
    TEMPERATURE_DEBUGGER,
)
from ..prompts.debugger import get_debugger_system_prompt
from ..state import AgentState, BacktestMetrics, DebugRecord
from ..utils.code_parser import extract_code
from ..utils.file_handler import get_latest_json_report, write_strategy_file
from ..utils.metrics import extract_metrics_from_report

# 初始化 Debug 模型
model_debugger = ChatAnthropic(
    model=MODEL_DEBUGGER["name"],
    anthropic_api_key=MODEL_DEBUGGER["api_key"],
    anthropic_api_url=MODEL_DEBUGGER["base_url"],
    temperature=TEMPERATURE_DEBUGGER,
)


def backtester_node(state: AgentState) -> dict:
    """
    回测节点主函数：
    1. 写入策略代码
    2. 执行回测（带错误捕获）
    3. 自动修复错误（如果失败）
    4. 返回结果或回滚
    """
    print("\n" + "=" * 80)
    print("🧪 回测节点启动")
    print("=" * 80)

    strategy_code = state.get("strategy_code", "")
    previous_code = state.get("previous_strategy_code", "")

    # 保存当前代码为"上一个版本"（用于可能的回滚）
    if not previous_code:
        previous_code = strategy_code

    # ===== 步骤 1: 写入策略文件 =====
    try:
        write_strategy_file(strategy_code)
        print(f"✅ 策略代码已写入: {STRATEGY_FILE_PATH}")
    except Exception as e:
        print(f"❌ 写入策略文件失败: {e}")
        return create_error_state(state, "FILE_WRITE_ERROR", str(e), "")

    # ===== 步骤 2: 执行回测（带 Debug 循环）=====
    debug_attempts = 0
    backtest_successful = False
    current_code = strategy_code
    debug_records = []

    while debug_attempts < MAX_DEBUG_ATTEMPTS and not backtest_successful:
        print(f"\n🚀 执行回测 (尝试 {debug_attempts + 1}/{MAX_DEBUG_ATTEMPTS})...")

        run_time = time.time()

        try:
            result = subprocess.run(
                ["uv", "run", "main.py", "backtest", "--type", "high"],
                capture_output=True,
                text=True,
                check=True,
                timeout=BACKTEST_TIMEOUT,
            )

            print("✅ 回测执行成功")
            backtest_successful = True

        except subprocess.TimeoutExpired:
            error_msg = f"回测执行超时（超过 {BACKTEST_TIMEOUT} 秒）"
            print(f"⏱️ {error_msg}")

            if debug_attempts < MAX_DEBUG_ATTEMPTS - 1:
                current_code, debug_record = attempt_fix_code(
                    code=current_code,
                    error_type="TIMEOUT",
                    error_message=error_msg,
                    error_traceback="",
                    state=state,
                )
                debug_records.append(debug_record)

                # 写入修复后的代码
                write_strategy_file(current_code)
                debug_attempts += 1
            else:
                break

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr or str(e)
            print(f"❌ 回测执行失败:\n{error_msg[:500]}...")

            if debug_attempts < MAX_DEBUG_ATTEMPTS - 1:
                current_code, debug_record = attempt_fix_code(
                    code=current_code,
                    error_type="RUNTIME_ERROR",
                    error_message=error_msg,
                    error_traceback=error_msg,
                    state=state,
                )
                debug_records.append(debug_record)

                # 写入修复后的代码
                write_strategy_file(current_code)
                debug_attempts += 1
            else:
                break

        except Exception as e:
            error_msg = str(e)
            error_trace = traceback.format_exc()
            print(f"❌ 未知错误:\n{error_trace[:500]}...")

            if debug_attempts < MAX_DEBUG_ATTEMPTS - 1:
                current_code, debug_record = attempt_fix_code(
                    code=current_code,
                    error_type="UNKNOWN_ERROR",
                    error_message=error_msg,
                    error_traceback=error_trace,
                    state=state,
                )
                debug_records.append(debug_record)

                # 写入修复后的代码
                write_strategy_file(current_code)
                debug_attempts += 1
            else:
                break

    # ===== 步骤 3: 处理结果 =====
    if not backtest_successful:
        print(f"\n❌ 回测失败，已尝试 {debug_attempts} 次修复")
        print("🔄 回滚到上一个成功版本")

        # 回滚代码
        if previous_code:
            write_strategy_file(previous_code)
            print("✅ 已回滚到上一个版本")

        # 生成失败的 debug 总结
        final_debug_record = debug_records[-1] if debug_records else None

        if not final_debug_record:
            # 如果没有 debug 记录，创建一个
            final_debug_record = DebugRecord(
                error_type="BACKTEST_FAILED",
                error_message="回测失败，所有修复尝试均未成功",
                error_traceback="",
                fix_attempts=debug_attempts,
                fix_successful=False,
                fix_summary="# Debug 失败\n\n回测执行失败，已尝试 {} 次自动修复，但均未成功。".format(
                    debug_attempts
                ),
                fixed_code=None,
                timestamp=datetime.now().isoformat(),
            )

        return {
            "code_run_successful": False,
            "debug_record": final_debug_record,
            "strategy_code": previous_code,  # 恢复到上一个版本
            "current_backtest_result": None,
        }

    # ===== 步骤 4: 读取回测结果 =====
    try:
        report = get_latest_json_report(run_time)
        metrics = extract_metrics_from_report(report)

        print(f"\n📊 回测结果:")
        print(f"  夏普率: {metrics['sharpe']:.3f}")
        print(f"  交易次数: {metrics['total_trades']}")
        print(f"  盈亏百分比: {metrics['profit_pct']:.2%}")
        print(f"  盈亏比: {metrics['profit_loss_ratio']:.2f}")
        print(f"  胜率: {metrics['win_rate']:.2%}")
        print(f"  预期值: {metrics['expectancy']:.4f}")
        print(f"  最大回撤: {metrics['max_drawdown']:.2%}\n")

    except Exception as e:
        print(f"❌ 读取回测结果失败: {e}")
        return create_error_state(
            state, "RESULT_READ_ERROR", str(e), traceback.format_exc()
        )

    # ===== 步骤 5: 更新最佳记录 =====
    best_metrics = state.get("best_metrics")
    update = {
        "code_run_successful": True,
        "current_backtest_result": metrics,
        "previous_strategy_code": current_code,  # 保存成功的代码
        "debug_record": None,  # 清空 debug 记录
    }

    # 如果有 debug 但最终成功了，记录成功的 debug
    if debug_records and backtest_successful:
        successful_debug = debug_records[-1]
        successful_debug["fix_successful"] = True
        update["debug_record"] = successful_debug
        print(f"✨ 代码经过 {len(debug_records)} 次修复后成功运行")

    # 更新历史最佳
    if not best_metrics or metrics["sharpe"] > best_metrics["sharpe"]:
        print(
            f"🎉 新记录！Sharpe 从 {best_metrics['sharpe'] if best_metrics else 0:.3f} "
            f"提升到 {metrics['sharpe']:.3f}"
        )
        update["best_metrics"] = metrics
        update["best_strategy_code"] = current_code

    return update


def attempt_fix_code(
    code: str,
    error_type: str,
    error_message: str,
    error_traceback: str,
    state: AgentState,
) -> Tuple[str, DebugRecord]:
    """
    尝试自动修复代码错误
    返回: (修复后的代码, Debug记录)
    """
    print(f"\n🔧 尝试自动修复错误...")

    system_msg = get_debugger_system_prompt()

    user_msg = f"""
    --- 错误类型 ---
    {error_type}

    --- 错误信息 ---
    {error_message[:1000]}

    --- 错误堆栈 ---
    {error_traceback[:2000]}

    --- 当前代码 ---
    ```python
    {code}
    请修复上述错误并输出完整的代码。
    """

    try:
        response = model_debugger.invoke(
            [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ]
        )

        result_text = str(response.content)

        # 提取修复总结和代码
        lines = result_text.strip().split("\n")
        fix_summary_line = lines[0].strip() if lines else "自动修复"
        fixed_code = extract_code(result_text)

        print(f"✅ 修复完成: {fix_summary_line}")

        # 生成完整的修复总结
        fix_summary = generate_debug_summary(
            error_type, error_message, error_traceback, fix_summary_line
        )

        # 创建 debug 记录
        debug_record: DebugRecord = {
            "error_type": error_type,
            "error_message": error_message[:500],  # 截断过长的消息
            "error_traceback": error_traceback[:1000],  # 截断过长的堆栈
            "fix_attempts": state.get("debug_record", {}).get("fix_attempts", 0) + 1,
            "fix_successful": False,  # 暂时标记为未成功，等回测验证
            "fix_summary": fix_summary,
            "fixed_code": fixed_code,
            "timestamp": datetime.now().isoformat(),
        }

        return fixed_code, debug_record

    except Exception as e:
        print(f"❌ 自动修复失败: {e}")

        # 返回原代码和失败记录
        debug_record: DebugRecord = {
            "error_type": error_type,
            "error_message": error_message[:500],
            "error_traceback": error_traceback[:1000],
            "fix_attempts": state.get("debug_record", {}).get("fix_attempts", 0) + 1,
            "fix_successful": False,
            "fix_summary": f"# 自动修复失败\n\n修复过程中发生错误: {str(e)}",
            "fixed_code": None,
            "timestamp": datetime.now().isoformat(),
        }

        return code, debug_record


def generate_debug_summary(
    error_type: str,
    error_message: str,
    error_traceback: str,
    fix_summary: str,
) -> str:
    """
    生成 Markdown 格式的 Debug 总结报告
    """
    summary = f"""
    # 错误信息
    - 错误类型：{error_type}
    - 错误描述：{error_message[:200]}
    # 错误堆栈
    {error_traceback[:500]}
    # 修复方案
    {fix_summary}
    # 建议
    在后续优化中，请注意避免类似错误，确保代码的语法正确性和逻辑完整性。
    """

    return summary


def create_error_state(
    state: AgentState,
    error_type: str,
    error_message: str,
    error_traceback: str,
) -> dict:
    """创建错误状态"""
    debug_record: DebugRecord = {
        "error_type": error_type,
        "error_message": error_message[:500],
        "error_traceback": error_traceback[:1000],
        "fix_attempts": 0,
        "fix_successful": False,
        "fix_summary": generate_debug_summary(
            error_type, error_message, error_traceback, "未尝试修复"
        ),
        "fixed_code": None,
        "timestamp": datetime.now().isoformat(),
    }
    return {
        "code_run_successful": False,
        "debug_record": debug_record,
        "current_backtest_result": None,
    }
