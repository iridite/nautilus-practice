"""
优化系统配置
"""

import os

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# ===== API 配置 =====
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_KEY", "")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

# ===== 模型定义 =====
# 可用的模型列表
AVAILABLE_MODELS = {
    "claude-sonnet-4.5": {
        "name": "claude-sonnet-4-5-20250929",
        "description": "Claude Sonnet 4.5 - 最强推理模型，适合复杂逻辑重构和评估",
        "api_key": ANTHROPIC_API_KEY,
        "base_url": ANTHROPIC_BASE_URL,
    },
    "claude-haiku-4.5": {
        "name": "claude-haiku-4-5-20251001",
        "description": "Claude Haiku 4.5 - 快速高效模型，适合参数微调",
        "api_key": ANTHROPIC_API_KEY,
        "base_url": ANTHROPIC_BASE_URL,
    },
    "claude-sonnet-4": {
        "name": "claude-sonnet-4-20250514",
        "description": "Claude Sonnet 4 - 平衡性能模型",
        "api_key": ANTHROPIC_API_KEY,
        "base_url": ANTHROPIC_BASE_URL,
    },
    "gemini-3-pro": {
        "name": "gemini-3-pro",
        "description": "Gemini 3 Pro - Google 最新模型",
        "api_key": ANTHROPIC_API_KEY,
        "base_url": ANTHROPIC_BASE_URL,
    },
    "gemini-3-pro-preview": {
        "name": "gemini-3-pro-preview",
        "description": "Gemini 3 Pro Preview - Google 预览版本",
        "api_key": ANTHROPIC_API_KEY,
        "base_url": ANTHROPIC_BASE_URL,
    },
}

# ===== 任务模型配置 =====
# 参数微调：使用快速模型，注重效率
MODEL_PARAMETER_TUNING = AVAILABLE_MODELS["claude-haiku-4.5"]
TEMPERATURE_PARAMETER_TUNING = 0.3

# 逻辑重构：使用最强模型，注重推理能力
MODEL_LOGIC_REWRITE = AVAILABLE_MODELS["claude-sonnet-4.5"]
TEMPERATURE_LOGIC_REWRITE = 0.7

# 评估器：使用强模型，注重准确性
MODEL_EVALUATOR = AVAILABLE_MODELS["claude-sonnet-4.5"]
TEMPERATURE_EVALUATOR = 0.2

# 调试器：使用强模型，注重问题定位
MODEL_DEBUGGER = AVAILABLE_MODELS["claude-sonnet-4.5"]
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
    "target_sharpe": 2.0,
    "min_trades": 150,
    "max_trades": 500,
    "target_win_rate": 0.55,
    "target_profit_loss_ratio": 2.0,
}
