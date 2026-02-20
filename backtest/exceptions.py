"""
回测引擎异常类定义（已弃用）

此模块已弃用，所有异常类已迁移到 core.exceptions。
为了向后兼容，此模块重新导出核心异常类。

请使用：
    from core.exceptions import BacktestEngineError, DataLoadError

而不是：
    from backtest.exceptions import BacktestEngineError, DataLoadError
"""

# 从核心异常模块导入
from core.exceptions import (
    BacktestEngineError,
    CatalogError,
    CustomDataError,
    DataLoadError,
    InstrumentLoadError,
    ResultProcessingError,
    StrategyConfigError,
    ValidationError,
)

# 导出以保持向后兼容
__all__ = [
    "BacktestEngineError",
    "DataLoadError",
    "InstrumentLoadError",
    "StrategyConfigError",
    "CustomDataError",
    "CatalogError",
    "ResultProcessingError",
    "ValidationError",
]
