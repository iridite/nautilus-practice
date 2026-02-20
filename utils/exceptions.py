"""
统一异常类模块（已弃用）

此模块已弃用，所有异常类已迁移到 core.exceptions。
为了向后兼容，此模块重新导出核心异常类。

请使用：
    from core.exceptions import DataValidationError, DataFetchError, ConfigError

而不是：
    from utils.exceptions import DataValidationError, DataFetchError, ConfigurationError
"""

# 从核心异常模块导入
from core.exceptions import (
    ConfigError,
    ConfigurationError,  # 向后兼容别名
    DataFetchError,
    DataValidationError,
)

# 导出以保持向后兼容
__all__ = [
    "DataValidationError",
    "DataFetchError",
    "ConfigurationError",
    "ConfigError",
]
