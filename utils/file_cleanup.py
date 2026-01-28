"""
文件清理工具

自动清理 log 和 output 目录中的旧文件，防止文件堆积。
"""

import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class FileCleanupConfig:
    """文件清理配置"""

    def __init__(
        self,
        max_files_per_dir: int = 100,
        enabled: bool = True,
        target_dirs: Optional[List[str]] = None,
    ):
        self.max_files_per_dir = max_files_per_dir
        self.enabled = enabled
        self.target_dirs = target_dirs or ["log", "output"]


def cleanup_directory(
    directory: Path,
    max_files: int = 100,
    recursive: bool = True,
) -> int:
    """
    清理目录中的旧文件

    Args:
        directory: 目标目录
        max_files: 每个子目录最大文件数
        recursive: 是否递归处理子目录

    Returns:
        int: 删除的文件总数
    """
    if not directory.exists():
        return 0

    deleted_count = 0

    if recursive:
        # 递归处理所有子目录
        for subdir in directory.rglob("*"):
            if subdir.is_dir():
                deleted_count += _cleanup_single_dir(subdir, max_files)
    else:
        deleted_count = _cleanup_single_dir(directory, max_files)

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
    # 获取目录中的所有文件（不包括子目录）
    files = [f for f in directory.iterdir() if f.is_file()]

    if len(files) <= max_files:
        return 0

    # 按修改时间排序（最旧的在前）
    files.sort(key=lambda f: f.stat().st_mtime)

    # 计算需要删除的文件数
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
    config: Optional[FileCleanupConfig] = None,
) -> int:
    """
    自动清理配置的目录

    Args:
        base_dir: 项目根目录
        config: 清理配置

    Returns:
        int: 删除的文件总数
    """
    if config is None:
        config = FileCleanupConfig()

    if not config.enabled:
        return 0

    total_deleted = 0

    for target_dir in config.target_dirs:
        dir_path = base_dir / target_dir
        if dir_path.exists():
            deleted = cleanup_directory(dir_path, config.max_files_per_dir)
            total_deleted += deleted

    if total_deleted > 0:
        logger.info(f"Total files cleaned: {total_deleted}")

    return total_deleted
