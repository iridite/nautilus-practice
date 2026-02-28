"""
测试 generate_universe.py 的可编程接口
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.generate_universe import generate_universe_data


class TestGenerateUniverseData(unittest.TestCase):
    """测试 generate_universe_data() 函数"""

    def test_invalid_top_n(self):
        """测试 top_n 参数验证"""
        with self.assertRaises(ValueError) as ctx:
            generate_universe_data(top_n=0)
        self.assertIn("top_n 必须 > 0", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            generate_universe_data(top_n=-5)
        self.assertIn("top_n 必须 > 0", str(ctx.exception))

    def test_invalid_freq(self):
        """测试 freq 参数验证"""
        with self.assertRaises(ValueError) as ctx:
            generate_universe_data(freq="INVALID")
        self.assertIn("freq 必须在", str(ctx.exception))

    def test_nonexistent_data_dir(self):
        """测试数据目录不存在时返回空字典"""
        fake_dir = Path("/nonexistent/path/to/data")
        result = generate_universe_data(data_dir=fake_dir)
        self.assertEqual(result, {})

    def test_valid_parameters(self):
        """测试有效参数不抛出异常"""
        # 使用默认参数
        try:
            result = generate_universe_data()
            self.assertIsInstance(result, dict)
        except ValueError:
            self.fail("generate_universe_data() raised ValueError with valid parameters")

        # 使用自定义参数
        try:
            result = generate_universe_data(top_n=10, freq="ME")
            self.assertIsInstance(result, dict)
        except ValueError:
            self.fail("generate_universe_data() raised ValueError with valid parameters")

    def test_all_valid_frequencies(self):
        """测试所有有效的频率参数"""
        valid_freqs = ["ME", "W-MON", "2W-MON"]
        for freq in valid_freqs:
            try:
                result = generate_universe_data(freq=freq)
                self.assertIsInstance(result, dict)
            except ValueError:
                self.fail(f"generate_universe_data() raised ValueError with valid freq: {freq}")


if __name__ == "__main__":
    unittest.main()
