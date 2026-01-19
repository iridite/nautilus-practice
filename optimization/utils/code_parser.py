"""
代码解析工具
"""

import re
from typing import Dict


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
            return False, "代码为空或过短"

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

        # 检查是否主要是注释
        lines = code.split("\n")
        non_comment_lines = sum(
            1 for line in lines if line.strip() and not line.strip().startswith("#")
        )

        if len(lines) > 0 and (non_comment_lines / len(lines)) < 0.1:
            return False, "代码主要由注释组成，缺少实际逻辑"

        return True, "验证通过"

    except Exception as e:
        return False, f"验证失败: {str(e)}"


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
            except:
                pass
    return params
