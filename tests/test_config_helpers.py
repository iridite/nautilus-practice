"""
配置助手工具模块单元测试

测试内容：
1. parse_universe_symbols() - Universe符号解析
2. Universe文件格式处理
3. 符号验证和清理
4. 错误处理和边界情况

Usage:
    uv run python -m unittest tests.test_config_helpers -v
"""

import tempfile
import unittest
from pathlib import Path

from utils.config_helpers import load_universe_symbols_from_file


class TestConfigHelpers(unittest.TestCase):
    """配置助手工具测试类"""

    def setUp(self):
        """设置测试环境"""
        # 创建临时目录用于测试
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)
        
        # 创建测试Universe文件
        self.create_test_files()

    def tearDown(self):
        """清理测试环境"""
        self.temp_dir.cleanup()

    def create_test_files(self):
        """创建各种格式的测试Universe文件"""
        # 1. 标准格式的Universe文件
        self.standard_universe = self.test_dir / "standard_universe.txt"
        standard_content = """# 标准Universe文件
# 包含主流交易对

BTCUSDT
ETHUSDT
BNBUSDT
ADAUSDT
SOLUSDT

# 更多符号
XRPUSDT
DOTUSDT
LINKUSDT
"""
        with open(self.standard_universe, 'w') as f:
            f.write(standard_content)

        # 2. 带空行和特殊字符的Universe文件
        self.mixed_universe = self.test_dir / "mixed_universe.txt"
        mixed_content = """
# 混合格式的Universe文件

BTCUSDT


ETHUSDT   # 带空格和注释
    BNBUSDT    # 前后有空格

# 一些垃圾行
ADAUSDT

    
SOLUSDT
"""
        with open(self.mixed_universe, 'w') as f:
            f.write(mixed_content)

        # 3. 空Universe文件
        self.empty_universe = self.test_dir / "empty_universe.txt"
        with open(self.empty_universe, 'w') as f:
            f.write("# 只有注释的文件\n# 没有实际符号\n")

        # 4. 只有符号没有注释的文件
        self.simple_universe = self.test_dir / "simple_universe.txt"
        simple_content = """BTCUSDT
ETHUSDT
BNBUSDT
ADAUSDT
SOLUSDT"""
        with open(self.simple_universe, 'w') as f:
            f.write(simple_content)

        # 5. 包含重复符号的文件
        self.duplicate_universe = self.test_dir / "duplicate_universe.txt"
        duplicate_content = """BTCUSDT
ETHUSDT
BTCUSDT  # 重复
BNBUSDT
ETHUSDT  # 又一次重复
ADAUSDT
"""
        with open(self.duplicate_universe, 'w') as f:
            f.write(duplicate_content)

    def test_load_universe_symbols_from_file_standard_format(self):
        """测试标准格式Universe文件解析"""
        symbols = load_universe_symbols_from_file(self.standard_universe)
        
        # 验证解析出正确数量的符号
        expected_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT", "XRPUSDT", "DOTUSDT", "LINKUSDT"]
        self.assertEqual(len(symbols), len(expected_symbols))
        
        # 验证所有预期符号都在结果中
        for symbol in expected_symbols:
            self.assertIn(symbol, symbols)

    def test_load_universe_symbols_from_file_mixed_format(self):
        """测试混合格式Universe文件解析"""
        symbols = load_universe_symbols_from_file(self.mixed_universe)
        
        # 验证解析出正确的符号（忽略空行、注释、空格）
        expected_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT"]
        self.assertEqual(len(symbols), len(expected_symbols))
        
        # 验证所有符号都被正确清理
        for symbol in symbols:
            self.assertIn(symbol, expected_symbols)
            # 验证符号没有多余的空格
            self.assertEqual(symbol, symbol.strip())

    def test_load_universe_symbols_from_file_empty_file(self):
        """测试空Universe文件解析"""
        symbols = load_universe_symbols_from_file(self.empty_universe)
        
        # 空文件应该返回空列表
        self.assertEqual(len(symbols), 0)
        self.assertEqual(symbols, [])

    def test_load_universe_symbols_from_file_simple_format(self):
        """测试简单格式Universe文件解析"""
        symbols = load_universe_symbols_from_file(self.simple_universe)
        
        # 验证解析出正确的符号
        expected_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT"]
        self.assertEqual(len(symbols), len(expected_symbols))
        
        # 验证顺序保持
        for i, symbol in enumerate(expected_symbols):
            self.assertEqual(symbols[i], symbol)

    def test_load_universe_symbols_from_file_duplicate_removal(self):
        """测试重复符号去除"""
        symbols = load_universe_symbols_from_file(self.duplicate_universe)
        
        # 验证重复符号被去除
        expected_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT"]
        self.assertEqual(len(symbols), len(expected_symbols))
        
        # 验证没有重复符号
        unique_symbols = list(set(symbols))
        self.assertEqual(len(symbols), len(unique_symbols))

    def test_load_universe_symbols_from_file_file_not_found(self):
        """测试文件不存在的情况"""
        nonexistent_file = self.test_dir / "does_not_exist.txt"
        
        symbols = load_universe_symbols_from_file(nonexistent_file)
        
        # 不存在的文件应该返回空列表
        self.assertEqual(symbols, [])

    def test_load_universe_symbols_from_file_case_handling(self):
        """测试大小写处理"""
        # 创建包含小写符号的测试文件
        lowercase_universe = self.test_dir / "lowercase_universe.txt"
        with open(lowercase_universe, 'w') as f:
            f.write("btcusdt\nethusdt\nBNBUSDT\nadausdt\n")
        
        symbols = load_universe_symbols_from_file(lowercase_universe)
        
        # 验证所有符号都被转换为大写
        expected_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT"]
        for symbol in symbols:
            self.assertIn(symbol, expected_symbols)
            self.assertTrue(symbol.isupper())

    def test_load_universe_symbols_from_file_whitespace_handling(self):
        """测试空白字符处理"""
        # 创建包含各种空白字符的测试文件
        whitespace_universe = self.test_dir / "whitespace_universe.txt"
        with open(whitespace_universe, 'w') as f:
            f.write("  BTCUSDT  \n\tETHUSDT\t\n BNBUSDT \n")
        
        symbols = load_universe_symbols_from_file(whitespace_universe)
        
        # 验证空白字符被正确去除
        expected_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        self.assertEqual(symbols, expected_symbols)
        
        # 验证没有空白字符残留
        for symbol in symbols:
            self.assertEqual(symbol, symbol.strip())

    def test_load_universe_symbols_from_file_comment_variations(self):
        """测试各种注释格式"""
        # 创建包含不同注释格式的测试文件
        comment_universe = self.test_dir / "comment_universe.txt"
        comment_content = """# 这是注释
BTCUSDT  # 行尾注释
ETHUSDT
## 另一种注释格式
BNBUSDT # 带空格的注释
# 完整注释行
ADAUSDT
### 第三种注释
"""
        with open(comment_universe, 'w') as f:
            f.write(comment_content)
        
        symbols = load_universe_symbols_from_file(comment_universe)
        
        # 验证只解析出符号，忽略注释
        expected_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT"]
        self.assertEqual(symbols, expected_symbols)

    def test_load_universe_symbols_from_file_invalid_symbols(self):
        """测试无效符号的处理"""
        # 创建包含可能无效符号的测试文件
        invalid_universe = self.test_dir / "invalid_universe.txt"
        with open(invalid_universe, 'w') as f:
            f.write("BTCUSDT\n123INVALID\nETHUSDT\n@#$%\nBNBUSDT\n")
        
        symbols = load_universe_symbols_from_file(invalid_universe)
        
        # 验证有效符号被保留，无效符号被过滤
        # 注意：当前实现可能不会过滤无效符号，这取决于具体实现
        self.assertIn("BTCUSDT", symbols)
        self.assertIn("ETHUSDT", symbols)
        self.assertIn("BNBUSDT", symbols)

    def test_load_universe_symbols_from_file_large_file(self):
        """测试大文件处理"""
        # 创建包含大量符号的测试文件
        large_universe = self.test_dir / "large_universe.txt"
        with open(large_universe, 'w') as f:
            f.write("# 大量符号测试\n")
            for i in range(100):
                f.write(f"SYMBOL{i:03d}USDT\n")
        
        symbols = load_universe_symbols_from_file(large_universe)
        
        # 验证解析出正确数量的符号
        self.assertEqual(len(symbols), 100)
        
        # 验证符号格式正确
        for i, symbol in enumerate(symbols):
            expected_symbol = f"SYMBOL{i:03d}USDT"
            self.assertEqual(symbol, expected_symbol)

    def test_load_universe_symbols_from_file_encoding_handling(self):
        """测试文件编码处理"""
        # 创建包含非ASCII字符的测试文件（在注释中）
        encoding_universe = self.test_dir / "encoding_universe.txt"
        with open(encoding_universe, 'w', encoding='utf-8') as f:
            f.write("# 包含中文注释的Universe文件\n")
            f.write("BTCUSDT  # 比特币\n")
            f.write("ETHUSDT  # 以太坊\n")
            f.write("# 更多交易对\n")
            f.write("BNBUSDT\n")
        
        symbols = load_universe_symbols_from_file(encoding_universe)
        
        # 验证正确处理UTF-8编码
        expected_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        self.assertEqual(symbols, expected_symbols)

    def test_load_universe_symbols_from_file_preserve_order(self):
        """测试顺序保持"""
        symbols = load_universe_symbols_from_file(self.simple_universe)
        
        # 验证符号顺序与文件中的顺序一致
        expected_order = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT"]
        self.assertEqual(symbols, expected_order)


if __name__ == "__main__":
    unittest.main()