"""
TUI-aware logging 配置模块

当 TUI 启用时，将所有 logger 输出重定向到 TUI，避免与 Rich Live Display 冲突。
当 TUI 禁用时，使用标准的 logging 配置。
"""

import logging
import sys

from backtest.tui_manager import get_tui, is_tui_enabled


class TUILogHandler(logging.Handler):
    """将 logging 输出重定向到 TUI 的自定义 Handler"""

    def __init__(self):
        super().__init__()
        self.tui = get_tui()

    def emit(self, record: logging.LogRecord):
        """发送日志记录到 TUI"""
        try:
            msg = self.format(record)
            level = record.levelname
            self.tui.add_log(msg, level)
        except Exception:
            self.handleError(record)


def setup_logging(level: int = logging.INFO, force_standard: bool = False):
    """
    配置全局 logging

    Args:
        level: 日志级别
        force_standard: 强制使用标准 logging（忽略 TUI）
    """
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)

    formatter = logging.Formatter("%(message)s")

    # 根据 TUI 状态选择 handler
    if not force_standard and is_tui_enabled():
        handler = TUILogHandler()
    else:
        handler = logging.StreamHandler(sys.stderr)

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
