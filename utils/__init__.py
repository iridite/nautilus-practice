"""
Utils 工具模块统一接口

提供便捷的工具函数导入接口，消除代码重复，标准化常用功能。
"""

# 版本信息
__version__ = "1.0.0"
__author__ = "NautilusTrader Utils"

# 模块级别导入
from . import (
    custom_data,
    exceptions,
    network,
    oi_funding_adapter,
    path_helpers,
    symbol_parser,
    time_helpers,
    universe,
)

# 数据加载
from .data_management.data_loader import (
    detect_time_column,
    load_ohlcv_csv,
)

# 异常类
from .exceptions import (
    ConfigurationError,
    DataFetchError,
    DataValidationError,
)

# 网络请求
from .network import (
    retry_fetch,
)

# 路径管理
from .path_helpers import (
    get_project_root,
)

# 符号解析
from .symbol_parser import (
    parse_timeframe,
    resolve_symbol_and_type,
)
from .time_helpers import (
    get_ms_timestamp,
)

# Universe 解析
from .universe import (
    extract_universe_symbols,
    load_universe_file,
    load_universe_symbols_from_file,
    parse_universe_symbols,
)

# 模块导出

__all__ = [
    # 版本信息
    "__version__",
    "__author__",

    # 异常类
    "DataValidationError",
    "DataFetchError",
    "ConfigurationError",

    # 核心功能 - 实际导入的函数
    "get_ms_timestamp",
    "retry_fetch",
    "resolve_symbol_and_type",
    "parse_timeframe",
    "load_ohlcv_csv",
    "detect_time_column",
    "get_project_root",
    "load_universe_file",
    "extract_universe_symbols",
    "load_universe_symbols_from_file",
    "parse_universe_symbols",

    # 模块导入
    "time_helpers",
    "network",
    "symbol_parser",
    "path_helpers",
    "universe",
    "custom_data",
    "oi_funding_adapter",
    "exceptions",
]
