"""
文件清理工具

自动清理 log 和 output 目录中的旧文件，防止文件堆积。
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def cleanup_directory(directory: Path, max_files: int = 100) -> int:
    """
    清理目录中的旧文件

    Args:
        directory: 目标目录
        max_files: 每个子目录最大文件数

    Returns:
        int: 删除的文件总数
    """
    if not directory.exists():
        return 0

    deleted_count = 0
    for subdir in directory.rglob("*"):
        if subdir.is_dir():
            deleted_count += _cleanup_single_dir(subdir, max_files)

    return deleted_count


def _cleanup_single_dir(directory: Path, max_files: int) -> int:
    """
    清理单个目录中的旧文件

    Args:
        directory: 目标目录
        max_files: 最大文件数

    Returns:
        int: 删除的文件数
    """
    files = [f for f in directory.iterdir() if f.is_file()]

    if len(files) <= max_files:
        return 0

    files.sort(key=lambda f: f.stat().st_mtime)
    files_to_delete = len(files) - max_files
    deleted_count = 0

    for file in files[:files_to_delete]:
        try:
            file.unlink()
            deleted_count += 1
            logger.debug(f"Deleted old file: {file}")
        except Exception as e:
            logger.warning(f"Failed to delete {file}: {e}")

    if deleted_count > 0:
        logger.info(f"Cleaned {deleted_count} files from {directory}")

    return deleted_count


def auto_cleanup(
    base_dir: Path,
    max_files_per_dir: int = 100,
    enabled: bool = True,
    target_dirs: list[str] | None = None,
) -> int:
    """
    自动清理配置的目录

    Args:
        base_dir: 项目根目录
        max_files_per_dir: 每个目录最大文件数
        enabled: 是否启用清理
        target_dirs: 目标目录列表

    Returns:
        int: 删除的文件总数
    """
    if not enabled:
        return 0

    if target_dirs is None:
        target_dirs = ["log", "output"]

    total_deleted = 0
    for target_dir in target_dirs:
        dir_path = base_dir / target_dir
        if dir_path.exists():
            deleted = cleanup_directory(dir_path, max_files_per_dir)
            total_deleted += deleted

    if total_deleted > 0:
        logger.info(f"Total files cleaned: {total_deleted}")

    return total_deleted
