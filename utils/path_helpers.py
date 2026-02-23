"""
路径辅助工具模块

提供项目路径管理的核心功能。
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional, Union


@lru_cache(maxsize=1)
def get_project_root(start_path: Optional[Union[str, Path]] = None) -> Path:
    """
    获取项目根目录路径（带缓存）

    从当前文件或指定路径向上查找，直到找到包含标志文件的目录。
    标志文件：pyproject.toml, setup.py, .git

    Parameters
    ----------
    start_path : str | Path | None
        起始搜索路径，默认为当前文件所在目录

    Returns
    -------
    Path
        项目根目录的绝对路径

    Raises
    ------
    RuntimeError
        如果无法找到项目根目录
    """
    if start_path is None:
        current = Path(__file__).resolve().parent
    else:
        current = Path(start_path).resolve()

    markers = ["pyproject.toml", "setup.py", ".git"]

    for parent in [current] + list(current.parents):
        if any((parent / marker).exists() for marker in markers):
            return parent

    raise RuntimeError(
        f"无法找到项目根目录。从 {current} 开始搜索，未找到标志文件：{', '.join(markers)}"
    )
