"""Checkpoint recovery mechanism for workflow graphs"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from shared.logging import get_logger

logger = get_logger(__name__)


class CheckpointManager:
    """工作流检查点管理器"""

    def __init__(self, checkpoint_dir: Path):
        """
        初始化检查点管理器

        Args:
            checkpoint_dir: 检查点保存目录
        """
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Checkpoint manager initialized", checkpoint_dir=str(checkpoint_dir))

    def save_checkpoint(
        self,
        workflow_id: str,
        node_name: str,
        state: dict[str, Any],
        metadata: Optional[dict[str, Any]] = None,
    ) -> Path:
        """
        保存检查点

        Args:
            workflow_id: 工作流 ID
            node_name: 当前节点名称
            state: 当前状态
            metadata: 额外元数据

        Returns:
            检查点文件路径
        """
        checkpoint_data = {
            "workflow_id": workflow_id,
            "node_name": node_name,
            "state": state,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        }

        checkpoint_file = self.checkpoint_dir / f"{workflow_id}_latest.json"

        try:
            with open(checkpoint_file, "w") as f:
                json.dump(checkpoint_data, f, indent=2, default=str)

            logger.info(
                "Checkpoint saved",
                workflow_id=workflow_id,
                node_name=node_name,
                file=str(checkpoint_file),
            )
            return checkpoint_file

        except Exception as e:
            logger.error("Failed to save checkpoint", workflow_id=workflow_id, error=str(e))
            raise

    def load_checkpoint(self, workflow_id: str) -> Optional[dict[str, Any]]:
        """
        加载检查点

        Args:
            workflow_id: 工作流 ID

        Returns:
            检查点数据，如果不存在则返回 None
        """
        checkpoint_file = self.checkpoint_dir / f"{workflow_id}_latest.json"

        if not checkpoint_file.exists():
            logger.debug("No checkpoint found", workflow_id=workflow_id)
            return None

        try:
            with open(checkpoint_file, "r") as f:
                checkpoint_data = json.load(f)

            logger.info(
                "Checkpoint loaded",
                workflow_id=workflow_id,
                node_name=checkpoint_data.get("node_name"),
                timestamp=checkpoint_data.get("timestamp"),
            )
            return checkpoint_data

        except Exception as e:
            logger.error("Failed to load checkpoint", workflow_id=workflow_id, error=str(e))
            return None

    def delete_checkpoint(self, workflow_id: str) -> bool:
        """
        删除检查点

        Args:
            workflow_id: 工作流 ID

        Returns:
            是否成功删除
        """
        checkpoint_file = self.checkpoint_dir / f"{workflow_id}_latest.json"

        if not checkpoint_file.exists():
            logger.debug("No checkpoint to delete", workflow_id=workflow_id)
            return False

        try:
            checkpoint_file.unlink()
            logger.info("Checkpoint deleted", workflow_id=workflow_id)
            return True

        except Exception as e:
            logger.error("Failed to delete checkpoint", workflow_id=workflow_id, error=str(e))
            return False

    def list_checkpoints(self) -> list[dict[str, Any]]:
        """
        列出所有检查点

        Returns:
            检查点信息列表
        """
        checkpoints = []

        for checkpoint_file in self.checkpoint_dir.glob("*_latest.json"):
            try:
                with open(checkpoint_file, "r") as f:
                    data = json.load(f)

                checkpoints.append(
                    {
                        "workflow_id": data.get("workflow_id"),
                        "node_name": data.get("node_name"),
                        "timestamp": data.get("timestamp"),
                        "file": str(checkpoint_file),
                    }
                )
            except Exception as e:
                logger.warning("Failed to read checkpoint file", file=str(checkpoint_file), error=str(e))

        return checkpoints

    def archive_checkpoint(self, workflow_id: str) -> Optional[Path]:
        """
        归档检查点（保留历史记录）

        Args:
            workflow_id: 工作流 ID

        Returns:
            归档文件路径，如果失败则返回 None
        """
        checkpoint_file = self.checkpoint_dir / f"{workflow_id}_latest.json"

        if not checkpoint_file.exists():
            logger.debug("No checkpoint to archive", workflow_id=workflow_id)
            return None

        try:
            # 读取检查点数据
            with open(checkpoint_file, "r") as f:
                data = json.load(f)

            # 生成归档文件名（带时间戳）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_file = self.checkpoint_dir / f"{workflow_id}_{timestamp}.json"

            # 保存归档
            with open(archive_file, "w") as f:
                json.dump(data, f, indent=2, default=str)

            logger.info("Checkpoint archived", workflow_id=workflow_id, archive_file=str(archive_file))
            return archive_file

        except Exception as e:
            logger.error("Failed to archive checkpoint", workflow_id=workflow_id, error=str(e))
            return None


class CheckpointMixin:
    """检查点功能混入类"""

    def __init__(self, *args: Any, checkpoint_manager: Optional[CheckpointManager] = None, **kwargs: Any):
        """
        初始化检查点混入

        Args:
            checkpoint_manager: 检查点管理器
        """
        super().__init__(*args, **kwargs)
        self.checkpoint_manager = checkpoint_manager

    def _save_checkpoint(
        self,
        workflow_id: str,
        node_name: str,
        state: dict[str, Any],
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        保存检查点（内部方法）

        Args:
            workflow_id: 工作流 ID
            node_name: 当前节点名称
            state: 当前状态
            metadata: 额外元数据
        """
        if self.checkpoint_manager:
            try:
                self.checkpoint_manager.save_checkpoint(workflow_id, node_name, state, metadata)
            except Exception as e:
                logger.warning("Checkpoint save failed, continuing execution", error=str(e))

    def _load_checkpoint(self, workflow_id: str) -> Optional[dict[str, Any]]:
        """
        加载检查点（内部方法）

        Args:
            workflow_id: 工作流 ID

        Returns:
            检查点数据
        """
        if self.checkpoint_manager:
            return self.checkpoint_manager.load_checkpoint(workflow_id)
        return None
