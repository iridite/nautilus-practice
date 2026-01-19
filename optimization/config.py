"""
优化系统配置
"""

import os

# ===== 模型配置 =====
MODEL_NAME = "deepseek-ai/DeepSeek-V3.2"
API_KEY = lambda: os.getenv("SF_API_KEY") or ""
BASE_URL = os.getenv("SF_BASE_URL")

# 不同任务的温度设置
TEMPERATURE_PARAMETER_TUNING = 0.3
TEMPERATURE_LOGIC_REWRITE = 0.7
TEMPERATURE_EVALUATOR = 0.2
TEMPERATURE_DEBUGGER = 0.1

# ===== 路径配置 =====
STRATEGY_FILE_PATH = "strategy/rs_squeeze.py"
BACKTEST_RESULT_PATTERN = "log/backtest/result/RSSqueezeStrategy_*.json"

# ===== 优化配置 =====
MAX_DEBUG_ATTEMPTS = 3  # 最大 Debug 尝试次数
MAX_ITERATIONS = 100  # 最大迭代次数
BACKTEST_TIMEOUT = 300  # 回测超时时间（秒）

# ===== 失败判定配置 =====
FAIL_COUNT_THRESHOLD_FOR_REWRITE = 3  # 失败多少次后切换到逻辑重构

# ===== 默认优化目标 =====
DEFAULT_OPTIMIZATION_TARGET = {
    "target_sharpe": 2.5,
    "min_trades": 150,
    "max_trades": 500,
    "target_win_rate": 0.55,
    "target_profit_loss_ratio": 2.0,
}
