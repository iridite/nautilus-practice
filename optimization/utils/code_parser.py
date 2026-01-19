"""
代码解析工具
"""

from typing import Dict


def extract_code(text: str) -> str:
    """提取 Markdown 中的代码"""
    if "```python" in text:
        return text.split("```python")[1].split("```")[0].strip()
    elif "```" in text:
        return text.split("```")[1].split("```")[0].strip()
    return text.strip()


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
