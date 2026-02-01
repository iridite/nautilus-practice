"""
回测引擎异常类定义

统一定义回测过程中可能出现的各种异常，提供清晰的错误信息和错误分类。
支持异常链追踪，便于调试和错误定位。

Usage:
    from backtest.exceptions import BacktestEngineError, DataLoadError

    try:
        # some backtest operation
        pass
    except DataLoadError as e:
        logger.error(f"数据加载失败: {e}")
    except BacktestEngineError as e:
        logger.error(f"回测引擎错误: {e}")
"""

from typing import Optional


class BacktestEngineError(Exception):
    """
    回测引擎基础异常类

    所有回测引擎相关异常的基类，提供统一的异常处理接口。
    """

    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(message)
        self.message = message
        self.cause = cause

    def __str__(self) -> str:
        if self.cause:
            return f"{self.message} (caused by: {self.cause})"
        return self.message


class DataLoadError(BacktestEngineError):
    """
    数据加载异常

    在加载OHLCV、OI、Funding Rate等各类市场数据时发生的异常。
    包括文件不存在、格式错误、数据验证失败等。
    """

    def __init__(self, message: str, file_path: Optional[str] = None, cause: Optional[Exception] = None):
        super().__init__(message, cause)
        self.file_path = file_path

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.file_path:
            return f"{base_msg} (file: {self.file_path})"
        return base_msg


class InstrumentLoadError(BacktestEngineError):
    """
    标的加载异常

    在加载交易标的（Instrument）信息时发生的异常。
    包括标的定义文件不存在、格式错误、标的验证失败等。
    """

    def __init__(self, message: str, instrument_id: Optional[str] = None, cause: Optional[Exception] = None):
        super().__init__(message, cause)
        self.instrument_id = instrument_id

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.instrument_id:
            return f"{base_msg} (instrument: {self.instrument_id})"
        return base_msg


class StrategyConfigError(BacktestEngineError):
    """
    策略配置异常

    在处理策略配置时发生的异常。
    包括参数验证失败、必需参数缺失、参数类型错误等。
    """

    def __init__(self, message: str, strategy_name: Optional[str] = None, cause: Optional[Exception] = None):
        super().__init__(message, cause)
        self.strategy_name = strategy_name

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.strategy_name:
            return f"{base_msg} (strategy: {self.strategy_name})"
        return base_msg


class CustomDataError(BacktestEngineError):
    """
    自定义数据异常

    在处理自定义数据（OI、Funding Rate等）时发生的异常。
    包括数据注入失败、格式不匹配、时间范围错误等。
    """

    def __init__(self, message: str, data_type: Optional[str] = None, cause: Optional[Exception] = None):
        super().__init__(message, cause)
        self.data_type = data_type

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.data_type:
            return f"{base_msg} (data_type: {self.data_type})"
        return base_msg


class CatalogError(BacktestEngineError):
    """
    数据目录异常

    在操作Parquet数据目录时发生的异常。
    包括目录创建失败、数据写入错误、索引损坏等。
    """

    def __init__(self, message: str, catalog_path: Optional[str] = None, cause: Optional[Exception] = None):
        super().__init__(message, cause)
        self.catalog_path = catalog_path

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.catalog_path:
            return f"{base_msg} (catalog: {self.catalog_path})"
        return base_msg


class ResultProcessingError(BacktestEngineError):
    """
    结果处理异常

    在处理回测结果时发生的异常。
    包括JSON序列化失败、文件写入错误、统计计算异常等。
    """
    pass


class ValidationError(BacktestEngineError):
    """
    验证异常

    在验证各种配置、数据、参数时发生的异常。
    提供详细的验证错误信息，便于快速定位问题。
    """

    def __init__(self, message: str, field_name: Optional[str] = None, field_value: Optional[str] = None):
        super().__init__(message)
        self.field_name = field_name
        self.field_value = field_value

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.field_name:
            if self.field_value:
                return f"{base_msg} (field: {self.field_name}={self.field_value})"
            else:
                return f"{base_msg} (field: {self.field_name})"
        return base_msg