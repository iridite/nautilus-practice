"""
数据验证工具模块

提供统一的数据验证、文件检查和配置验证功能，确保数据完整性和配置正确性。

功能包括：
- 文件存在性和大小验证
- 数据格式和内容验证
- 配置参数验证
- 时间范围验证
- 数值范围验证
"""

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple, Union

import pandas as pd


class ValidationError(Exception):
    """验证错误的基类"""
    pass


class FileValidationError(ValidationError):
    """文件验证错误"""
    pass


class DataValidationError(ValidationError):
    """数据验证错误"""
    pass


class ConfigValidationError(ValidationError):
    """配置验证错误"""
    pass


def check_data_exists(
    symbols: List[str],
    start_date: str,
    end_date: str,
    timeframe: str,
    exchange_id: str,
    base_dir: Path,
    filename_template: Union[Callable, None] = None,
    min_size_bytes: int = 10 * 1024
) -> bool:
    """
    检查 OHLCV 数据文件是否存在且有效
    
    Parameters
    ----------
    symbols : List[str]
        交易对符号列表（如 ["BTCUSDT", "ETHUSDT"]）
    start_date : str
        开始日期（YYYY-MM-DD）
    end_date : str
        结束日期（YYYY-MM-DD）
    timeframe : str
        时间周期（如 "1h", "1d"）
    exchange_id : str
        交易所名称
    base_dir : Path
        基础目录路径
    filename_template : callable | None, optional
        文件名模板函数，接受 (exchange_id, symbol, timeframe, start_date, end_date) 参数
        默认使用标准格式：{exchange}-{symbol}-{timeframe}-{start_date}_{end_date}.csv
    min_size_bytes : int, optional
        最小文件大小（字节），默认 10KB
        
    Returns
    -------
    bool
        所有数据文件是否都存在且有效
        
    Examples
    --------
    >>> exists = check_data_exists(["BTCUSDT"], "2024-01-01", "2024-12-31", "1h", "binance", Path("."))
    >>> if not exists:
    ...     print("数据文件不存在或无效")
        
    >>> # 使用自定义文件名模板
    >>> template = lambda ex, sym, tf, start, end: f"{ex}_{sym}_{tf}.csv"
    >>> exists = check_data_exists(["BTCUSDT"], "2024-01-01", "2024-12-31", "1h", "custom", Path("."), template)
    """
    if filename_template is None:
        # 默认文件名模板
        filename_template = lambda ex, sym, tf, start, end: f"{ex.lower()}-{sym}-{tf}-{start}_{end}.csv"
    
    for symbol in symbols:
        safe_symbol = symbol.replace("/", "")
        filename = filename_template(exchange_id, safe_symbol, timeframe, start_date, end_date)
        filepath = base_dir / "data" / "raw" / safe_symbol / filename
        
        if not filepath.exists():
            return False
        
        # 检查文件大小
        try:
            file_size_bytes = filepath.stat().st_size
            if file_size_bytes < min_size_bytes:
                return False
        except OSError:
            # 文件访问错误
            return False
    
    # 所有文件都存在且大小符合要求
    return True


def check_single_data_file(
    symbol_str: str,
    start_date: str,
    end_date: str,
    timeframe: str,
    exchange: str,
    base_dir: Path,
    min_size_kb: int = 10
) -> Tuple[bool, str | None]:
    """
    检查单个 OHLCV 数据文件是否存在且有效（兼容旧接口）
    
    Parameters
    ----------
    symbol_str : str
        交易对符号（如 "BTCUSDT"）
    start_date : str
        开始日期（YYYY-MM-DD）
    end_date : str
        结束日期（YYYY-MM-DD）
    timeframe : str
        时间周期（如 "1h", "1d"）
    exchange : str
        交易所名称
    base_dir : Path
        基础目录路径
    min_size_kb : int, optional
        最小文件大小（KB），默认 10KB
        
    Returns
    -------
    Tuple[bool, str | None]
        (文件是否存在且有效, 警告信息)
        
    Examples
    --------
    >>> exists, warning = check_single_data_file("BTCUSDT", "2024-01-01", "2024-12-31", "1h", "binance", Path("."))
    >>> if not exists:
    ...     print("数据文件不存在")
    >>> elif warning:
    ...     print(f"警告: {warning}")
    """
    safe_symbol = symbol_str.replace("/", "")
    filename = f"{exchange.lower()}-{safe_symbol}-{timeframe}-{start_date}_{end_date}.csv"
    filepath = base_dir / "data" / "raw" / safe_symbol / filename
    
    if not filepath.exists():
        return (False, None)
    
    # 检查文件大小
    file_size_bytes = filepath.stat().st_size
    file_size_kb = file_size_bytes / 1024
    
    if file_size_kb >= min_size_kb:
        return (True, None)
    else:
        warning = f"⚠️ Data file for {symbol_str} ({exchange} {timeframe}) is unusually small ({file_size_kb:.1f}KB)"
        return (True, warning)


def validate_file_exists(
    file_path: Union[str, Path],
    raise_error: bool = False
) -> bool:
    """
    验证文件是否存在
    
    Parameters
    ----------
    file_path : Union[str, Path]
        文件路径
    raise_error : bool, optional
        是否在文件不存在时抛出异常，默认 False
        
    Returns
    -------
    bool
        文件是否存在
        
    Raises
    ------
    FileValidationError
        当文件不存在且 raise_error=True 时
    """
    path = Path(file_path)
    exists = path.exists()
    
    if not exists and raise_error:
        raise FileValidationError(f"File not found: {path}")
    
    return exists


def validate_file_size(
    file_path: Union[str, Path],
    min_size_bytes: int = 0,
    max_size_bytes: int | None = None,
    raise_error: bool = False
) -> Tuple[bool, str | None]:
    """
    验证文件大小是否在合理范围内
    
    Parameters
    ----------
    file_path : Union[str, Path]
        文件路径
    min_size_bytes : int, optional
        最小文件大小（字节），默认 0
    max_size_bytes : int | None, optional
        最大文件大小（字节），默认 None（无限制）
    raise_error : bool, optional
        是否在验证失败时抛出异常，默认 False
        
    Returns
    -------
    Tuple[bool, str | None]
        (是否通过验证, 错误信息)
    """
    path = Path(file_path)
    
    if not path.exists():
        error_msg = f"File not found: {path}"
        if raise_error:
            raise FileValidationError(error_msg)
        return (False, error_msg)
    
    file_size = path.stat().st_size
    
    if file_size < min_size_bytes:
        error_msg = f"File too small: {file_size} bytes < {min_size_bytes} bytes"
        if raise_error:
            raise FileValidationError(error_msg)
        return (False, error_msg)
    
    if max_size_bytes and file_size > max_size_bytes:
        error_msg = f"File too large: {file_size} bytes > {max_size_bytes} bytes"
        if raise_error:
            raise FileValidationError(error_msg)
        return (False, error_msg)
    
    return (True, None)


def validate_csv_structure(
    file_path: Union[str, Path],
    required_columns: List[str] | None = None,
    min_rows: int = 1
) -> Tuple[bool, str | None]:
    """
    验证 CSV 文件结构
    
    Parameters
    ----------
    file_path : Union[str, Path]
        CSV 文件路径
    required_columns : List[str] | None, optional
        必需的列名列表，默认 None
    min_rows : int, optional
        最小行数，默认 1
        
    Returns
    -------
    Tuple[bool, str | None]
        (是否通过验证, 错误信息)
        
    Examples
    --------
    >>> valid, error = validate_csv_structure("data.csv", ["timestamp", "open", "high", "low", "close", "volume"])
    """
    path = Path(file_path)
    
    try:
        # 只读取前几行来检查结构，避免加载大文件
        df = pd.read_csv(path, nrows=min_rows)
    except Exception as e:
        return (False, f"Failed to read CSV file: {e}")
    
    # 检查行数
    if len(df) < min_rows:
        return (False, f"CSV has {len(df)} rows, expected at least {min_rows}")
    
    # 检查必需的列
    if required_columns:
        missing_columns = set(required_columns) - set(df.columns)
        if missing_columns:
            return (False, f"Missing required columns: {missing_columns}")
    
    return (True, None)


def validate_ohlcv_data(
    file_path: Union[str, Path],
    time_column: str = "timestamp"
) -> Tuple[bool, str | None]:
    """
    验证 OHLCV 数据文件格式
    
    Parameters
    ----------
    file_path : Union[str, Path]
        OHLCV 数据文件路径
    time_column : str, optional
        时间列名称，默认 "timestamp"
        
    Returns
    -------
    Tuple[bool, str | None]
        (是否通过验证, 错误信息)
    """
    # 检查基本文件结构
    required_cols = [time_column, "open", "high", "low", "close", "volume"]
    valid, error = validate_csv_structure(file_path, required_cols, min_rows=1)
    
    if not valid:
        return (False, error)
    
    try:
        # 读取少量数据验证数值字段
        df = pd.read_csv(file_path, nrows=10)
        
        # 检查价格字段是否为数值
        price_cols = ["open", "high", "low", "close"]
        for col in price_cols:
            if not pd.api.types.is_numeric_dtype(df[col]):
                return (False, f"Price column '{col}' is not numeric")
        
        # 检查成交量是否为数值
        if not pd.api.types.is_numeric_dtype(df["volume"]):
            return (False, "Volume column is not numeric")
        
        # 检查价格逻辑：high >= low, high >= open, high >= close, low <= open, low <= close
        for _, row in df.iterrows():
            high, low, open_price, close = row["high"], row["low"], row["open"], row["close"]
            
            if high < low:
                return (False, f"Invalid price data: high ({high}) < low ({low})")
            if high < open_price:
                return (False, f"Invalid price data: high ({high}) < open ({open_price})")
            if high < close:
                return (False, f"Invalid price data: high ({high}) < close ({close})")
            if low > open_price:
                return (False, f"Invalid price data: low ({low}) > open ({open_price})")
            if low > close:
                return (False, f"Invalid price data: low ({low}) > close ({close})")
        
        return (True, None)
        
    except Exception as e:
        return (False, f"Failed to validate OHLCV data: {e}")


def validate_json_config(
    file_path: Union[str, Path],
    required_keys: List[str] | None = None
) -> Tuple[bool, str | None]:
    """
    验证 JSON 配置文件
    
    Parameters
    ----------
    file_path : Union[str, Path]
        JSON 文件路径
    required_keys : List[str] | None, optional
        必需的顶级键列表
        
    Returns
    -------
    Tuple[bool, str | None]
        (是否通过验证, 错误信息)
    """
    path = Path(file_path)
    
    if not path.exists():
        return (False, f"JSON file not found: {path}")
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return (False, f"Invalid JSON format: {e}")
    except Exception as e:
        return (False, f"Failed to read JSON file: {e}")
    
    if required_keys:
        missing_keys = set(required_keys) - set(data.keys())
        if missing_keys:
            return (False, f"Missing required keys: {missing_keys}")
    
    return (True, None)


def validate_date_range(
    start_date: str,
    end_date: str,
    date_format: str = "%Y-%m-%d"
) -> Tuple[bool, str | None]:
    """
    验证日期范围的有效性
    
    Parameters
    ----------
    start_date : str
        开始日期字符串
    end_date : str
        结束日期字符串
    date_format : str, optional
        日期格式，默认 "%Y-%m-%d"
        
    Returns
    -------
    Tuple[bool, str | None]
        (是否通过验证, 错误信息)
    """
    try:
        from datetime import datetime
        
        start_dt = datetime.strptime(start_date, date_format)
        end_dt = datetime.strptime(end_date, date_format)
        
        if start_dt > end_dt:
            return (False, f"Start date ({start_date}) is later than end date ({end_date})")
        
        return (True, None)
        
    except ValueError as e:
        return (False, f"Invalid date format: {e}")


def validate_numeric_range(
    value: Union[int, float],
    min_value: Union[int, float] | None = None,
    max_value: Union[int, float] | None = None,
    value_name: str = "value"
) -> Tuple[bool, str | None]:
    """
    验证数值是否在指定范围内
    
    Parameters
    ----------
    value : Union[int, float]
        要验证的数值
    min_value : Union[int, float] | None, optional
        最小值，默认 None
    max_value : Union[int, float] | None, optional
        最大值，默认 None
    value_name : str, optional
        值的名称（用于错误信息），默认 "value"
        
    Returns
    -------
    Tuple[bool, str | None]
        (是否通过验证, 错误信息)
    """
    if min_value is not None and value < min_value:
        return (False, f"{value_name} ({value}) is less than minimum ({min_value})")
    
    if max_value is not None and value > max_value:
        return (False, f"{value_name} ({value}) is greater than maximum ({max_value})")
    
    return (True, None)


def validate_symbol_format(
    symbol: str,
    allowed_patterns: List[str] | None = None
) -> Tuple[bool, str | None]:
    """
    验证交易对符号格式
    
    Parameters
    ----------
    symbol : str
        交易对符号
    allowed_patterns : List[str] | None, optional
        允许的模式列表，支持正则表达式
        
    Returns
    -------
    Tuple[bool, str | None]
        (是否通过验证, 错误信息)
        
    Examples
    --------
    >>> valid, error = validate_symbol_format("BTCUSDT", [r"^[A-Z]+USDT$"])
    >>> valid, error = validate_symbol_format("BTC/USDT:USDT", [r"^[A-Z]+/USDT:USDT$"])
    """
    if not symbol or not isinstance(symbol, str):
        return (False, "Symbol must be a non-empty string")
    
    if allowed_patterns:
        import re
        for pattern in allowed_patterns:
            if re.match(pattern, symbol):
                return (True, None)
        return (False, f"Symbol '{symbol}' does not match any allowed patterns: {allowed_patterns}")
    
    # 基本格式检查
    if len(symbol) < 3:
        return (False, f"Symbol '{symbol}' is too short")
    
    return (True, None)


def validate_timeframe(timeframe: str) -> Tuple[bool, str | None]:
    """
    验证时间周期格式
    
    Parameters
    ----------
    timeframe : str
        时间周期（如 "1m", "5m", "1h", "1d"）
        
    Returns
    -------
    Tuple[bool, str | None]
        (是否通过验证, 错误信息)
    """
    if not timeframe or not isinstance(timeframe, str):
        return (False, "Timeframe must be a non-empty string")
    
    valid_units = ["m", "h", "d", "w", "M"]  # 分钟、小时、天、周、月
    
    if len(timeframe) < 2:
        return (False, f"Invalid timeframe format: '{timeframe}'")
    
    unit = timeframe[-1]
    if unit not in valid_units:
        return (False, f"Invalid timeframe unit: '{unit}'. Allowed: {valid_units}")
    
    try:
        period = int(timeframe[:-1])
        if period <= 0:
            return (False, f"Timeframe period must be positive: {period}")
    except ValueError:
        return (False, f"Invalid timeframe period: '{timeframe[:-1]}'")
    
    return (True, None)


class DataValidator:
    """
    数据验证器类
    
    提供链式验证功能，便于组合多个验证规则
    """
    
    def __init__(self):
        self.errors = []
        self.warnings = []
    
    def add_error(self, error: str) -> 'DataValidator':
        """添加错误信息"""
        self.errors.append(error)
        return self
    
    def add_warning(self, warning: str) -> 'DataValidator':
        """添加警告信息"""
        self.warnings.append(warning)
        return self
    
    def validate_file(
        self,
        file_path: Union[str, Path],
        min_size_kb: int = 1
    ) -> 'DataValidator':
        """验证文件存在性和大小"""
        if not validate_file_exists(file_path):
            self.add_error(f"File not found: {file_path}")
        else:
            valid, error = validate_file_size(file_path, min_size_bytes=min_size_kb * 1024)
            if not valid:
                self.add_warning(error)
        return self
    
    def validate_csv(
        self,
        file_path: Union[str, Path],
        required_columns: List[str] | None = None
    ) -> 'DataValidator':
        """验证 CSV 文件结构"""
        valid, error = validate_csv_structure(file_path, required_columns)
        if not valid:
            self.add_error(error)
        return self
    
    def validate_range(
        self,
        value: Union[int, float],
        min_val: Union[int, float] | None = None,
        max_val: Union[int, float] | None = None,
        name: str = "value"
    ) -> 'DataValidator':
        """验证数值范围"""
        valid, error = validate_numeric_range(value, min_val, max_val, name)
        if not valid:
            self.add_error(error)
        return self
    
    def is_valid(self) -> bool:
        """检查是否所有验证都通过（无错误）"""
        return len(self.errors) == 0
    
    def has_warnings(self) -> bool:
        """检查是否有警告"""
        return len(self.warnings) > 0
    
    def get_summary(self) -> Dict[str, Any]:
        """获取验证结果摘要"""
        return {
            "valid": self.is_valid(),
            "errors": self.errors.copy(),
            "warnings": self.warnings.copy(),
            "error_count": len(self.errors),
            "warning_count": len(self.warnings)
        }