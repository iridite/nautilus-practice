"""
文件清理工具

自动清理 log 和 output 目录中的旧文件，防止文件堆积。
"""

import gzip
import logging
import shutil
from datetime import datetime
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


def cleanup_by_age(
    directory: Path,
    keep_days: int = 7,
    delete_days: int = 30,
) -> dict[str, int]:
    """
    基于时间的日志轮转清理

    Args:
        directory: 目标目录
        keep_days: 保留最近N天的日志（不压缩）
        delete_days: 删除超过N天的日志和压缩文件

    Returns:
        dict: 统计信息 {'compressed': N, 'deleted': N}
    """
    if not directory.exists():
        return {"compressed": 0, "deleted": 0}

    now = datetime.now()
    stats = {"compressed": 0, "deleted": 0}

    # 处理 .log 文件
    for file_path in directory.rglob("*.log"):
        if not file_path.is_file():
            continue

        mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
        age_days = (now - mtime).days

        # 删除超过 delete_days 的文件
        if age_days > delete_days:
            try:
                file_path.unlink()
                stats["deleted"] += 1
                logger.debug(f"Deleted old log: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to delete {file_path}: {e}")

        # 压缩 keep_days 到 delete_days 之间的文件
        elif age_days > keep_days:
            gz_path = file_path.with_suffix(".log.gz")
            if gz_path.exists():
                continue

            try:
                with open(file_path, "rb") as f_in:
                    with gzip.open(gz_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                file_path.unlink()
                stats["compressed"] += 1
                logger.debug(f"Compressed log: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to compress {file_path}: {e}")

    # 删除超过 delete_days 的 .gz 文件
    for gz_path in directory.rglob("*.log.gz"):
        if not gz_path.is_file():
            continue

        mtime = datetime.fromtimestamp(gz_path.stat().st_mtime)
        age_days = (now - mtime).days

        if age_days > delete_days:
            try:
                gz_path.unlink()
                stats["deleted"] += 1
                logger.debug(f"Deleted old compressed log: {gz_path}")
            except Exception as e:
                logger.warning(f"Failed to delete {gz_path}: {e}")

    if stats["compressed"] > 0 or stats["deleted"] > 0:
        logger.info(
            f"Log rotation in {directory}: "
            f"compressed {stats['compressed']}, deleted {stats['deleted']} files"
        )

    return stats


def auto_cleanup_by_age(
    base_dir: Path,
    keep_days: int = 7,
    delete_days: int = 30,
    enabled: bool = True,
    target_dirs: list[str] | None = None,
) -> dict[str, int]:
    """
    基于时间的自动日志轮转

    Args:
        base_dir: 项目根目录
        keep_days: 保留最近N天的日志
        delete_days: 删除超过N天的日志
        enabled: 是否启用清理
        target_dirs: 目标目录列表

    Returns:
        dict: 统计信息 {'compressed': N, 'deleted': N}
    """
    if not enabled:
        return {"compressed": 0, "deleted": 0}

    if target_dirs is None:
        target_dirs = ["log"]

    total_stats = {"compressed": 0, "deleted": 0}
    for target_dir in target_dirs:
        dir_path = base_dir / target_dir
        if dir_path.exists():
            stats = cleanup_by_age(dir_path, keep_days, delete_days)
            total_stats["compressed"] += stats["compressed"]
            total_stats["deleted"] += stats["deleted"]

    if total_stats["compressed"] > 0 or total_stats["deleted"] > 0:
        logger.info(
            f"Total log rotation: "
            f"compressed {total_stats['compressed']}, "
            f"deleted {total_stats['deleted']} files"
        )

    return total_stats
