"""
State 定义
"""

from operator import add
from typing import Annotated, Optional, Sequence, TypedDict


class OptimizationTarget(TypedDict, total=False):
    """优化目标配置（所有字段可选，由用户在 LangSmith 界面输入）"""

    target_sharpe: Optional[float]  # 目标夏普率，如 2.5
    target_trades: Optional[int]  # 目标下单数量，如 150
    min_trades: Optional[int]  # 最小下单数量（避免过少）
    max_trades: Optional[int]  # 最大下单数量（避免过多）
    target_profit_pct: Optional[float]  # 目标盈亏百分比，如 0.15 (15%)
    target_profit_loss_ratio: Optional[float]  # 目标盈亏比，如 2.0
    target_win_rate: Optional[float]  # 目标胜率，如 0.55 (55%)
    target_expectancy: Optional[float]  # 目标预期值


class BacktestMetrics(TypedDict):
    """标准化的回测指标"""

    sharpe: float
    total_trades: int
    profit_pct: float  # 总盈亏百分比
    profit_loss_ratio: float  # 盈亏比（平均盈利/平均亏损）
    win_rate: float  # 胜率
    expectancy: float  # 预期值 = (win_rate * avg_win) - (loss_rate * avg_loss)

    # 详细指标
    avg_profit: float
    avg_loss: float
    max_profit: float
    max_loss: float
    max_drawdown: float
    profit_factor: float

    # 信号统计
    total_signals: int  # 总信号数
    filtered_signals: int  # 被过滤的信号数
    filtered_by_symbol: dict  # 各币种过滤情况 {symbol: filtered_count}

    # 参数信息
    strategy_parameters: dict  # 策略使用的参数

    timestamp: str


class DebugRecord(TypedDict):
    """调试记录"""

    error_type: str  # 错误类型
    error_message: str  # 错误信息
    error_traceback: str  # 完整堆栈
    fix_attempts: int  # 修复尝试次数
    fix_successful: bool  # 是否修复成功
    fix_summary: str  # 修复总结（Markdown 格式）
    fixed_code: Optional[str]  # 修复后的代码（如果成功）
    timestamp: str


class AgentState(TypedDict):
    # ===== 用户输入（LangSmith 界面） =====
    optimization_target: OptimizationTarget  # 优化目标
    initial_strategy_code: Optional[str]  # 初始策略代码（第一次运行时输入）

    # ===== 当前策略状态 =====
    strategy_code: str  # 当前策略代码
    previous_strategy_code: str  # 上一个成功运行的策略代码（用于回滚）
    code_run_successful: bool  # 代码是否成功运行

    # ===== 回测结果 =====
    current_backtest_result: Optional[
        BacktestMetrics
    ]  # 当前回测结果（简化版，快速查看）
    current_backtest_report: Optional[dict]  # 完整的 JSON 回测报告（包含所有原始数据）
    backtest_history: Annotated[
        Sequence[BacktestMetrics], add
    ]  # 历史回测结果（简化版）
    backtest_report_history: Annotated[Sequence[dict], add]  # 历史完整报告

    # ===== 最佳记录 =====
    best_metrics: Optional[BacktestMetrics]  # 历史最佳指标
    best_strategy_code: str  # 历史最佳策略代码

    # ===== 优化状态 =====
    optimization_mode: str  # "parameter_tuning" 或 "logic_rewrite"
    last_optimization_mode: str  # 上一次使用的优化方式
    fail_count: int  # 失败次数
    iteration: int  # 当前迭代次数

    # ===== 调试信息 =====
    debug_record: Optional[DebugRecord]  # 最新的调试记录
    debug_history: Annotated[Sequence[DebugRecord], add]  # 历史调试记录

    # ===== 分析报告 =====
    evaluation_report: str  # 目标达成度评估报告
    optimization_analysis: str  # 优化分析报告

    # ===== 控制标志 =====
    goal_achieved: bool  # 是否达成目标
    needs_initial_backtest: bool  # 是否需要初始回测
