"""Tests for checkpoint manager"""

import json
import tempfile
from pathlib import Path


from langgraph.infrastructure.graph.checkpoint import CheckpointManager


class TestCheckpointManager:
    """检查点管理器测试"""

    def test_save_and_load_checkpoint(self):
        """测试保存和加载检查点"""
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_dir = Path(tmpdir)
            manager = CheckpointManager(checkpoint_dir)

            workflow_id = "test-workflow-123"
            node_name = "test-node"
            state = {"key": "value", "count": 42}

            # 保存检查点
            checkpoint_file = manager.save_checkpoint(workflow_id, node_name, state)

            assert checkpoint_file.exists()

            # 加载检查点
            loaded_data = manager.load_checkpoint(workflow_id)

            assert loaded_data is not None
            assert loaded_data["workflow_id"] == workflow_id
            assert loaded_data["node_name"] == node_name
            assert loaded_data["state"] == state

    def test_load_nonexistent_checkpoint(self):
        """测试加载不存在的检查点"""
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_dir = Path(tmpdir)
            manager = CheckpointManager(checkpoint_dir)

            loaded_data = manager.load_checkpoint("nonexistent-workflow")

            assert loaded_data is None

    def test_delete_checkpoint(self):
        """测试删除检查点"""
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_dir = Path(tmpdir)
            manager = CheckpointManager(checkpoint_dir)

            workflow_id = "test-workflow-123"
            state = {"key": "value"}

            # 保存检查点
            manager.save_checkpoint(workflow_id, "test-node", state)

            # 删除检查点
            result = manager.delete_checkpoint(workflow_id)

            assert result is True

            # 检查点应该不存在
            loaded_data = manager.load_checkpoint(workflow_id)
            assert loaded_data is None

    def test_delete_nonexistent_checkpoint(self):
        """测试删除不存在的检查点"""
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_dir = Path(tmpdir)
            manager = CheckpointManager(checkpoint_dir)

            result = manager.delete_checkpoint("nonexistent-workflow")

            assert result is False

    def test_list_checkpoints(self):
        """测试列出所有检查点"""
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_dir = Path(tmpdir)
            manager = CheckpointManager(checkpoint_dir)

            # 保存多个检查点
            manager.save_checkpoint("workflow-1", "node-1", {"data": 1})
            manager.save_checkpoint("workflow-2", "node-2", {"data": 2})

            # 列出检查点
            checkpoints = manager.list_checkpoints()

            assert len(checkpoints) == 2
            workflow_ids = [cp["workflow_id"] for cp in checkpoints]
            assert "workflow-1" in workflow_ids
            assert "workflow-2" in workflow_ids

    def test_archive_checkpoint(self):
        """测试归档检查点"""
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_dir = Path(tmpdir)
            manager = CheckpointManager(checkpoint_dir)

            workflow_id = "test-workflow-123"
            state = {"key": "value"}

            # 保存检查点
            manager.save_checkpoint(workflow_id, "test-node", state)

            # 归档检查点
            archive_file = manager.archive_checkpoint(workflow_id)

            assert archive_file is not None
            assert archive_file.exists()
            assert workflow_id in archive_file.name

            # 验证归档内容
            with open(archive_file, "r") as f:
                archived_data = json.load(f)

            assert archived_data["workflow_id"] == workflow_id
            assert archived_data["state"] == state

    def test_checkpoint_with_metadata(self):
        """测试带元数据的检查点"""
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_dir = Path(tmpdir)
            manager = CheckpointManager(checkpoint_dir)

            workflow_id = "test-workflow-123"
            state = {"key": "value"}
            metadata = {"iteration": 5, "score": 0.85}

            # 保存检查点
            manager.save_checkpoint(workflow_id, "test-node", state, metadata)

            # 加载检查点
            loaded_data = manager.load_checkpoint(workflow_id)

            assert loaded_data is not None
            assert loaded_data["metadata"] == metadata

    def test_overwrite_checkpoint(self):
        """测试覆盖检查点"""
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_dir = Path(tmpdir)
            manager = CheckpointManager(checkpoint_dir)

            workflow_id = "test-workflow-123"

            # 保存第一个检查点
            manager.save_checkpoint(workflow_id, "node-1", {"version": 1})

            # 覆盖检查点
            manager.save_checkpoint(workflow_id, "node-2", {"version": 2})

            # 应该只有最新的检查点
            loaded_data = manager.load_checkpoint(workflow_id)

            assert loaded_data is not None
            assert loaded_data["node_name"] == "node-2"
            assert loaded_data["state"]["version"] == 2
