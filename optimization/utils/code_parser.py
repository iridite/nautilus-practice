"""
代码解析工具
"""

import re
from typing import Any, Dict


def extract_code(text: str) -> str:
    """
    提取 Markdown 中的代码，并验证其有效性

    Args:
        text: 包含代码块的文本

    Returns:
        提取的 Python 代码

    Raises:
        ValueError: 如果提取的代码无效
    """
    # 尝试提取代码块
    code = ""
    if "```python" in text:
        code = text.split("```python")[1].split("```")[0].strip()
    elif "```" in text:
        code = text.split("```")[1].split("```")[0].strip()
    else:
        code = text.strip()

    # 验证提取的代码
    if not code:
        raise ValueError("未能提取到任何代码内容")

    # 处理转义的换行符（AI 可能返回 \n 作为字面字符串）
    # 检查是否包含大量的 \n 字面字符串（而不是真正的换行符）
    if r"\n" in code or "\\n" in code:
        # 计算实际换行符和转义换行符的比例
        actual_newlines = code.count("\n")
        escaped_newlines = code.count(r"\n") + code.count("\\n")

        # 如果转义的换行符远多于实际换行符，说明需要反转义
        if escaped_newlines > actual_newlines * 2:
            print(f"⚠️ 检测到转义的换行符 (\\n)，正在修复...")
            # 替换所有转义的换行符为真正的换行符
            code = code.replace(r"\n", "\n")
            code = code.replace("\\n", "\n")
            print(f"✅ 已将 {escaped_newlines} 个转义换行符替换为真正的换行符")

    # 处理其他常见的转义字符
    if r"\t" in code or "\\t" in code:
        code = code.replace(r"\t", "    ")  # 替换为4个空格
        code = code.replace("\\t", "    ")

    # 检查是否只是注释（超过90%的行都是注释或空行）
    lines = code.split("\n")
    non_comment_lines = 0
    comment_or_empty_lines = 0

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            comment_or_empty_lines += 1
        else:
            non_comment_lines += 1

    total_lines = len(lines)
    if total_lines > 0 and (comment_or_empty_lines / total_lines) > 0.9:
        raise ValueError(
            f"提取的内容主要是注释（{comment_or_empty_lines}/{total_lines}行），"
            "缺少实际的策略代码。请确保 AI 返回完整的策略代码。"
        )

    # 检查是否包含必要的策略类定义
    if "class" not in code:
        raise ValueError("提取的代码中未找到类定义。请确保返回完整的策略类代码。")

    # 检查是否包含 Config 类
    has_config_class = bool(re.search(r"class\s+\w+Config\s*\(", code))
    if not has_config_class:
        raise ValueError(
            "提取的代码中未找到 Config 类定义（如 RSSqueezeConfig）。"
            "请确保返回完整的策略代码。"
        )

    # 检查是否包含 Strategy 类
    has_strategy_class = bool(re.search(r"class\s+\w+Strategy\s*\(", code))
    if not has_strategy_class:
        raise ValueError(
            "提取的代码中未找到 Strategy 类定义（如 RSSqueezeStrategy）。"
            "请确保返回完整的策略代码。"
        )

    # 检查是否包含必要的 import 语句
    if "import" not in code:
        raise ValueError("提取的代码中未找到 import 语句。请确保返回完整的策略代码。")

    # 检查代码长度是否合理（至少应该有一定长度）
    if len(code) < 500:
        raise ValueError(
            f"提取的代码过短（{len(code)}字符），可能不完整。"
            "完整的策略代码通常至少有几千字符。"
        )

    # 检查是否包含 __init__ 方法
    if "def __init__" not in code:
        raise ValueError(
            "提取的代码中未找到 __init__ 方法。请确保返回完整的策略类代码。"
        )

    return code


def validate_strategy_code(code: str) -> tuple[bool, str]:
    """
    验证策略代码的完整性

    Args:
        code: 策略代码

    Returns:
        (is_valid, error_message) 元组
    """
    try:
        # 使用 extract_code 的验证逻辑
        # 这里只是再次验证，不进行提取

        # 检查基本结构
        if not code or len(code.strip()) < 500:
            return False, "代码为空或过短（至少需要500字符）"

        if "class" not in code:
            return False, "缺少类定义"

        if not re.search(r"class\s+\w+Config\s*\(", code):
            return False, "缺少 Config 类"

        if not re.search(r"class\s+\w+Strategy\s*\(", code):
            return False, "缺少 Strategy 类"

        if "import" not in code:
            return False, "缺少 import 语句"

        if "def __init__" not in code:
            return False, "缺少 __init__ 方法"

        # 检查关键方法是否存在
        required_methods = ["on_start", "on_bar"]
        missing_methods = [m for m in required_methods if f"def {m}" not in code]
        if missing_methods:
            return False, f"缺少关键方法: {', '.join(missing_methods)}"

        # 检查是否主要是注释
        lines = code.split("\n")
        non_comment_lines = sum(
            1 for line in lines if line.strip() and not line.strip().startswith("#")
        )

        if len(lines) > 0 and (non_comment_lines / len(lines)) < 0.1:
            return False, "代码主要由注释组成，缺少实际逻辑"

        # 检查是否有转义的换行符（说明代码格式有问题）
        if r"\n" in code or "\\n" in code:
            escaped_count = code.count(r"\n") + code.count("\\n")
            actual_count = code.count("\n")
            if escaped_count > actual_count * 2:
                return False, "代码包含大量转义的换行符（\\n），格式不正确"

        # 深度检查：验证代码的完整性
        completeness_check = check_code_completeness(code)
        if not completeness_check["is_complete"]:
            return False, completeness_check["reason"]

        return True, "验证通过"

    except Exception as e:
        return False, f"验证失败: {str(e)}"


def check_code_completeness(code: str) -> Dict[str, Any]:
    """
    深度检查代码的完整性

    Args:
        code: 策略代码

    Returns:
        包含 is_complete 和 reason 的字典
    """
    # 检查代码长度（完整策略通常至少 3000 字符）
    if len(code) < 3000:
        return {
            "is_complete": False,
            "reason": f"代码过短（{len(code)}字符），完整策略通常至少3000字符。可能缺少方法实现。",
        }

    # 检查是否有方法只包含 pass 或 ... (占位符)
    # 匹配: def method(): \n    pass 或 def method(): \n    ...
    method_pattern = r"def\s+(\w+)\s*\([^)]*\):\s*\n\s+(?:pass|\.\.\.)\s*(?:\n|$)"
    placeholder_methods = re.findall(method_pattern, code, re.MULTILINE)
    if placeholder_methods:
        return {
            "is_complete": False,
            "reason": f"发现占位符方法（只有pass或...）: {', '.join(placeholder_methods[:3])}。请提供完整实现。",
        }

    # 检查关键策略方法是否有实际逻辑
    critical_methods = {
        "on_bar": r"def\s+on_bar\s*\([^)]*\):\s*\n((?:\s+.+\n){5,})",  # 至少5行逻辑
        "on_start": r"def\s+on_start\s*\([^)]*\):\s*\n((?:\s+.+\n){3,})",  # 至少3行逻辑
        "__init__": r"def\s+__init__\s*\([^)]*\):\s*\n((?:\s+.+\n){10,})",  # 至少10行逻辑
    }

    for method, pattern in critical_methods.items():
        if not re.search(pattern, code):
            return {
                "is_complete": False,
                "reason": f"方法 {method} 缺少足够的实现逻辑。请确保包含完整的方法体。",
            }

    # 检查是否包含关键的策略组件
    required_components = {
        "indicators": [
            "BollingerBands",
            "KeltnerChannel",
            "AverageTrueRange",
            "ExponentialMovingAverage",
        ],
        "data_structures": ["deque", "Dict", "Optional"],
        "trading_operations": ["submit_order", "cancel_all_orders"],
    }

    missing_components = []
    for category, components in required_components.items():
        found = [c for c in components if c in code]
        if len(found) < len(components) // 2:  # 至少要有一半的组件
            missing_components.append(category)

    if missing_components:
        return {
            "is_complete": False,
            "reason": f"缺少关键策略组件: {', '.join(missing_components)}。代码可能被过度简化。",
        }

    # 检查是否有足够的方法定义（完整策略通常有10+个方法）
    method_count = len(re.findall(r"def\s+\w+\s*\(", code))
    if method_count < 8:
        return {
            "is_complete": False,
            "reason": f"方法数量过少（{method_count}个）。完整策略通常包含10+个方法。",
        }

    return {"is_complete": True, "reason": "代码完整性检查通过"}


def extract_parameters(code: str) -> Dict[str, str]:
    """从代码中提取参数（简单实现）"""
    params = {}
    for line in code.split("\n"):
        if "=" in line and not line.strip().startswith("#"):
            try:
                parts = line.split("=")
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip().split("#")[0].strip()
                    params[key] = value
            except Exception:
                pass
    return params
