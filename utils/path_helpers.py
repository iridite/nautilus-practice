"""
路径操作工具模块

提供统一的文件和目录路径操作功能，消除项目中重复的路径处理代码。

功能包括：
- 项目路径标准化和获取
- 标准数据目录路径生成
- 安全的目录创建和文件操作
- 文件查找和过滤工具
- 路径验证和规范化
"""

import glob
import os
from pathlib import Path
from typing import List, Union, Tuple, Optional


# 项目路径常量
def get_project_root(start_path: Optional[Union[str, Path]] = None) -> Path:
    """
    获取项目根目录路径
    
    从指定路径向上查找项目根目录（包含 pyproject.toml 的目录）
    
    Parameters
    ----------
    start_path : Optional[Union[str, Path]], optional
        起始查找路径，默认使用调用文件的路径
        
    Returns
    -------
    Path
        项目根目录路径
        
    Examples
    --------
    >>> root = get_project_root()
    >>> print(root)  # /home/user/nautilus-practice
    
    >>> # 从脚本文件获取项目根目录
    >>> root = get_project_root(__file__)
    """
    if start_path is None:
        # 使用调用者的文件路径作为起始点
        import inspect
        frame = inspect.currentframe().f_back
        start_path = Path(frame.f_globals['__file__']).resolve()
    else:
        start_path = Path(start_path).resolve()
    
    # 如果起始路径是文件，取其父目录
    if start_path.is_file():
        start_path = start_path.parent
    
    # 向上查找包含 pyproject.toml 的目录
    current = start_path
    while current != current.parent:  # 直到根目录
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    
    # 如果没找到，返回调用文件的父目录的父目录（适用于大多数情况）
    if start_path.name == "utils":
        return start_path.parent
    elif "utils" in str(start_path):
        # 如果在 utils 子目录中
        parts = start_path.parts
        if "utils" in parts:
            utils_index = parts.index("utils")
            return Path(*parts[:utils_index])
    
    # 默认向上两级
    return start_path.parent.parent


def get_script_project_root(script_file: Union[str, Path]) -> Path:
    """
    从脚本文件路径获取项目根目录
    
    专门用于脚本文件（如 scripts/ 目录下的文件）
    
    Parameters
    ----------
    script_file : Union[str, Path]
        脚本文件路径（通常传入 __file__）
        
    Returns
    -------
    Path
        项目根目录路径
        
    Examples
    --------
    >>> # 在 scripts/prepare_data.py 中使用
    >>> PROJECT_ROOT = get_script_project_root(__file__)
    """
    return Path(script_file).resolve().parent.parent


def get_data_dir(base_dir: Union[str, Path], subdir: str = "raw") -> Path:
    """
    获取标准化的数据目录路径
    
    Parameters
    ----------
    base_dir : Union[str, Path]
        项目基础目录
    subdir : str, optional
        数据子目录名称，默认 "raw"
        可选值："raw", "parquet", "top", "instrument", "models", "record"
        
    Returns
    -------
    Path
        数据目录路径
        
    Examples
    --------
    >>> data_dir = get_data_dir(PROJECT_ROOT, "raw")
    >>> print(data_dir)  # /project/data/raw
    
    >>> parquet_dir = get_data_dir(PROJECT_ROOT, "parquet")
    >>> print(parquet_dir)  # /project/data/parquet
    """
    return Path(base_dir) / "data" / subdir


def get_log_dir(base_dir: Union[str, Path], log_type: str = "backtest") -> Path:
    """
    获取标准化的日志目录路径
    
    Parameters
    ----------
    base_dir : Union[str, Path]
        项目基础目录
    log_type : str, optional
        日志类型，默认 "backtest"
        可选值："backtest", "sandbox", "live"
        
    Returns
    -------
    Path
        日志目录路径
        
    Examples
    --------
    >>> log_dir = get_log_dir(PROJECT_ROOT, "backtest")
    >>> print(log_dir)  # /project/log/backtest
    """
    return Path(base_dir) / "log" / log_type


def get_output_dir(base_dir: Union[str, Path], subdir: str = "") -> Path:
    """
    获取标准化的输出目录路径
    
    Parameters
    ----------
    base_dir : Union[str, Path]
        项目基础目录
    subdir : str, optional
        输出子目录名称，默认为空
        
    Returns
    -------
    Path
        输出目录路径
        
    Examples
    --------
    >>> output_dir = get_output_dir(PROJECT_ROOT)
    >>> print(output_dir)  # /project/output
    
    >>> strategy_output = get_output_dir(PROJECT_ROOT, "oi_divergence")
    >>> print(strategy_output)  # /project/output/oi_divergence
    """
    if subdir:
        return Path(base_dir) / "output" / subdir
    return Path(base_dir) / "output"


def ensure_directory(path: Union[str, Path]) -> Path:
    """
    确保目录存在，如不存在则创建
    
    Parameters
    ----------
    path : Union[str, Path]
        目录路径
        
    Returns
    -------
    Path
        目录路径对象
        
    Examples
    --------
    >>> data_dir = ensure_directory("/project/data/custom")
    >>> # 目录将被创建（如果不存在）
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_parent_directory(file_path: Union[str, Path]) -> Path:
    """
    确保文件的父目录存在
    
    Parameters
    ----------
    file_path : Union[str, Path]
        文件路径
        
    Returns
    -------
    Path
        文件路径对象
        
    Examples
    --------
    >>> file_path = ensure_parent_directory("/project/data/new/file.csv")
    >>> # /project/data/new/ 目录将被创建
    """
    file_path = Path(file_path)
    if not file_path.parent.exists():
        file_path.parent.mkdir(parents=True, exist_ok=True)
    return file_path


def safe_file_exists(file_path: Union[str, Path], min_size_bytes: int = 0) -> bool:
    """
    安全检查文件是否存在且满足最小大小要求
    
    Parameters
    ----------
    file_path : Union[str, Path]
        文件路径
    min_size_bytes : int, optional
        最小文件大小（字节），默认 0
        
    Returns
    -------
    bool
        文件是否存在且满足大小要求
        
    Examples
    --------
    >>> exists = safe_file_exists("data.csv", min_size_bytes=1024)
    >>> if exists:
    ...     print("File is valid")
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return False
        if path.stat().st_size < min_size_bytes:
            return False
        return True
    except (OSError, IOError):
        return False


def get_file_size_mb(file_path: Union[str, Path]) -> float:
    """
    获取文件大小（MB）
    
    Parameters
    ----------
    file_path : Union[str, Path]
        文件路径
        
    Returns
    -------
    float
        文件大小（MB），文件不存在返回 0.0
        
    Examples
    --------
    >>> size = get_file_size_mb("large_data.csv")
    >>> print(f"File size: {size:.2f} MB")
    """
    try:
        path = Path(file_path)
        if path.exists():
            return path.stat().st_size / (1024 * 1024)
        return 0.0
    except (OSError, IOError):
        return 0.0


def find_symbol_data_files(
    data_dir: Union[str, Path],
    symbol: str,
    pattern: str = "*.csv",
    exchange: str | None = None
) -> List[Path]:
    """
    查找指定符号的数据文件
    
    Parameters
    ----------
    data_dir : Union[str, Path]
        数据根目录
    symbol : str
        交易对符号（如 "BTCUSDT"）
    pattern : str, optional
        文件匹配模式，默认 "*.csv"
    exchange : str | None, optional
        交易所名称过滤，默认 None
        
    Returns
    -------
    List[Path]
        匹配的文件路径列表
        
    Examples
    --------
    >>> files = find_symbol_data_files(data_dir, "BTCUSDT", "*-1h-*.csv")
    >>> oi_files = find_symbol_data_files(data_dir, "BTCUSDT", "*-oi-*.csv", "binance")
    """
    safe_symbol = symbol.replace("/", "")
    symbol_dir = Path(data_dir) / safe_symbol
    
    if not symbol_dir.exists():
        return []
    
    files = list(symbol_dir.glob(pattern))
    
    # 按交易所过滤
    if exchange:
        exchange_lower = exchange.lower()
        files = [f for f in files if f.name.lower().startswith(f"{exchange_lower}-")]
    
    return sorted(files)


def find_files_by_pattern(
    directory: Union[str, Path],
    pattern: str,
    recursive: bool = False
) -> List[Path]:
    """
    按模式查找文件
    
    Parameters
    ----------
    directory : Union[str, Path]
        搜索目录
    pattern : str
        文件匹配模式
    recursive : bool, optional
        是否递归搜索，默认 False
        
    Returns
    -------
    List[Path]
        匹配的文件路径列表
        
    Examples
    --------
    >>> csv_files = find_files_by_pattern("/data", "*.csv")
    >>> all_json = find_files_by_pattern("/config", "**/*.json", recursive=True)
    """
    directory = Path(directory)
    
    if not directory.exists():
        return []
    
    if recursive:
        pattern = "**/" + pattern
        files = list(directory.glob(pattern))
    else:
        files = list(directory.glob(pattern))
    
    return sorted(files)


def get_instrument_file_path(
    base_dir: Union[str, Path],
    symbol: str,
    venue: str = "BINANCE"
) -> Path:
    """
    获取标的定义文件路径
    
    Parameters
    ----------
    base_dir : Union[str, Path]
        项目基础目录
    symbol : str
        符号名称
    venue : str, optional
        交易所名称，默认 "BINANCE"
        
    Returns
    -------
    Path
        标的定义文件路径
        
    Examples
    --------
    >>> inst_path = get_instrument_file_path(PROJECT_ROOT, "BTCUSDT-PERP")
    >>> print(inst_path)  # /project/data/instrument/BINANCE/BTCUSDT-PERP.json
    """
    return get_data_dir(base_dir, "instrument") / venue / f"{symbol}.json"


def generate_data_file_path(
    base_dir: Union[str, Path],
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    exchange: str = "binance",
    data_type: str = "ohlcv"
) -> Path:
    """
    生成标准化的数据文件路径
    
    Parameters
    ----------
    base_dir : Union[str, Path]
        项目基础目录
    symbol : str
        交易对符号
    timeframe : str
        时间周期
    start_date : str
        开始日期
    end_date : str
        结束日期
    exchange : str, optional
        交易所名称，默认 "binance"
    data_type : str, optional
        数据类型，默认 "ohlcv"
        可选值："ohlcv", "oi", "funding"
        
    Returns
    -------
    Path
        数据文件路径
        
    Examples
    --------
    >>> path = generate_data_file_path(
    ...     PROJECT_ROOT, "BTCUSDT", "1h", "2024-01-01", "2024-12-31"
    ... )
    >>> # /project/data/raw/BTCUSDT/binance-BTCUSDT-1h-2024-01-01_2024-12-31.csv
    
    >>> oi_path = generate_data_file_path(
    ...     PROJECT_ROOT, "BTCUSDT", "1h", "2024-01-01", "2024-12-31", 
    ...     data_type="oi"
    ... )
    >>> # /project/data/raw/BTCUSDT/binance-BTCUSDT-oi-1h-2024-01-01_2024-12-31.csv
    """
    safe_symbol = symbol.replace("/", "")
    
    if data_type == "ohlcv":
        filename = f"{exchange.lower()}-{safe_symbol}-{timeframe}-{start_date}_{end_date}.csv"
    elif data_type == "oi":
        filename = f"{exchange.lower()}-{safe_symbol}-oi-{timeframe}-{start_date}_{end_date}.csv"
    elif data_type == "funding":
        filename = f"{exchange.lower()}-{safe_symbol}-funding-{start_date}_{end_date}.csv"
    else:
        filename = f"{exchange.lower()}-{safe_symbol}-{data_type}-{start_date}_{end_date}.csv"
    
    return get_data_dir(base_dir, "raw") / safe_symbol / filename


def clean_symbol_for_path(symbol: str) -> str:
    """
    清理符号名称，使其适合作为文件/目录名
    
    Parameters
    ----------
    symbol : str
        原始符号名称
        
    Returns
    -------
    str
        清理后的符号名称
        
    Examples
    --------
    >>> clean_name = clean_symbol_for_path("BTC/USDT:USDT")
    >>> print(clean_name)  # "BTCUSDT"
    """
    return symbol.replace("/", "").replace(":", "")


def normalize_path(path: Union[str, Path]) -> Path:
    """
    规范化路径（解析相对路径、符号链接等）
    
    Parameters
    ----------
    path : Union[str, Path]
        输入路径
        
    Returns
    -------
    Path
        规范化后的路径对象
        
    Examples
    --------
    >>> norm_path = normalize_path("../data/./raw/../raw/BTCUSDT")
    >>> print(norm_path)  # 绝对路径形式
    """
    return Path(path).resolve()


def is_relative_to_project(
    path: Union[str, Path], 
    project_root: Union[str, Path] | None = None
) -> bool:
    """
    检查路径是否在项目目录内
    
    Parameters
    ----------
    path : Union[str, Path]
        要检查的路径
    project_root : Union[str, Path] | None, optional
        项目根目录，默认自动检测
        
    Returns
    -------
    bool
        路径是否在项目内
        
    Examples
    --------
    >>> is_inside = is_relative_to_project("/project/data/raw")
    >>> print(is_inside)  # True
    """
    if project_root is None:
        project_root = get_project_root()
    
    try:
        path = normalize_path(path)
        project_root = normalize_path(project_root)
        return path.is_relative_to(project_root)
    except (ValueError, OSError):
        return False


def get_relative_path(
    path: Union[str, Path], 
    base_path: Union[str, Path] | None = None
) -> Path:
    """
    获取相对于基础路径的相对路径
    
    Parameters
    ----------
    path : Union[str, Path]
        目标路径
    base_path : Union[str, Path] | None, optional
        基础路径，默认使用项目根目录
        
    Returns
    -------
    Path
        相对路径
        
    Examples
    --------
    >>> rel_path = get_relative_path("/project/data/raw/BTCUSDT/file.csv")
    >>> print(rel_path)  # data/raw/BTCUSDT/file.csv
    """
    if base_path is None:
        base_path = get_project_root()
    
    path = normalize_path(path)
    base_path = normalize_path(base_path)
    
    try:
        return path.relative_to(base_path)
    except ValueError:
        return path


class PathManager:
    """
    路径管理器类
    
    提供项目路径的统一管理和访问
    """
    
    def __init__(self, project_root: Union[str, Path] | None = None):
        """
        初始化路径管理器
        
        Parameters
        ----------
        project_root : Union[str, Path] | None, optional
            项目根目录，默认自动检测
        """
        self._project_root = normalize_path(project_root) if project_root else get_project_root()
    
    @property
    def project_root(self) -> Path:
        """项目根目录"""
        return self._project_root
    
    @property
    def data_root(self) -> Path:
        """数据根目录"""
        return self._project_root / "data"
    
    @property
    def raw_data_dir(self) -> Path:
        """原始数据目录"""
        return self.data_root / "raw"
    
    @property
    def parquet_data_dir(self) -> Path:
        """Parquet数据目录"""
        return self.data_root / "parquet"
    
    @property
    def instrument_dir(self) -> Path:
        """标的定义目录"""
        return self.data_root / "instrument"
    
    @property
    def log_root(self) -> Path:
        """日志根目录"""
        return self._project_root / "log"
    
    @property
    def output_root(self) -> Path:
        """输出根目录"""
        return self._project_root / "output"
    
    def get_symbol_data_dir(self, symbol: str) -> Path:
        """获取指定符号的数据目录"""
        return self.raw_data_dir / clean_symbol_for_path(symbol)
    
    def get_strategy_output_dir(self, strategy_name: str) -> Path:
        """获取指定策略的输出目录"""
        return self.output_root / strategy_name
    
    def get_backtest_log_dir(self, engine_type: str = "high_level") -> Path:
        """获取回测日志目录"""
        return self.log_root / "backtest" / engine_type
    
    def ensure_all_directories(self) -> None:
        """确保所有标准目录存在"""
        directories = [
            self.data_root,
            self.raw_data_dir,
            self.parquet_data_dir,
            self.instrument_dir,
            self.log_root,
            self.output_root,
        ]
        
        for directory in directories:
            ensure_directory(directory)


# 便捷的全局路径管理器实例
_global_path_manager: PathManager | None = None


def get_path_manager() -> PathManager:
    """
    获取全局路径管理器实例
    
    Returns
    -------
    PathManager
        路径管理器实例
    """
    global _global_path_manager
    if _global_path_manager is None:
        _global_path_manager = PathManager()
    return _global_path_manager