"""
全局 TUI 管理器 - 整合回测所有阶段的终端输出

提供统一的进度显示和日志管理，避免终端输出混乱。
"""

import os
import sys
from collections import deque
from contextlib import contextmanager
from typing import Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskID, TaskProgressColumn, TextColumn
from rich.table import Table
from rich.text import Text


class BacktestTUIManager:
    """回测 TUI 管理器 - 单例模式"""

    _instance: Optional["BacktestTUIManager"] = None
    _enabled: bool = False

    def __init__(self):
        self.console = Console()
        self.live: Optional[Live] = None
        self.progress: Optional[Progress] = None
        self.current_task: Optional[TaskID] = None
        self.current_phase: str = "Initializing"
        self.stats: dict = {}
        self.logs: deque = deque(maxlen=5)  # 保留最近 5 条日志
        self._is_active = False

    @classmethod
    def get_instance(cls) -> "BacktestTUIManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def is_enabled(cls) -> bool:
        """检查 TUI 是否启用"""
        if not cls._enabled:
            # 检查环境变量和 TTY
            use_tui = os.getenv("NAUTILUS_USE_TUI", "true").lower() != "false"
            cls._enabled = use_tui and sys.stdout.isatty()
        return cls._enabled

    def start(self):
        """启动 TUI"""
        if not self.is_enabled() or self._is_active:
            return

        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console,
        )

        self.live = Live(
            self._build_layout(),
            console=self.console,
            refresh_per_second=4,
            transient=False,
        )
        self.live.start()
        self._is_active = True

    def stop(self):
        """停止 TUI"""
        if self.live and self._is_active:
            self.live.stop()
            self._is_active = False

    def start_phase(self, phase_name: str, total: Optional[int] = None):
        """开始新阶段"""
        if not self._is_active:
            return

        self.current_phase = phase_name

        if self.progress:
            # 移除旧任务
            if self.current_task is not None:
                self.progress.remove_task(self.current_task)

            # 创建新任务
            if total is not None:
                self.current_task = self.progress.add_task(f"{phase_name}...", total=total)
            else:
                self.current_task = self.progress.add_task(f"{phase_name}...", total=None)

        self._update_display()

    def update_progress(
        self,
        advance: int = 1,
        description: Optional[str] = None,
        completed: Optional[int] = None,
    ):
        """更新进度"""
        if not self._is_active or self.current_task is None or self.progress is None:
            return

        if completed is not None:
            self.progress.update(self.current_task, completed=completed)
        else:
            self.progress.advance(self.current_task, advance)

        if description:
            self.progress.update(self.current_task, description=description)

        self._update_display()

    def add_log(self, message: str, level: str = "INFO"):
        """添加日志消息"""
        if not self._is_active:
            return

        # 根据级别设置颜色
        color_map = {
            "DEBUG": "dim",
            "INFO": "cyan",
            "WARNING": "yellow",
            "ERROR": "red",
        }
        color = color_map.get(level, "white")

        self.logs.append((level, message, color))
        self._update_display()

    def update_stat(self, key: str, value):
        """更新统计信息"""
        if not self._is_active:
            return

        self.stats[key] = value
        self._update_display()

    def increment_stat(self, key: str, delta: int = 1):
        """增加统计计数"""
        if not self._is_active:
            return

        self.stats[key] = self.stats.get(key, 0) + delta
        self._update_display()

    def _build_layout(self) -> Layout:
        """构建 TUI 布局"""
        layout = Layout()

        # 三层布局：阶段信息 + 进度条 + 统计/日志
        layout.split_column(
            Layout(name="phase", size=3),
            Layout(name="progress", size=3),
            Layout(name="info", size=10),
        )

        # 底部分为统计和日志两列
        layout["info"].split_row(
            Layout(name="stats"),
            Layout(name="logs"),
        )

        # 填充内容
        layout["phase"].update(self._make_phase_panel())
        layout["progress"].update(self.progress if self.progress else "")
        layout["stats"].update(self._make_stats_panel())
        layout["logs"].update(self._make_logs_panel())

        return layout

    def _make_phase_panel(self) -> Panel:
        """创建阶段信息面板"""
        text = Text(f"🚀 {self.current_phase}", style="bold green")
        return Panel(text, border_style="green")

    def _make_stats_panel(self) -> Panel:
        """创建统计信息面板"""
        if not self.stats:
            return Panel("No statistics yet", title="Statistics", border_style="blue")

        table = Table.grid(padding=(0, 2))
        table.add_column(style="cyan", justify="right")
        table.add_column(style="magenta")

        for key, value in self.stats.items():
            # 格式化键名（将下划线替换为空格，首字母大写）
            display_key = key.replace("_", " ").title() + ":"
            table.add_row(display_key, str(value))

        return Panel(table, title="Statistics", border_style="blue")

    def _make_logs_panel(self) -> Panel:
        """创建日志面板"""
        if not self.logs:
            return Panel("No logs yet", title="Recent Logs", border_style="yellow")

        table = Table.grid(padding=(0, 1))
        table.add_column(style="bold", width=8)
        table.add_column()

        for level, message, color in self.logs:
            # 截断过长的消息
            if len(message) > 60:
                message = message[:57] + "..."
            table.add_row(f"[{level}]", Text(message, style=color))

        return Panel(table, title="Recent Logs", border_style="yellow")

    def _update_display(self):
        """更新显示"""
        if self.live and self._is_active:
            self.live.update(self._build_layout())

    @contextmanager
    def phase(self, phase_name: str, total: Optional[int] = None):
        """阶段上下文管理器"""
        self.start_phase(phase_name, total)
        try:
            yield self
        finally:
            pass  # 不自动结束，等待下一个阶段

    def __enter__(self):
        """上下文管理器入口"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.stop()
        return False


# 全局便捷函数
def get_tui() -> BacktestTUIManager:
    """获取全局 TUI 实例"""
    return BacktestTUIManager.get_instance()


def is_tui_enabled() -> bool:
    """检查 TUI 是否启用"""
    return BacktestTUIManager.is_enabled()
