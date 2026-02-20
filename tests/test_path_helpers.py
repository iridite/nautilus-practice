"""
测试 utils/path_helpers.py 路径辅助工具
"""

import unittest
from pathlib import Path
import tempfile
import shutil

from utils.path_helpers import get_project_root


class TestGetProjectRoot(unittest.TestCase):
    """测试 get_project_root 函数"""

    def test_get_project_root_default(self):
        """测试默认获取项目根目录"""
        root = get_project_root()
        self.assertIsInstance(root, Path)
        self.assertTrue(root.exists())
        # 应该能找到 pyproject.toml
        self.assertTrue((root / "pyproject.toml").exists())

    def test_get_project_root_with_start_path(self):
        """测试从指定路径获取项目根目录"""
        # 使用当前文件所在目录作为起始路径
        current_file = Path(__file__)
        root = get_project_root(current_file)
        self.assertIsInstance(root, Path)
        self.assertTrue(root.exists())
        self.assertTrue((root / "pyproject.toml").exists())

    def test_get_project_root_with_string_path(self):
        """测试使用字符串路径"""
        current_file = str(Path(__file__))
        root = get_project_root(current_file)
        self.assertIsInstance(root, Path)
        self.assertTrue(root.exists())

    def test_get_project_root_caching(self):
        """测试缓存功能"""
        # 多次调用应该返回相同的对象（由于 lru_cache）
        root1 = get_project_root()
        root2 = get_project_root()
        self.assertEqual(root1, root2)

    def test_get_project_root_finds_git(self):
        """测试能找到 .git 目录"""
        root = get_project_root()
        # 项目根目录应该有 .git 或 pyproject.toml
        has_marker = (root / ".git").exists() or (root / "pyproject.toml").exists()
        self.assertTrue(has_marker)

    def test_get_project_root_not_found(self):
        """测试找不到项目根目录的情况"""
        # 创建一个临时目录，不包含任何标志文件
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir) / "deep" / "nested" / "path"
            temp_path.mkdir(parents=True, exist_ok=True)

            # 应该抛出 RuntimeError
            with self.assertRaises(RuntimeError) as context:
                get_project_root(temp_path)

            self.assertIn("无法找到项目根目录", str(context.exception))

    def test_get_project_root_absolute_path(self):
        """测试返回的是绝对路径"""
        root = get_project_root()
        self.assertTrue(root.is_absolute())

    def test_get_project_root_from_subdirectory(self):
        """测试从子目录获取项目根目录"""
        # 使用 tests 目录作为起始点
        tests_dir = Path(__file__).parent
        root = get_project_root(tests_dir)

        # 应该找到项目根目录，而不是 tests 目录
        self.assertTrue((root / "pyproject.toml").exists())
        self.assertNotEqual(root, tests_dir)


if __name__ == "__main__":
    unittest.main()
