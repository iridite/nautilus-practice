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


# ============================================================================
# OI (Open Interest) 数据验证功能
# ============================================================================

def check_oi_data_exists(
    symbols: List[str],
    start_date: str,
    end_date: str,
    period: str,
    exchange_id: str,
    base_dir: Path,
    min_size_bytes: int = 1024
) -> Tuple[bool, List[str]]:
    """
    检查 OI 数据文件是否存在且有效
    
    Parameters
    ----------
    symbols : List[str]
        交易对符号列表（如 ["BTCUSDT", "ETHUSDT"]）
    start_date : str
        开始日期（YYYY-MM-DD）
    end_date : str
        结束日期（YYYY-MM-DD）
    period : str
        时间周期（如 "1h", "4h"）
    exchange_id : str
        交易所名称
    base_dir : Path
        基础目录路径
    min_size_bytes : int, optional
        最小文件大小（字节），默认 1KB
        
    Returns
    -------
    Tuple[bool, List[str]]
        (所有文件是否都存在, 缺失文件列表)
        
    Examples
    --------
    >>> exists, missing = check_oi_data_exists(["BTCUSDT"], "2024-01-01", "2024-12-31", "1h", "binance", Path("."))
    >>> if not exists:
    ...     print(f"Missing OI files: {missing}")
    """
    missing_files = []
    
    for symbol in symbols:
        safe_symbol = symbol.replace("/", "")
        filename = f"{exchange_id.lower()}-{safe_symbol}-oi-{period}-{start_date}_{end_date}.csv"
        filepath = base_dir / "data" / "raw" / safe_symbol / filename
        
        if not filepath.exists():
            missing_files.append(str(filepath))
            continue
        
        # 检查文件大小
        try:
            file_size_bytes = filepath.stat().st_size
            if file_size_bytes < min_size_bytes:
                missing_files.append(str(filepath))
        except OSError:
            missing_files.append(str(filepath))
    
    return len(missing_files) == 0, missing_files


def check_funding_data_exists(
    symbols: List[str],
    start_date: str,
    end_date: str,
    exchange_id: str,
    base_dir: Path,
    min_size_bytes: int = 1024
) -> Tuple[bool, List[str]]:
    """
    检查 Funding Rate 数据文件是否存在且有效
    
    Parameters
    ----------
    symbols : List[str]
        交易对符号列表（如 ["BTCUSDT", "ETHUSDT"]）
    start_date : str
        开始日期（YYYY-MM-DD）
    end_date : str
        结束日期（YYYY-MM-DD）
    exchange_id : str
        交易所名称
    base_dir : Path
        基础目录路径
    min_size_bytes : int, optional
        最小文件大小（字节），默认 1KB
        
    Returns
    -------
    Tuple[bool, List[str]]
        (所有文件是否都存在, 缺失文件列表)
    """
    missing_files = []
    
    for symbol in symbols:
        safe_symbol = symbol.replace("/", "")
        filename = f"{exchange_id.lower()}-{safe_symbol}-funding-{start_date}_{end_date}.csv"
        filepath = base_dir / "data" / "raw" / safe_symbol / filename
        
        if not filepath.exists():
            missing_files.append(str(filepath))
            continue
        
        # 检查文件大小
        try:
            file_size_bytes = filepath.stat().st_size
            if file_size_bytes < min_size_bytes:
                missing_files.append(str(filepath))
        except OSError:
            missing_files.append(str(filepath))
    
    return len(missing_files) == 0, missing_files


def validate_oi_data_structure(
    file_path: Union[str, Path],
    time_column: str = "timestamp"
) -> Tuple[bool, str | None]:
    """
    验证 OI 数据文件结构和内容
    
    Parameters
    ----------
    file_path : Union[str, Path]
        OI 数据文件路径
    time_column : str, optional
        时间列名称，默认 "timestamp"
        
    Returns
    -------
    Tuple[bool, str | None]
        (是否通过验证, 错误信息)
    """
    # 检查基本文件结构
    required_cols = [time_column, "open_interest"]
    valid, error = validate_csv_structure(file_path, required_cols, min_rows=1)
    
    if not valid:
        return (False, error)
    
    try:
        # 读取少量数据验证数值字段
        df = pd.read_csv(file_path, nrows=10)
        
        # 检查 open_interest 是否为数值且非负
        if not pd.api.types.is_numeric_dtype(df["open_interest"]):
            return (False, "open_interest column is not numeric")
        
        if (df["open_interest"] < 0).any():
            return (False, "open_interest contains negative values")
        
        # 检查时间列格式
        if time_column in df.columns:
            try:
                if time_column == "timestamp":
                    # 检查是否为时间戳格式
                    pd.to_datetime(df[time_column], unit='ms')
                else:
                    # 检查是否为日期时间格式
                    pd.to_datetime(df[time_column])
            except Exception:
                return (False, f"Invalid {time_column} format")
        
        return (True, None)
        
    except Exception as e:
        return (False, f"Failed to validate OI data: {e}")


def validate_funding_data_structure(
    file_path: Union[str, Path],
    time_column: str = "timestamp"
) -> Tuple[bool, str | None]:
    """
    验证 Funding Rate 数据文件结构和内容
    
    Parameters
    ----------
    file_path : Union[str, Path]
        Funding Rate 数据文件路径
    time_column : str, optional
        时间列名称，默认 "timestamp"
        
    Returns
    -------
    Tuple[bool, str | None]
        (是否通过验证, 错误信息)
    """
    # 检查基本文件结构
    required_cols = [time_column, "funding_rate"]
    valid, error = validate_csv_structure(file_path, required_cols, min_rows=1)
    
    if not valid:
        return (False, error)
    
    try:
        # 读取少量数据验证数值字段
        df = pd.read_csv(file_path, nrows=10)
        
        # 检查 funding_rate 是否为数值
        if not pd.api.types.is_numeric_dtype(df["funding_rate"]):
            return (False, "funding_rate column is not numeric")
        
        # 检查资金费率是否在合理范围内（通常在 -1% 到 1% 之间）
        if (df["funding_rate"].abs() > 0.01).any():
            return (False, "funding_rate contains unrealistic values (>1%)")
        
        # 检查时间列格式
        if time_column in df.columns:
            try:
                if time_column == "timestamp":
                    pd.to_datetime(df[time_column], unit='ms')
                else:
                    pd.to_datetime(df[time_column])
            except Exception:
                return (False, f"Invalid {time_column} format")
        
        return (True, None)
        
    except Exception as e:
        return (False, f"Failed to validate Funding Rate data: {e}")


def validate_oi_data_completeness(
    file_path: Union[str, Path],
    expected_start: str,
    expected_end: str,
    period: str = "1h",
    time_column: str = "timestamp",
    tolerance_pct: float = 0.05
) -> Tuple[bool, str | None, Dict[str, Any]]:
    """
    验证 OI 数据的时间完整性
    
    Parameters
    ----------
    file_path : Union[str, Path]
        OI 数据文件路径
    expected_start : str
        期望的开始日期（YYYY-MM-DD）
    expected_end : str
        期望的结束日期（YYYY-MM-DD）
    period : str, optional
        时间周期，默认 "1h"
    time_column : str, optional
        时间列名称，默认 "timestamp"
    tolerance_pct : float, optional
        允许的缺失数据百分比，默认 5%
        
    Returns
    -------
    Tuple[bool, str | None, Dict[str, Any]]
        (是否通过验证, 错误信息, 统计信息)
    """
    try:
        df = pd.read_csv(file_path)
        
        if df.empty:
            return (False, "Data file is empty", {})
        
        # 转换时间列
        if time_column == "timestamp":
            df['datetime'] = pd.to_datetime(df[time_column], unit='ms')
        else:
            df['datetime'] = pd.to_datetime(df[time_column])
        
        # 生成期望的时间范围
        from datetime import datetime
        start_dt = datetime.strptime(expected_start, "%Y-%m-%d")
        end_dt = datetime.strptime(expected_end, "%Y-%m-%d")
        
        # 根据周期生成期望的时间序列
        freq_map = {
            "1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
            "1h": "1H", "2h": "2H", "4h": "4H", "6h": "6H", "12h": "12H",
            "1d": "1D"
        }
        freq = freq_map.get(period, "1H")
        
        expected_times = pd.date_range(start=start_dt, end=end_dt, freq=freq)
        actual_times = set(df['datetime'].dt.floor(freq))
        expected_times_set = set(expected_times)
        
        # 计算缺失的时间点
        missing_times = expected_times_set - actual_times
        missing_count = len(missing_times)
        expected_count = len(expected_times)
        missing_pct = missing_count / expected_count if expected_count > 0 else 0
        
        # 检查数据质量
        stats = {
            "total_records": len(df),
            "expected_records": expected_count,
            "missing_records": missing_count,
            "missing_percentage": missing_pct * 100,
            "data_start": df['datetime'].min().strftime("%Y-%m-%d %H:%M:%S"),
            "data_end": df['datetime'].max().strftime("%Y-%m-%d %H:%M:%S"),
            "has_duplicates": df.duplicated(subset=[time_column]).any(),
            "has_null_oi": df["open_interest"].isnull().any()
        }
        
        # 验证是否通过
        if missing_pct > tolerance_pct:
            error_msg = f"Too many missing records: {missing_pct:.1%} > {tolerance_pct:.1%}"
            return (False, error_msg, stats)
        
        if stats["has_duplicates"]:
            return (False, "Data contains duplicate timestamps", stats)
        
        if stats["has_null_oi"]:
            return (False, "Data contains null open_interest values", stats)
        
        return (True, None, stats)
        
    except Exception as e:
        return (False, f"Failed to validate data completeness: {e}", {})


def validate_oi_ohlcv_alignment(
    oi_file_path: Union[str, Path],
    ohlcv_file_path: Union[str, Path],
    oi_time_column: str = "timestamp",
    ohlcv_time_column: str = "timestamp",
    max_time_diff_minutes: int = 60
) -> Tuple[bool, str | None, Dict[str, Any]]:
    """
    验证 OI 数据与 OHLCV 数据的时间对齐
    
    Parameters
    ----------
    oi_file_path : Union[str, Path]
        OI 数据文件路径
    ohlcv_file_path : Union[str, Path]
        OHLCV 数据文件路径
    oi_time_column : str, optional
        OI 数据时间列名称，默认 "timestamp"
    ohlcv_time_column : str, optional
        OHLCV 数据时间列名称，默认 "timestamp"
    max_time_diff_minutes : int, optional
        允许的最大时间差（分钟），默认 60 分钟
        
    Returns
    -------
    Tuple[bool, str | None, Dict[str, Any]]
        (是否通过验证, 错误信息, 对齐统计信息)
    """
    try:
        # 读取数据文件
        oi_df = pd.read_csv(oi_file_path)
        ohlcv_df = pd.read_csv(ohlcv_file_path)
        
        if oi_df.empty or ohlcv_df.empty:
            return (False, "One or both data files are empty", {})
        
        # 转换时间列
        if oi_time_column == "timestamp":
            oi_df['datetime'] = pd.to_datetime(oi_df[oi_time_column], unit='ms')
        else:
            oi_df['datetime'] = pd.to_datetime(oi_df[oi_time_column])
            
        if ohlcv_time_column == "timestamp":
            ohlcv_df['datetime'] = pd.to_datetime(ohlcv_df[ohlcv_time_column], unit='ms')
        else:
            ohlcv_df['datetime'] = pd.to_datetime(ohlcv_df[ohlcv_time_column])
        
        # 计算时间范围重叠
        oi_start, oi_end = oi_df['datetime'].min(), oi_df['datetime'].max()
        ohlcv_start, ohlcv_end = ohlcv_df['datetime'].min(), ohlcv_df['datetime'].max()
        
        overlap_start = max(oi_start, ohlcv_start)
        overlap_end = min(oi_end, ohlcv_end)
        
        if overlap_start >= overlap_end:
            return (False, "No time overlap between OI and OHLCV data", {})
        
        # 在重叠时间范围内进行对齐检查
        oi_overlap = oi_df[(oi_df['datetime'] >= overlap_start) & (oi_df['datetime'] <= overlap_end)]
        ohlcv_overlap = ohlcv_df[(ohlcv_df['datetime'] >= overlap_start) & (ohlcv_df['datetime'] <= overlap_end)]
        
        # 计算可匹配的时间点
        max_diff = pd.Timedelta(minutes=max_time_diff_minutes)
        matched_count = 0
        
        for oi_time in oi_overlap['datetime']:
            time_diffs = (ohlcv_overlap['datetime'] - oi_time).abs()
            if time_diffs.min() <= max_diff:
                matched_count += 1
        
        match_rate = matched_count / len(oi_overlap) if len(oi_overlap) > 0 else 0
        
        stats = {
            "oi_records": len(oi_df),
            "ohlcv_records": len(ohlcv_df),
            "oi_time_range": f"{oi_start} to {oi_end}",
            "ohlcv_time_range": f"{ohlcv_start} to {ohlcv_end}",
            "overlap_range": f"{overlap_start} to {overlap_end}",
            "overlap_oi_records": len(oi_overlap),
            "overlap_ohlcv_records": len(ohlcv_overlap),
            "matched_records": matched_count,
            "match_rate": match_rate * 100
        }
        
        # 验证对齐质量
        if match_rate < 0.8:  # 要求至少 80% 的 OI 数据能找到对应的 OHLCV 数据
            error_msg = f"Poor time alignment: only {match_rate:.1%} of OI data can be matched"
            return (False, error_msg, stats)
        
        return (True, None, stats)
        
    except Exception as e:
        return (False, f"Failed to validate OI-OHLCV alignment: {e}", {})


class OIDataValidator(DataValidator):
    """
    OI 数据验证器类
    
    扩展基础验证器，添加 OI 和 Funding Rate 数据的专门验证功能
    """
    
    def validate_oi_file(
        self,
        file_path: Union[str, Path],
        time_column: str = "timestamp"
    ) -> 'OIDataValidator':
        """验证 OI 数据文件"""
        valid, error = validate_oi_data_structure(file_path, time_column)
        if not valid:
            self.add_error(f"OI data validation failed: {error}")
        return self
    
    def validate_funding_file(
        self,
        file_path: Union[str, Path],
        time_column: str = "timestamp"
    ) -> 'OIDataValidator':
        """验证 Funding Rate 数据文件"""
        valid, error = validate_funding_data_structure(file_path, time_column)
        if not valid:
            self.add_error(f"Funding Rate data validation failed: {error}")
        return self
    
    def validate_oi_completeness(
        self,
        file_path: Union[str, Path],
        expected_start: str,
        expected_end: str,
        period: str = "1h",
        time_column: str = "timestamp",
        tolerance_pct: float = 0.05
    ) -> 'OIDataValidator':
        """验证 OI 数据完整性"""
        valid, error, stats = validate_oi_data_completeness(
            file_path, expected_start, expected_end, period, time_column, tolerance_pct
        )
        if not valid:
            self.add_error(f"OI data completeness check failed: {error}")
        elif stats.get("missing_percentage", 0) > 0:
            self.add_warning(f"OI data has {stats['missing_percentage']:.1f}% missing records")
        return self
    
    def validate_oi_ohlcv_alignment(
        self,
        oi_file_path: Union[str, Path],
        ohlcv_file_path: Union[str, Path],
        oi_time_column: str = "timestamp",
        ohlcv_time_column: str = "timestamp",
        max_time_diff_minutes: int = 60
    ) -> 'OIDataValidator':
        """验证 OI 与 OHLCV 数据对齐"""
        valid, error, stats = validate_oi_ohlcv_alignment(
            oi_file_path, ohlcv_file_path, oi_time_column, ohlcv_time_column, max_time_diff_minutes
        )
        if not valid:
            self.add_error(f"OI-OHLCV alignment check failed: {error}")
        elif stats.get("match_rate", 100) < 95:
            self.add_warning(f"OI-OHLCV alignment rate: {stats['match_rate']:.1f}%")
        return self


# ============================================================================
# Parquet 数据时间范围验证功能
# ============================================================================

def check_parquet_data_coverage(
    symbol: str,
    start_date: str,
    end_date: str,
    timeframe: str,
    exchange: str,
    base_dir: Path,
    strategy_name: str = "RSSqueezeStrategy"
) -> Tuple[bool, str | None, Dict[str, Any]]:
    """
    检查 Parquet 数据的时间覆盖范围
    
    Parameters
    ----------
    symbol : str
        交易对符号（如 "BTCUSDT"）
    start_date : str
        期望的开始日期（YYYY-MM-DD）
    end_date : str
        期望的结束日期（YYYY-MM-DD）
    timeframe : str
        时间周期（如 "1h", "4h"）
    exchange : str
        交易所名称
    base_dir : Path
        基础目录路径
    strategy_name : str, optional
        策略名称，默认 "RSSqueezeStrategy"
        
    Returns
    -------
    Tuple[bool, str | None, Dict[str, Any]]
        (数据覆盖是否充分, 警告信息, 覆盖统计信息)
        
    Examples
    --------
    >>> covered, warning, stats = check_parquet_data_coverage("DOGEUSDT", "2022-01-01", "2025-12-20", "1h", "binance", Path("."))
    >>> if not covered:
    ...     print(f"数据覆盖不足: {warning}")
    >>> print(f"实际覆盖范围: {stats['actual_start']} 到 {stats['actual_end']}")
    """
    from datetime import datetime
    import glob
    
    # 构建 parquet 文件路径
    safe_symbol = symbol.replace("/", "")
    instrument_id = f"{safe_symbol}-PERP.{exchange.upper()}"
    
    # 转换时间周期格式：1h -> 1-HOUR, 4h -> 4-HOUR
    if timeframe.endswith('h'):
        period_num = timeframe[:-1]
        timeframe_formatted = f"{period_num}-HOUR"
    elif timeframe.endswith('m'):
        period_num = timeframe[:-1]
        timeframe_formatted = f"{period_num}-MINUTE"
    elif timeframe.endswith('d'):
        period_num = timeframe[:-1]
        timeframe_formatted = f"{period_num}-DAY"
    else:
        timeframe_formatted = timeframe.upper()
    
    bar_type = f"{instrument_id}-{timeframe_formatted}-LAST-EXTERNAL"
    
    parquet_dir = base_dir / "data" / "parquet" / strategy_name / "data" / "bar" / bar_type
    
    stats = {
        "symbol": symbol,
        "expected_start": start_date,
        "expected_end": end_date,
        "actual_start": None,
        "actual_end": None,
        "coverage_percentage": 0.0,
        "parquet_files": [],
        "total_days_expected": 0,
        "total_days_actual": 0,
        "gap_days": 0
    }
    
    if not parquet_dir.exists():
        return (False, f"Parquet directory not found: {parquet_dir}", stats)
    
    # 查找所有 parquet 文件
    parquet_files = list(parquet_dir.glob("*.parquet"))
    if not parquet_files:
        return (False, f"No parquet files found in {parquet_dir}", stats)
    
    stats["parquet_files"] = [f.name for f in parquet_files]
    
    # 解析文件名获取时间范围
    actual_start = None
    actual_end = None
    
    for file_path in parquet_files:
        filename = file_path.stem  # 去掉 .parquet 扩展名
        try:
            # 解析文件名格式: 2022-01-01T00-00-00-000000000Z_2022-10-19T15-00-00-000000000Z
            if "_" in filename:
                start_str, end_str = filename.split("_")
                
                # 解析开始时间: 2022-01-01T00-00-00-000000000Z
                # 提取日期部分: 2022-01-01
                start_date_part = start_str.split("T")[0]
                file_start = datetime.strptime(start_date_part, "%Y-%m-%d")
                
                # 解析结束时间: 2022-10-19T15-00-00-000000000Z
                # 提取日期部分: 2022-10-19
                end_date_part = end_str.split("T")[0]
                file_end = datetime.strptime(end_date_part, "%Y-%m-%d")
                
                # 更新总体时间范围
                if actual_start is None or file_start < actual_start:
                    actual_start = file_start
                if actual_end is None or file_end > actual_end:
                    actual_end = file_end
                    
        except Exception as e:
            # 如果解析失败，跳过这个文件，但记录错误用于调试
            continue
    
    if actual_start is None or actual_end is None:
        return (False, f"Failed to parse time range from parquet files", stats)
    
    # 更新统计信息
    stats["actual_start"] = actual_start.strftime("%Y-%m-%d")
    stats["actual_end"] = actual_end.strftime("%Y-%m-%d")
    
    # 计算期望的时间范围
    expected_start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    expected_end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    
    # 计算覆盖范围
    overlap_start = max(actual_start, expected_start_dt)
    overlap_end = min(actual_end, expected_end_dt)
    
    if overlap_start >= overlap_end:
        # 没有重叠
        stats["coverage_percentage"] = 0.0
        warning = f"No data overlap: expected {start_date} to {end_date}, actual {stats['actual_start']} to {stats['actual_end']}"
        return (False, warning, stats)
    
    # 计算覆盖百分比
    expected_days = (expected_end_dt - expected_start_dt).days + 1
    overlap_days = (overlap_end - overlap_start).days + 1
    coverage_pct = (overlap_days / expected_days) * 100 if expected_days > 0 else 0
    
    stats["total_days_expected"] = expected_days
    stats["total_days_actual"] = (actual_end - actual_start).days + 1
    stats["coverage_percentage"] = coverage_pct
    stats["gap_days"] = expected_days - overlap_days
    
    # 判断覆盖是否充分（阈值可调整）
    coverage_threshold = 80.0  # 80% 覆盖率阈值
    
    if coverage_pct < coverage_threshold:
        warning = f"Insufficient data coverage: {coverage_pct:.1f}% (expected ≥{coverage_threshold}%). " \
                 f"Missing {stats['gap_days']} days of data. " \
                 f"Actual range: {stats['actual_start']} to {stats['actual_end']}"
        return (False, warning, stats)
    elif coverage_pct < 100.0:
        warning = f"Partial data coverage: {coverage_pct:.1f}%. " \
                 f"Missing {stats['gap_days']} days of data. " \
                 f"Actual range: {stats['actual_start']} to {stats['actual_end']}"
        return (True, warning, stats)
    else:
        return (True, None, stats)


def check_single_data_file_enhanced(
    symbol_str: str,
    start_date: str,
    end_date: str,
    timeframe: str,
    exchange: str,
    base_dir: Path,
    min_size_kb: int = 10,
    check_parquet: bool = True,
    strategy_name: str = "RSSqueezeStrategy"
) -> Tuple[bool, str | None]:
    """
    增强版单个数据文件检查，同时检查 CSV 和 Parquet 数据
    
    优先级逻辑：
    1. CSV存在且有效 -> 使用CSV，正常进行
    2. CSV缺失但Parquet有效 -> 使用Parquet，给出CSV缺失警告
    3. 都不满足 -> 标记为缺失，需要补全
    
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
    check_parquet : bool, optional
        是否检查 parquet 数据，默认 True
    strategy_name : str, optional
        策略名称，默认 "RSSqueezeStrategy"
        
    Returns
    -------
    Tuple[bool, str | None]
        (数据是否充分可以进行回测, 警告信息)
    """
    # 首先检查原始 CSV 数据
    csv_exists, csv_warning = check_single_data_file(
        symbol_str, start_date, end_date, timeframe, exchange, base_dir, min_size_kb
    )
    
    if not check_parquet:
        return (csv_exists, csv_warning)
    
    # 检查 Parquet 数据覆盖范围
    parquet_covered, parquet_warning, parquet_stats = check_parquet_data_coverage(
        symbol_str, start_date, end_date, timeframe, exchange, base_dir, strategy_name
    )
    
    # 智能判断逻辑
    if csv_exists:
        # CSV 存在，优先使用CSV
        if parquet_covered and parquet_warning:
            # CSV和Parquet都有，但Parquet有警告
            combined_warning = csv_warning if csv_warning else None
            if parquet_warning and "coverage" in parquet_warning.lower():
                if combined_warning:
                    combined_warning += f"; Parquet: {parquet_warning}"
                else:
                    combined_warning = f"Parquet: {parquet_warning}"
            return (True, combined_warning)
        else:
            return (True, csv_warning)
    
    elif parquet_covered:
        # CSV 不存在但 Parquet 数据充分，可以继续回测
        coverage_pct = parquet_stats.get("coverage_percentage", 0)
        if coverage_pct >= 80:  # 覆盖率足够
            warning = f"⚠️ CSV data missing, using Parquet data (coverage: {coverage_pct:.1f}%)"
            return (True, warning)  # 返回True允许回测继续
        else:
            warning = f"⚠️ CSV missing, Parquet coverage insufficient ({coverage_pct:.1f}%)"
            return (True, warning)  # 仍然允许继续，但给出警告
    
    else:
        # CSV和Parquet都不满足要求
        warning_parts = [f"No sufficient data for {symbol_str}"]
        if parquet_warning:
            warning_parts.append(f"Parquet: {parquet_warning}")
        return (False, "; ".join(warning_parts))


def analyze_universe_data_coverage(
    universe_symbols: set,
    start_date: str,
    end_date: str,
    timeframe: str,
    exchange: str,
    base_dir: Path,
    strategy_name: str = "RSSqueezeStrategy",
    min_coverage_pct: float = 80.0
) -> Dict[str, Any]:
    """
    分析 Universe 中所有标的的数据覆盖情况
    
    Parameters
    ----------
    universe_symbols : set
        Universe 符号集合
    start_date : str
        开始日期（YYYY-MM-DD）
    end_date : str
        结束日期（YYYY-MM-DD）
    timeframe : str
        时间周期（如 "1h", "4h"）
    exchange : str
        交易所名称
    base_dir : Path
        基础目录路径
    strategy_name : str, optional
        策略名称，默认 "RSSqueezeStrategy"
    min_coverage_pct : float, optional
        最小覆盖百分比阈值，默认 80.0%
        
    Returns
    -------
    Dict[str, Any]
        数据覆盖分析结果
    """
    from datetime import datetime
    
    analysis = {
        "total_symbols": len(universe_symbols),
        "symbols_with_sufficient_data": [],
        "symbols_with_partial_data": [],
        "symbols_with_no_data": [],
        "coverage_stats": {},
        "recommended_timerange": {
            "start": start_date,
            "end": end_date,
            "symbols_count": 0
        },
        "summary": {
            "sufficient_count": 0,
            "partial_count": 0,
            "no_data_count": 0,
            "avg_coverage_pct": 0.0
        }
    }
    
    total_coverage = 0.0
    
    for symbol in sorted(universe_symbols):
        symbol_str = symbol.split(":")[0]  # SOLUSDT:USDT -> SOLUSDT
        
        # 检查数据覆盖
        covered, warning, stats = check_parquet_data_coverage(
            symbol_str, start_date, end_date, timeframe, exchange, base_dir, strategy_name
        )
        
        coverage_pct = stats.get("coverage_percentage", 0.0)
        total_coverage += coverage_pct
        
        symbol_info = {
            "symbol": symbol_str,
            "coverage_percentage": coverage_pct,
            "actual_start": stats.get("actual_start"),
            "actual_end": stats.get("actual_end"),
            "warning": warning,
            "parquet_files": stats.get("parquet_files", [])
        }
        
        analysis["coverage_stats"][symbol_str] = symbol_info
        
        if coverage_pct >= min_coverage_pct:
            analysis["symbols_with_sufficient_data"].append(symbol_str)
            analysis["summary"]["sufficient_count"] += 1
        elif coverage_pct > 0:
            analysis["symbols_with_partial_data"].append(symbol_str)
            analysis["summary"]["partial_count"] += 1
        else:
            analysis["symbols_with_no_data"].append(symbol_str)
            analysis["summary"]["no_data_count"] += 1
    
    # 计算平均覆盖率
    if analysis["total_symbols"] > 0:
        analysis["summary"]["avg_coverage_pct"] = total_coverage / analysis["total_symbols"]
    
    # 推荐最优时间范围（基于数据覆盖最好的时间段）
    if analysis["symbols_with_sufficient_data"]:
        # 找到所有有充分数据的标的的共同时间范围
        common_start = None
        common_end = None
        
        for symbol in analysis["symbols_with_sufficient_data"]:
            stats = analysis["coverage_stats"][symbol]
            if stats["actual_start"] and stats["actual_end"]:
                symbol_start = datetime.strptime(stats["actual_start"], "%Y-%m-%d")
                symbol_end = datetime.strptime(stats["actual_end"], "%Y-%m-%d")
                
                if common_start is None or symbol_start > common_start:
                    common_start = symbol_start
                if common_end is None or symbol_end < common_end:
                    common_end = symbol_end
        
        if common_start and common_end and common_start <= common_end:
            analysis["recommended_timerange"]["start"] = common_start.strftime("%Y-%m-%d")
            analysis["recommended_timerange"]["end"] = common_end.strftime("%Y-%m-%d")
            analysis["recommended_timerange"]["symbols_count"] = len(analysis["symbols_with_sufficient_data"])
    
    return analysis