"""
统一异常类模块

提供项目范围内的标准异常类，用于数据管理、配置处理和验证等场景。
"""

from typing import Optional


class DataValidationError(Exception):
    """数据验证异常"""

    def __init__(self, message: str, field_name: Optional[str] = None):
        super().__init__(message)
        self.field_name = field_name

    def __str__(self) -> str:
        if self.field_name:
            return f"{self.args[0]} (field: {self.field_name})"
        return self.args[0]


class DataFetchError(Exception):
    """数据获取异常"""

    def __init__(self, message: str, source: Optional[str] = None, cause: Optional[Exception] = None):
        super().__init__(message)
        self.source = source
        self.cause = cause

    def __str__(self) -> str:
        msg = self.args[0]
        if self.source:
            msg = f"{msg} (source: {self.source})"
        if self.cause:
            msg = f"{msg} (caused by: {self.cause})"
        return msg


class ConfigurationError(Exception):
    """配置异常"""

    def __init__(self, message: str, config_key: Optional[str] = None):
        super().__init__(message)
        self.config_key = config_key

    def __str__(self) -> str:
        if self.config_key:
            return f"{self.args[0]} (config: {self.config_key})"
        return self.args[0]
