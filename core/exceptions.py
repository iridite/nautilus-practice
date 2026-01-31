"""
配置系统统一异常类

提供清晰的异常层次结构，用于配置加载、验证和处理过程中的错误处理。
"""

from typing import Any, Optional

# ============================================================================
# 基础异常类
# ============================================================================


class ConfigError(Exception):
    """配置系统基础异常"""

    def __init__(self, message: str, cause: Optional[Exception] = None):
        self.message = message
        self.cause = cause
        super().__init__(self.message)


# ============================================================================
# 配置验证异常
# ============================================================================


class ConfigValidationError(ConfigError):
    """配置验证错误"""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Any = None,
        cause: Optional[Exception] = None,
    ):
        self.field = field
        self.value = value
        super().__init__(message, cause)


# ============================================================================
# 配置加载异常
# ============================================================================


class ConfigLoadError(ConfigError):
    """配置加载错误"""

    pass


# ============================================================================
# Universe 配置异常
# ============================================================================


class UniverseParseError(ConfigError):
    """Universe 解析错误"""

    pass


# ============================================================================
# 标的配置异常
# ============================================================================


class InstrumentConfigError(ConfigError):
    """标的配置错误"""

    pass


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    "ConfigError",
    "ConfigValidationError",
    "ConfigLoadError",
    "UniverseParseError",
    "InstrumentConfigError",
]
