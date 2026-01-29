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
- config_helpers: 配置解析和Universe处理

常用导入：
    from utils import get_ms_timestamp, retry_fetch, check_data_exists
    from utils import parse_timeframe, load_csv_with_time_detection, get_project_root
    from utils import parse_universe_symbols

完整模块导入：
    from utils import time_helpers, network, validation
    from utils import symbol_parser, data_loader, path_helpers, config_helpers

版本：1.0.0
"""

# 版本信息
__version__ = "1.0.0"
__author__ = "NautilusTrader Utils"

# ============================================================================
# 核心工具函数 - 最常用的功能
# ============================================================================

# 时间处理
from .time_helpers import (
    get_ms_timestamp,
)

# 网络请求
from .network import (
    retry_fetch,
)

# 数据验证
from .validation import (
    check_data_exists,
)

# 符号解析
from .symbol_parser import (
    resolve_symbol_and_type,
    parse_timeframe,
)

# 数据加载
from .data_loader import (
    load_ohlcv_csv,
    detect_time_column,
)

# 路径管理
from .path_helpers import (
    get_project_root,
)

# 配置解析
from .config_helpers import (
    parse_universe_symbols,
)

# ============================================================================
# 模块级别导入 - 用于需要完整功能的场景
# ============================================================================

from . import time_helpers
from . import network
from . import validation
from . import symbol_parser
from . import data_loader
from . import path_helpers
from . import config_helpers

# 保持已有的自定义数据类型
from . import custom_data
from . import oi_funding_adapter

# ============================================================================
# 便捷别名和组合功能
# ============================================================================

# 常用组合功能别名
parse_symbol = resolve_symbol_and_type
load_csv = load_ohlcv_csv
check_file = check_data_exists
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
        项目基础目录
    symbols : List[str]
        符号列表
    start_date : str
        开始日期
    end_date : str
        结束日期
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
    
    base_path = Path(base_dir)
    results = {
        "total": len(symbols),
        "exists": 0,
        "missing": 0,
        "warnings": [],
        "details": {}
    }
    
    for symbol in symbols:
        exists, warning = check_data_exists(
            symbol, start_date, end_date, timeframe, exchange, base_path
        )
        
        results["details"][symbol] = {
            "exists": exists,
            "warning": warning
        }
        
        if exists:
            results["exists"] += 1
        else:
            results["missing"] += 1
            
        if warning:
            results["warnings"].append(warning)
    
    return results


# ============================================================================
# 模块信息
# ============================================================================

__all__ = [
    # 版本信息
    "__version__",
    "__author__",
    
    # 核心功能 - 实际导入的函数
    "get_ms_timestamp",
    "retry_fetch",
    "check_data_exists",
    "resolve_symbol_and_type",
    "parse_timeframe",
    "load_ohlcv_csv",
    "detect_time_column",
    "get_project_root",
    "parse_universe_symbols",
    
    # 别名
    "parse_symbol",
    "load_csv",
    "check_file",
    "get_timestamp",
    
    # 便捷组合功能
    "batch_validate_data",
    
    # 模块导入
    "time_helpers",
    "network",
    "validation",
    "symbol_parser",
    "data_loader",
    "path_helpers",
    "config_helpers",
    "custom_data",
    "oi_funding_adapter",
    "oi_funding_fetcher",
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
            "time_helpers", "network", "validation", "symbol_parser",
            "data_loader", "path_helpers", "config_helpers"
        ],
        "core_functions": [
            "get_ms_timestamp", "retry_fetch", "check_data_exists",
            "parse_timeframe", "load_ohlcv_csv", "detect_time_column",
            "get_project_root", "parse_universe_symbols"
        ],
        "python_version": ">=3.12.12",
    }


# 模块加载时检查版本
_check_python_version()
