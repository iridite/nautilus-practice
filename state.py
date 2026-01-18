from typing import List, Optional, TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    # 策略代码的当前版本
    strategy_code: str
    # 历史回测结果摘要列表 (用于回溯分析)
    backtest_history: List[dict]
    # 历史最高夏普比率
    best_sharpe: float
    # 尝试失败的计数器 (用于触发深度回溯)
    fail_count: int
    # 迷宫寻路日志 (Claude 自己的思考记录)
    thought_process: List[str]
    # 当前研究方向描述
    current_direction: str
