"""
Utils 工具模块统一接口

提供便捷的工具函数导入接口，消除代码重复，标准化常用功能。

主要模块：
- time_helpers: 时间处理工具
- network: 网络请求和重试机制
- validation: 数据验证和文件检查
- symbol_parser: 符号格式解析和转换
- data_loader: CSV数据加载和处理
- path_helpers: 路径操作和文件管理

常用导入：
    from utils import get_ms_timestamp, retry_fetch, check_data_exists
    from utils import parse_timeframe, load_csv_with_time_detection, get_project_root
    from utils import parse_universe_symbols

完整模块导入：
    from utils import time_helpers, network
    from utils import symbol_parser, data_loader, path_helpers

版本：1.0.0
"""

# 版本信息
__version__ = "1.0.0"
__author__ = "NautilusTrader Utils"

# ============================================================================
# 核心工具函数 - 最常用的功能
# ============================================================================

# 时间处理
# ============================================================================
# 模块级别导入 - 用于需要完整功能的场景
# ============================================================================
# 保持已有的自定义数据类型
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

# ============================================================================
# 便捷别名和组合功能
# ============================================================================

# 常用组合功能别名
parse_symbol = resolve_symbol_and_type
load_csv = load_ohlcv_csv
get_timestamp = get_ms_timestamp


# ============================================================================
# 工具函数组合 - 高级便捷功能
# ============================================================================

def batch_validate_data(base_dir, symbols, start_date, end_date, timeframe="1h", exchange="binance"):
    """
    批量验证数据文件的便捷函数

    Parameters
    ----------
    base_dir : str | Path
        基础目录路径
    symbols : list
        交易对符号列表
    start_date : str
        开始日期（YYYY-MM-DD）
    end_date : str
        结束日期（YYYY-MM-DD）
    timeframe : str, optional
        时间框架，默认 "1h"
    exchange : str, optional
        交易所，默认 "binance"

    Returns
    -------
    dict
        验证结果统计
    """
    from pathlib import Path

    from .data_file_checker import check_single_data_file

    base_path = Path(base_dir)
    results = {
        "total": len(symbols),
        "exists": 0,
        "missing": 0,
        "warnings": [],
        "details": {}
    }

    for symbol in symbols:
        exists, filepath = check_single_data_file(
            symbol, start_date, end_date, timeframe, exchange, base_path
        )

        results["details"][symbol] = {
            "exists": exists,
            "filepath": filepath
        }

        if exists:
            results["exists"] += 1
        else:
            results["missing"] += 1

    return results


# ============================================================================
# 模块信息
# ============================================================================

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

    # 别名
    "parse_symbol",
    "load_csv",
    "get_timestamp",

    # 便捷组合功能
    "batch_validate_data",

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


# ============================================================================
# 初始化和兼容性检查
# ============================================================================

def _check_python_version():
    """检查Python版本兼容性"""
    import sys
    if sys.version_info < (3, 12):
        import warnings
        warnings.warn(
            "Utils模块推荐使用Python 3.12+以获得最佳性能和类型支持",
            UserWarning
        )


def get_utils_info():
    """获取utils模块信息"""
    return {
        "version": __version__,
        "author": __author__,
        "modules": [
            "time_helpers", "network", "symbol_parser",
            "path_helpers", "data_management"
        ],
        "core_functions": [
            "get_ms_timestamp", "retry_fetch",
            "parse_timeframe", "load_ohlcv_csv", "detect_time_column",
            "get_project_root", "load_universe_file", "parse_universe_symbols"
        ],
        "python_version": ">=3.12.12",
    }


# 模块加载时检查版本
_check_python_version()
