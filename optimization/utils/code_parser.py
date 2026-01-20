"""
代码解析与验证工具 (AST 增强版)
"""

import ast
import re
from typing import Any, Dict, List, Tuple


def extract_code(text: str) -> str:
    """
    从 LLM 回复中提取 Python 代码，并进行清洗。
    只负责提取和清洗，不负责逻辑验证。
    """
    code = ""
    text = text.strip()

    # 1. 提取 Markdown 代码块
    # 优先匹配 python 标记的代码块
    python_block_match = re.search(r"```python\s*(.*?)```", text, re.DOTALL)
    if python_block_match:
        code = python_block_match.group(1)
    else:
        # 尝试匹配无语言标记的代码块
        generic_block_match = re.search(r"```\s*(.*?)```", text, re.DOTALL)
        if generic_block_match:
            code = generic_block_match.group(1)
        else:
            # 如果没有代码块标记，假设全文都是代码（视情况而定，对于 strict prompt 这是一个兜底）
            # 但为了安全，如果没找到代码块，我们检查是否有 class 定义，如果有则认为是纯代码
            if "class " in text and "def " in text:
                code = text
            else:
                # 最后的尝试：可能只有一行代码或开头没有标记
                code = text

    code = code.strip()

    if not code:
        raise ValueError("未能从回复中提取到有效的代码块 (```python ... ```)")

    # 2. 修复转义字符 (JSON 传输常见问题)
    code = _fix_escape_sequences(code)

    return code


def _fix_escape_sequences(code: str) -> str:
    """修复由 API 传输导致的过度转义问题"""
    # 检查是否包含字面量的 \n
    if r"\n" in code or "\\n" in code:
        actual_newlines = code.count("\n")
        # 统计字面量 \n 的数量
        escaped_newlines = code.count(r"\n") + code.count("\\n")

        # 启发式判断：如果转义符比实际换行符多得多，说明需要反转义
        if escaped_newlines > actual_newlines or actual_newlines < 5:
            print(f"🔧 [Parser] 检测到转义换行符，正在修复...")
            code = code.replace(r"\n", "\n").replace("\\n", "\n")
            code = code.replace(r"\t", "    ").replace("\\t", "    ")
            code = code.replace(r"\"", '"').replace("\\'", "'")

    return code


def validate_strategy_code(code: str) -> Tuple[bool, str]:
    """
    使用 AST (抽象语法树) 对策略代码进行深度验证。
    """
    # 1. 基础长度检查
    if not code or len(code) < 500:
        return False, f"代码长度过短 ({len(code)} 字符)，完整策略通常 > 3000 字符。"

    # 2. 语法检查 (Syntax Check)
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Python 语法错误 (Line {e.lineno}): {e.msg}"
    except Exception as e:
        return False, f"代码解析失败: {str(e)}"

    # 3. AST 结构分析
    analyzer = StrategyVisitor()
    analyzer.visit(tree)

    # 4. 规则校验
    errors = []

    # 4.1 检查类定义
    if not analyzer.has_config_class:
        errors.append("缺少 Config 类定义 (需继承 BaseStrategyConfig)")
    if not analyzer.has_strategy_class:
        errors.append("缺少 Strategy 类定义 (需继承 BaseStrategy)")

    # 4.2 检查关键方法实现
    required_methods = ["__init__", "on_start", "on_bar"]
    for method in required_methods:
        if method not in analyzer.methods_found:
            errors.append(f"Strategy 类缺少关键方法: {method}")
        else:
            # 检查方法体是否有效（不是 pass, ..., 且长度足够）
            body_stats = analyzer.methods_found[method]
            if body_stats["is_empty_or_pass"]:
                errors.append(f"方法 {method} 未实现逻辑 (只有 pass/...)")
            elif body_stats["stmt_count"] < 3:
                # 只有一两行代码的关键方法通常是有问题的 (__init__ 除外，可能调用 super)
                if method != "__init__":
                    errors.append(
                        f"方法 {method} 逻辑过于简单 ({body_stats['stmt_count']} 行)"
                    )

    # 4.3 检查 import 语句
    if analyzer.import_count < 5:
        errors.append("Import 语句过少，可能缺少必要的依赖库")

    # 4.4 检查 Nautilus 核心组件引用 (通过 AST 检查是否有特定调用或类型标注)
    # 这是一个宽松检查，确保代码是针对 Nautilus 写的
    required_keywords = ["Bar", "InstrumentId", "Config"]
    missing_keywords = [kw for kw in required_keywords if kw not in code]
    if len(missing_keywords) > 1:
        errors.append(f"代码似乎未引用 Nautilus 核心组件: {missing_keywords}")

    if errors:
        return False, "; ".join(errors)

    return True, "代码结构验证通过"


class StrategyVisitor(ast.NodeVisitor):
    """
    AST 访问器，用于提取代码结构信息
    """

    def __init__(self):
        self.has_config_class = False
        self.has_strategy_class = False
        self.methods_found = {}  # {method_name: {stmt_count: int, is_empty_or_pass: bool}}
        self.import_count = 0
        self.in_strategy_class = False

    def visit_Import(self, node):
        self.import_count += 1
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        self.import_count += 1
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        # 启发式判断类类型
        if "Config" in node.name:
            self.has_config_class = True

        # 检查是否是策略类 (通常包含 Strategy 或继承 BaseStrategy)
        is_strategy = "Strategy" in node.name
        # 也可以检查基类 (bases)，但这需要解析基类名称，比较复杂，这里用名字简单判断

        if is_strategy:
            self.has_strategy_class = True
            self.in_strategy_class = True
            self.generic_visit(node)  # 继续遍历类内部
            self.in_strategy_class = False
        else:
            self.generic_visit(node)

    def visit_FunctionDef(self, node):
        # 只关心 Strategy 类中的方法
        if self.in_strategy_class:
            stmt_count = 0
            is_empty_or_pass = False

            # 分析函数体
            if not node.body:
                is_empty_or_pass = True
            else:
                # 过滤掉 Docstring 和 注释 (ast.parse 会自动忽略 # 注释，但 docstring 是 Expr)
                real_stmts = []
                for stmt in node.body:
                    if (
                        isinstance(stmt, ast.Expr)
                        and isinstance(stmt.value, ast.Constant)
                        and isinstance(stmt.value.value, str)
                    ):
                        # 这是一个 Docstring
                        continue
                    real_stmts.append(stmt)

                stmt_count = len(real_stmts)

                if stmt_count == 0:
                    is_empty_or_pass = True
                elif stmt_count == 1:
                    # 检查是否是 pass 或 ...
                    first_stmt = real_stmts[0]
                    if isinstance(first_stmt, ast.Pass):
                        is_empty_or_pass = True
                    elif (
                        isinstance(first_stmt, ast.Expr)
                        and isinstance(first_stmt.value, ast.Constant)
                        and first_stmt.value.value is Ellipsis
                    ):
                        is_empty_or_pass = True

            self.methods_found[node.name] = {
                "stmt_count": stmt_count,
                "is_empty_or_pass": is_empty_or_pass,
            }

        self.generic_visit(node)


def extract_parameters(code: str) -> Dict[str, str]:
    """
    (保留原有的简单实现，用于快速提取参数，不需要 AST 那么重)
    从代码中提取参数
    """
    params = {}
    for line in code.split("\n"):
        if "=" in line and not line.strip().startswith("#"):
            try:
                # 简单的字符串分割，适用于 Python 的 field = value 语法
                parts = line.split("=", 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    # 去掉注释和类型标注 (简单的 split 处理)
                    if ":" in key:
                        key = key.split(":")[0].strip()

                    value = parts[1].strip()
                    # 去掉行尾注释
                    if "#" in value:
                        value = value.split("#")[0].strip()

                    params[key] = value
            except Exception:
                pass
    return params
