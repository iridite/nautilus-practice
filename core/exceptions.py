"""
Nautilus Practice 统一异常体系

提供项目范围内的标准异常类层次结构，用于配置、数据、回测、策略等各个模块。

异常层次结构：
    NautilusPracticeError (基类)
    ├── ConfigError (配置相关)
    │   ├── ConfigValidationError
    │   ├── ConfigLoadError
    │   ├── UniverseParseError
    │   └── InstrumentConfigError
    ├── DataError (数据相关)
    │   ├── DataValidationError
    │   ├── DataLoadError
    │   ├── DataFetchError
    │   ├── TimeColumnError
    │   └── CatalogError
    ├── BacktestError (回测相关)
    │   ├── BacktestEngineError
    │   ├── InstrumentLoadError
    │   ├── StrategyConfigError
    │   ├── CustomDataError
    │   ├── ResultProcessingError
    │   └── ValidationError
    ├── ParsingError (解析相关)
    │   ├── SymbolParsingError
    │   └── TimeframeParsingError
    └── RuntimeError (运行时相关)
        └── PreflightError

Usage:
    from core.exceptions import DataLoadError, ConfigValidationError

    try:
        load_data(path)
    except DataLoadError as e:
        logger.error(f"数据加载失败: {e}")
"""

from typing import Any, Optional, Sequence


# ============================================================================
# 基础异常类
# ============================================================================


class NautilusPracticeError(Exception):
    """
    Nautilus Practice 项目基础异常类

    所有项目异常的根基类，提供统一的异常处理接口和异常链追踪。
    """

    def __init__(self, message: str, cause: Optional[Exception] = None):
        """
        初始化异常

        Parameters
        ----------
        message : str
            异常消息
        cause : Optional[Exception]
            导致此异常的原始异常（异常链）
        """
        self.message = message
        self.cause = cause
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.cause:
            return f"{self.message} (caused by: {self.cause})"
        return self.message


# ============================================================================
# 配置相关异常
# ============================================================================


class ConfigError(NautilusPracticeError):
    """配置系统基础异常"""
    pass


class ConfigValidationError(ConfigError):
    """
    配置验证错误

    在验证配置参数时发生的异常，包括类型错误、值范围错误、必需参数缺失等。
    """

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Any = None,
        cause: Optional[Exception] = None,
    ):
        """
        初始化配置验证错误

        Parameters
        ----------
        message : str
            错误消息
        field : Optional[str]
            出错的字段名
        value : Any
            出错的字段值
        cause : Optional[Exception]
            原始异常
        """
        self.field = field
        self.value = value
        super().__init__(message, cause)

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.field:
            if self.value is not None:
                return f"{base_msg} (field: {self.field}={self.value})"
            return f"{base_msg} (field: {self.field})"
        return base_msg


class ConfigLoadError(ConfigError):
    """
    配置加载错误

    在加载配置文件时发生的异常，包括文件不存在、格式错误、解析失败等。
    """
    pass


class UniverseParseError(ConfigError):
    """
    Universe 解析错误

    在解析交易标的池配置时发生的异常���
    """
    pass


class InstrumentConfigError(ConfigError):
    """
    标的配置错误

    在处理交易标的配置时发生的异常。
    """
    pass


# ============================================================================
# 数据相关异常
# ============================================================================


class DataError(NautilusPracticeError):
    """数据处理基础异常"""
    pass


class DataValidationError(DataError):
    """
    数据验证异常

    在验证数据质量、格式、完整性时发生的异常。
    """

    def __init__(self, message: str, field_name: Optional[str] = None, cause: Optional[Exception] = None):
        """
        初始化数据验证错误

        Parameters
        ----------
        message : str
            错误消息
        field_name : Optional[str]
            出错的字段名
        cause : Optional[Exception]
            原始异常
        """
        super().__init__(message, cause)
        self.field_name = field_name

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.field_name:
            return f"{base_msg} (field: {self.field_name})"
        return base_msg


class DataLoadError(DataError):
    """
    数据加载异常

    在加载OHLCV、OI、Funding Rate等各类市场数据时发生的异常。
    包括文件不存在、格式错误、数据验证失败等。
    """

    def __init__(self, message: str, file_path: Optional[str] = None, cause: Optional[Exception] = None):
        """
        初始化数据加载错误

        Parameters
        ----------
        message : str
            错误消息
        file_path : Optional[str]
            出错的文件路径
        cause : Optional[Exception]
            原始异常
        """
        super().__init__(message, cause)
        self.file_path = file_path

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.file_path:
            return f"{base_msg} (file: {self.file_path})"
        return base_msg


class DataFetchError(DataError):
    """
    数据获取异常

    在从交易所或其他数据源获取数据时发生的异常。
    """

    def __init__(self, message: str, source: Optional[str] = None, cause: Optional[Exception] = None):
        """
        初始化数据获取错误

        Parameters
        ----------
        message : str
            错误消息
        source : Optional[str]
            数据源（如交易所名称）
        cause : Optional[Exception]
            原始异常
        """
        super().__init__(message, cause)
        self.source = source

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.source:
            return f"{base_msg} (source: {self.source})"
        return base_msg


class TimeColumnError(DataLoadError):
    """
    时间列检测错误

    在检测或处理CSV文件的时间列时发生的异常。
    """
    pass


class CatalogError(DataError):
    """
    数据目录异常

    在操作Parquet数据目录时发生的异常。
    包括目录创建失败、数据写入错误、索引损坏等。
    """

    def __init__(self, message: str, catalog_path: Optional[str] = None, cause: Optional[Exception] = None):
        """
        初始化数据目录错误

        Parameters
        ----------
        message : str
            错误消息
        catalog_path : Optional[str]
            目录路径
        cause : Optional[Exception]
            原始异常
        """
        super().__init__(message, cause)
        self.catalog_path = catalog_path

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.catalog_path:
            return f"{base_msg} (catalog: {self.catalog_path})"
        return base_msg


# ============================================================================
# 回测相关异常
# ============================================================================


class BacktestError(NautilusPracticeError):
    """回测系统基础异常"""
    pass


class BacktestEngineError(BacktestError):
    """
    回测引擎异常

    在回测引擎运行过程中发生的通用异常。
    """
    pass


class InstrumentLoadError(BacktestError):
    """
    标的加载异常

    在加载交易标的（Instrument）信息时发生的异常。
    包括标的定义文件不存在、格式错误、标的验证失败等。
    """

    def __init__(self, message: str, instrument_id: Optional[str] = None, cause: Optional[Exception] = None):
        """
        初始化标的加载错误

        Parameters
        ----------
        message : str
            错误消息
        instrument_id : Optional[str]
            标的ID
        cause : Optional[Exception]
            原始异常
        """
        super().__init__(message, cause)
        self.instrument_id = instrument_id

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.instrument_id:
            return f"{base_msg} (instrument: {self.instrument_id})"
        return base_msg


class StrategyConfigError(BacktestError):
    """
    策略配置异常

    在处理策略配置时发生的异常。
    包括参数验证失败、必需参数缺失、参数类型错误等。
    """

    def __init__(self, message: str, strategy_name: Optional[str] = None, cause: Optional[Exception] = None):
        """
        初始化策略配置错误

        Parameters
        ----------
        message : str
            错误消息
        strategy_name : Optional[str]
            策略名称
        cause : Optional[Exception]
            原始异常
        """
        super().__init__(message, cause)
        self.strategy_name = strategy_name

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.strategy_name:
            return f"{base_msg} (strategy: {self.strategy_name})"
        return base_msg


class CustomDataError(BacktestError):
    """
    自定义数据异常

    在处理自定义数据（OI、Funding Rate等）时发生的异常。
    包括数据注入失败、格式不匹配、时间范围错误等。
    """

    def __init__(self, message: str, data_type: Optional[str] = None, cause: Optional[Exception] = None):
        """
        初始化自定义数据错误

        Parameters
        ----------
        message : str
            错误消息
        data_type : Optional[str]
            数据类型（如 "oi", "funding"）
        cause : Optional[Exception]
            原始异常
        """
        super().__init__(message, cause)
        self.data_type = data_type

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.data_type:
            return f"{base_msg} (data_type: {self.data_type})"
        return base_msg


class ResultProcessingError(BacktestError):
    """
    结果处理异常

    在处理回测结果时发生的异常。
    包括JSON序列化失败、文件写入错误、统计计算异常等。
    """
    pass


class ValidationError(BacktestError):
    """
    验证异常

    在验证各种配置、数据、参数时发生的异常。
    提供详细的验证错误信息，便于快速定位问题。
    """

    def __init__(
        self,
        message: str,
        field_name: Optional[str] = None,
        field_value: Optional[str] = None,
        cause: Optional[Exception] = None
    ):
        """
        初始化验证错误

        Parameters
        ----------
        message : str
            错误消息
        field_name : Optional[str]
            字段名
        field_value : Optional[str]
            字段值
        cause : Optional[Exception]
            原始异常
        """
        super().__init__(message, cause)
        self.field_name = field_name
        self.field_value = field_value

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.field_name:
            if self.field_value:
                return f"{base_msg} (field: {self.field_name}={self.field_value})"
            return f"{base_msg} (field: {self.field_name})"
        return base_msg


# ============================================================================
# 解析相关异常
# ============================================================================


class ParsingError(NautilusPracticeError):
    """解析处理基础异常"""
    pass


class SymbolParsingError(ParsingError):
    """
    符号解析错误

    在解析交易对符号时发生的异常。
    """
    pass


class TimeframeParsingError(ParsingError):
    """
    时间周期解析错误

    在解析时间周期格式时发生的异常。
    """
    pass


# ============================================================================
# 运行时相关异常
# ============================================================================


class PreflightError(NautilusPracticeError):
    """
    预检查异常

    在沙盒环境预检查时发现阻塞性问题时抛出。
    """

    def __init__(self, problems: Sequence[str]):
        """
        初始化预检查错误

        Parameters
        ----------
        problems : Sequence[str]
            问题列表
        """
        msg = "Preflight failed with the following problems:\n" + "\n".join(f"- {p}" for p in problems)
        super().__init__(msg)
        self.problems = list(problems)


# ============================================================================
# 向后兼容别名（已弃用，将在未来版本移除）
# ============================================================================

# 为了向后兼容，保留旧的异常名称作为别名
ConfigurationError = ConfigError  # 已弃用，使用 ConfigError


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    # 基础异常
    "NautilusPracticeError",

    # 配置相关
    "ConfigError",
    "ConfigValidationError",
    "ConfigLoadError",
    "UniverseParseError",
    "InstrumentConfigError",

    # 数据相关
    "DataError",
    "DataValidationError",
    "DataLoadError",
    "DataFetchError",
    "TimeColumnError",
    "CatalogError",

    # 回测相关
    "BacktestError",
    "BacktestEngineError",
    "InstrumentLoadError",
    "StrategyConfigError",
    "CustomDataError",
    "ResultProcessingError",
    "ValidationError",

    # 解析相关
    "ParsingError",
    "SymbolParsingError",
    "TimeframeParsingError",

    # 运行时相关
    "PreflightError",

    # 向后兼容（已弃用）
    "ConfigurationError",
]
