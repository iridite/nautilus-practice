"""
Prompt 模板模块
"""

from .debugger import get_debugger_system_prompt
from .researcher import (
    get_evaluator_system_prompt,
    get_logic_rewrite_system_prompt,
    get_parameter_tuning_system_prompt,
)

__all__ = [
    "get_evaluator_system_prompt",
    "get_parameter_tuning_system_prompt",
    "get_logic_rewrite_system_prompt",
    "get_debugger_system_prompt",
]
