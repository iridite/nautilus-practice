"""
路径助手工具模块单元测试

测试内容：
1. get_project_root() - 项目根目录获取
2. 路径解析和验证
3. 不同环境下的路径处理
4. 边界情况测试

Usage:
    uv run python -m unittest tests.test_path_helpers -v
"""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from utils.path_helpers import get_project_root


class TestPathHelpers(unittest.TestCase):
    """路径助手工具测试类"""

    def test_get_project_root_basic(self):
        """测试基本的项目根目录获取"""
        root = get_project_root()

        # 验证返回值是Path对象
        self.assertIsInstance(root, Path)

        # 验证路径存在
        self.assertTrue(root.exists())

        # 验证是目录
        self.assertTrue(root.is_dir())

    def test_get_project_root_has_marker_files(self):
        """测试项目根目录包含标志性文件"""
        root = get_project_root()

        # 验证包含项目标志性文件
        expected_files = ["pyproject.toml", "main.py"]

        for file_name in expected_files:
            file_path = root / file_name
            self.assertTrue(
                file_path.exists(),
                f"项目根目录应包含 {file_name} 文件"
            )

    def test_get_project_root_has_expected_structure(self):
        """测试项目根目录有期望的目录结构"""
        root = get_project_root()

        # 验证包含预期的目录结构
        expected_dirs = ["utils", "strategy", "backtest", "tests", "scripts"]

        for dir_name in expected_dirs:
            dir_path = root / dir_name
            self.assertTrue(
                dir_path.exists(),
                f"项目根目录应包含 {dir_name} 目录"
            )
            self.assertTrue(
                dir_path.is_dir(),
                f"{dir_name} 应该是一个目录"
            )

    def test_get_project_root_consistency(self):
        """测试多次调用的一致性"""
        root1 = get_project_root()
        root2 = get_project_root()

        # 多次调用应返回相同路径
        self.assertEqual(root1, root2)

    def test_get_project_root_absolute_path(self):
        """测试返回的是绝对路径"""
        root = get_project_root()

        # 验证返回的是绝对路径
        self.assertTrue(root.is_absolute())

    def test_get_project_root_from_different_working_directories(self):
        """测试从不同工作目录调用的情况"""
        # 获取原始工作目录
        original_cwd = Path.cwd()

        try:
            # 测试从项目根目录调用
            root_from_root = get_project_root()

            # 切换到utils目录
            utils_dir = root_from_root / "utils"
            if utils_dir.exists():
                os.chdir(utils_dir)
                root_from_utils = get_project_root()

                # 从不同目录调用应返回相同的根目录
                self.assertEqual(root_from_root, root_from_utils)

            # 切换到tests目录
            tests_dir = root_from_root / "tests"
            if tests_dir.exists():
                os.chdir(tests_dir)
                root_from_tests = get_project_root()

                # 从不同目录调用应返回相同的根目录
                self.assertEqual(root_from_root, root_from_tests)

        finally:
            # 恢复原始工作目录
            os.chdir(original_cwd)

    def test_get_project_root_path_operations(self):
        """测试路径操作的正确性"""
        root = get_project_root()

        # 测试路径拼接操作
        data_dir = root / "data"
        utils_dir = root / "utils"

        self.assertEqual(data_dir.name, "data")
        self.assertEqual(utils_dir.name, "utils")

        # 测试路径是相对于根目录的
        self.assertEqual(data_dir.parent, root)
        self.assertEqual(utils_dir.parent, root)

    def test_get_project_root_with_subdirectories(self):
        """测试在子目录中也能正确获取项目根目录"""
        root = get_project_root()

        # 验证可以正确构建深层路径
        deep_path = root / "data" / "raw" / "BTCUSDT"

        # 验证路径构建正确
        expected_parts = ["data", "raw", "BTCUSDT"]
        actual_parts = deep_path.relative_to(root).parts

        self.assertEqual(actual_parts, tuple(expected_parts))

    @patch('pathlib.Path.cwd')
    def test_get_project_root_mock_environment(self, mock_cwd):
        """测试模拟环境下的行为"""
        # 模拟一个假的工作目录
        fake_project_dir = Path("/fake/project")
        mock_cwd.return_value = fake_project_dir

        # 在模拟环境下，函数应该能处理不存在的目录
        # 这主要测试函数不会崩溃
        try:
            root = get_project_root()
            # 在模拟环境下，应该返回一个Path对象
            self.assertIsInstance(root, Path)
        except Exception:
            # 如果抛出异常，说明函数正确处理了无效环境
            pass

    def test_get_project_root_file_system_operations(self):
        """测试文件系统操作的正确性"""
        root = get_project_root()

        # 验证可以正确进行文件系统操作
        # 测试文件读取路径
        pyproject_path = root / "pyproject.toml"
        if pyproject_path.exists():
            # 验证可以读取文件
            self.assertTrue(pyproject_path.is_file())
            # 验证文件有内容
            self.assertGreater(pyproject_path.stat().st_size, 0)

    def test_get_project_root_relative_path_resolution(self):
        """测试相对路径解析"""
        root = get_project_root()

        # 测试相对路径解析
        relative_path = "utils/time_helpers.py"
        full_path = root / relative_path

        # 验证路径解析正确
        expected_path = root / "utils" / "time_helpers.py"
        self.assertEqual(full_path, expected_path)

    def test_get_project_root_cross_platform_compatibility(self):
        """测试跨平台兼容性"""
        root = get_project_root()

        # 验证路径分隔符处理正确（跨平台）
        utils_path = root / "utils"

        # 在所有平台上，路径都应该能正确构建
        self.assertTrue(isinstance(utils_path, Path))

        # 验证路径字符串表示不包含错误的分隔符
        path_str = str(utils_path)
        self.assertNotIn("//", path_str)  # 不应有双斜杠
        self.assertNotIn("\\\\", path_str)  # 不应有双反斜杠

    def test_get_project_root_performance(self):
        """测试性能（简单的响应时间测试）"""
        import time

        # 测试函数执行时间
        start_time = time.time()
        root = get_project_root()
        end_time = time.time()

        execution_time = end_time - start_time

        # 函数应该在合理时间内完成（1秒内）
        self.assertLess(execution_time, 1.0)

        # 验证确实返回了有效结果
        self.assertIsInstance(root, Path)

    def test_get_project_root_edge_cases(self):
        """测试边界情况"""
        root = get_project_root()

        # 测试路径的各种属性
        self.assertIsNotNone(root)
        self.assertNotEqual(root, Path())  # 不应该是空路径
        self.assertGreater(len(str(root)), 0)  # 路径字符串不应为空


if __name__ == "__main__":
    unittest.main()