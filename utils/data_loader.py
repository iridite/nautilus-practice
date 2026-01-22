"""
数据加载工具模块

提供统一的CSV数据加载、预处理和验证功能，支持多种数据格式和自动时间列检测。

功能包括：
- 智能时间列检测（datetime/timestamp）
- CSV数据加载和预处理
- 时间范围过滤和数据验证
- 自定义数据类型加载（OI, Funding Rate）
- NautilusTrader 数据格式转换
- 数据清洗和去重
"""

from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

import pandas as pd
from nautilus_trader.core.nautilus_pyo3 import millis_to_nanos
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.loaders import CSVBarDataLoader
from nautilus_trader.persistence.wranglers import BarDataWrangler

from utils.custom_data import FundingRateData, OpenInterestData


class DataLoadError(Exception):
    """数据加载错误"""
    pass


class TimeColumnError(DataLoadError):
    """时间列检测错误"""
    pass


def detect_time_column(csv_path: Union[str, Path], sample_rows: int = 5) -> str:
    """
    智能检测CSV文件的时间列名称
    
    Parameters
    ----------
    csv_path : Union[str, Path]
        CSV文件路径
    sample_rows : int, optional
        用于检测的样本行数，默认 5
        
    Returns
    -------
    str
        检测到的时间列名称
        
    Raises
    ------
    TimeColumnError
        当无法检测到有效的时间列时
        
    Examples
    --------
    >>> time_col = detect_time_column("data.csv")
    >>> print(time_col)  # "datetime" 或 "timestamp"
    """
    try:
        sample_df = pd.read_csv(csv_path, nrows=sample_rows)
        
        # 优先级：datetime > timestamp > 其他可能的时间列名
        time_candidates = ["datetime", "timestamp", "time", "date", "ts"]
        
        for candidate in time_candidates:
            if candidate in sample_df.columns:
                # 验证是否为有效的时间格式
                if _validate_time_column(sample_df[candidate]):
                    return candidate
        
        # 如果没有标准时间列名，尝试检测可能的时间列
        for col in sample_df.columns:
            if _looks_like_time_column(sample_df[col]):
                return col
        
        # 抛出详细错误信息
        available_cols = list(sample_df.columns)
        raise TimeColumnError(
            f"No valid time column found in {csv_path}. "
            f"Expected one of {time_candidates}, got: {available_cols}"
        )
        
    except pd.errors.EmptyDataError:
        raise TimeColumnError(f"CSV file is empty: {csv_path}")
    except Exception as e:
        raise TimeColumnError(f"Error detecting time column in {csv_path}: {e}")


def _validate_time_column(series: pd.Series) -> bool:
    """验证序列是否为有效的时间列"""
    if len(series) == 0:
        return False
    
    try:
        # 尝试解析第一个非空值
        sample_value = series.dropna().iloc[0] if not series.dropna().empty else None
        if sample_value is None:
            return False
        
        # 检查是否为时间戳（数值）或日期字符串
        if isinstance(sample_value, (int, float)):
            # 可能是时间戳
            return True
        elif isinstance(sample_value, str):
            # 尝试解析为日期
            pd.to_datetime(sample_value)
            return True
        else:
            return False
    except:
        return False


def _looks_like_time_column(series: pd.Series) -> bool:
    """检查序列是否看起来像时间列"""
    if len(series) == 0:
        return False
    
    # 检查列名是否包含时间相关关键词
    col_name = series.name.lower() if series.name else ""
    time_keywords = ["time", "date", "ts", "stamp"]
    
    return any(keyword in col_name for keyword in time_keywords)


def load_ohlcv_csv(
    csv_path: Union[str, Path],
    time_column: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    validate_data: bool = True
) -> pd.DataFrame:
    """
    加载OHLCV CSV数据，支持自动时间列检测和时间范围过滤
    
    Parameters
    ----------
    csv_path : Union[str, Path]
        CSV文件路径
    time_column : str | None, optional
        指定时间列名称，None表示自动检测
    start_date : str | None, optional
        开始日期（YYYY-MM-DD格式）
    end_date : str | None, optional
        结束日期（YYYY-MM-DD格式）
    validate_data : bool, optional
        是否验证数据完整性，默认 True
        
    Returns
    -------
    pd.DataFrame
        加载并处理后的OHLCV数据，以时间为索引
        
    Raises
    ------
    DataLoadError
        当数据加载或处理失败时
    """
    csv_path = Path(csv_path)
    
    if not csv_path.exists():
        raise DataLoadError(f"CSV file not found: {csv_path}")
    
    try:
        # 自动检测时间列
        if time_column is None:
            time_column = detect_time_column(csv_path)
        
        # 定义必需的列
        required_columns = [time_column, "open", "high", "low", "close", "volume"]
        
        # 使用 NautilusTrader 的高效加载器
        df = CSVBarDataLoader.load(
            file_path=csv_path,
            index_col=time_column,
            usecols=required_columns,
            parse_dates=True,
        )
        
        # 确保索引已排序
        df.sort_index(inplace=True)
        
        # 时间范围过滤
        if start_date:
            start_ts = pd.Timestamp(start_date)
            if start_ts.tz is not None:
                start_ts = start_ts.tz_localize(None)
            df = df[df.index >= start_ts]
        
        if end_date:
            end_ts = pd.Timestamp(end_date)
            if end_ts.tz is not None:
                end_ts = end_ts.tz_localize(None)
            df = df[df.index <= end_ts]
        
        # 验证数据
        if validate_data:
            _validate_ohlcv_data(df)
        
        if len(df) == 0:
            raise DataLoadError(f"No data available in specified range for {csv_path}")
        
        return df
        
    except Exception as e:
        if isinstance(e, DataLoadError):
            raise
        raise DataLoadError(f"Error loading OHLCV data from {csv_path}: {e}")


def _validate_ohlcv_data(df: pd.DataFrame) -> None:
    """验证OHLCV数据完整性"""
    required_cols = ["open", "high", "low", "close", "volume"]
    
    # 检查必需列
    missing_cols = set(required_cols) - set(df.columns)
    if missing_cols:
        raise DataLoadError(f"Missing required columns: {missing_cols}")
    
    # 检查数值类型
    for col in required_cols:
        if not pd.api.types.is_numeric_dtype(df[col]):
            raise DataLoadError(f"Column '{col}' must be numeric")
    
    # 检查价格逻辑
    invalid_rows = (
        (df["high"] < df["low"]) |
        (df["high"] < df["open"]) |
        (df["high"] < df["close"]) |
        (df["low"] > df["open"]) |
        (df["low"] > df["close"])
    )
    
    if invalid_rows.any():
        first_invalid = df[invalid_rows].index[0]
        raise DataLoadError(f"Invalid OHLC data detected at {first_invalid}")


def create_nautilus_bars(
    df: pd.DataFrame,
    bar_type: Any,
    instrument: Any
) -> List[Bar]:
    """
    将pandas DataFrame转换为NautilusTrader Bar对象列表
    
    Parameters
    ----------
    df : pd.DataFrame
        OHLCV数据框（以时间为索引）
    bar_type : BarType
        NautilusTrader BarType对象
    instrument : Instrument
        NautilusTrader Instrument对象
        
    Returns
    -------
    List[Bar]
        NautilusTrader Bar对象列表
    """
    try:
        wrangler = BarDataWrangler(bar_type, instrument)
        bars = wrangler.process(df)
        return bars
    except Exception as e:
        raise DataLoadError(f"Error creating Nautilus bars: {e}")


def load_custom_csv_data(
    csv_path: Union[str, Path],
    data_type: str,
    instrument_id: InstrumentId,
    time_column: str | None = None
) -> List[Union[OpenInterestData, FundingRateData]]:
    """
    加载自定义CSV数据（OI或Funding Rate）
    
    Parameters
    ----------
    csv_path : Union[str, Path]
        CSV文件路径
    data_type : str
        数据类型（"oi" 或 "funding"）
    instrument_id : InstrumentId
        NautilusTrader 合约标识符
    time_column : str | None, optional
        时间列名称，None表示自动检测
        
    Returns
    -------
    List[Union[OpenInterestData, FundingRateData]]
        自定义数据对象列表
    """
    csv_path = Path(csv_path)
    
    if not csv_path.exists():
        raise DataLoadError(f"Custom data file not found: {csv_path}")
    
    try:
        # 自动检测时间列
        if time_column is None:
            time_column = detect_time_column(csv_path)
        
        df = pd.read_csv(csv_path)
        
        if time_column not in df.columns:
            raise DataLoadError(f"Time column '{time_column}' not found in {csv_path}")
        
        data_list = []
        
        if data_type.lower() == "oi":
            if "open_interest" not in df.columns:
                raise DataLoadError(f"'open_interest' column not found in {csv_path}")
            
            for _, row in df.iterrows():
                ts_ms = int(row[time_column])
                ts_event = millis_to_nanos(ts_ms)
                ts_init = ts_event
                
                oi_data = OpenInterestData(
                    instrument_id=instrument_id,
                    open_interest=Decimal(str(row["open_interest"])),
                    ts_event=ts_event,
                    ts_init=ts_init,
                )
                data_list.append(oi_data)
                
        elif data_type.lower() == "funding":
            if "funding_rate" not in df.columns:
                raise DataLoadError(f"'funding_rate' column not found in {csv_path}")
            
            for _, row in df.iterrows():
                ts_ms = int(row[time_column])
                ts_event = millis_to_nanos(ts_ms)
                ts_init = ts_event
                
                # 可选的下次资金费率时间
                next_funding_time = None
                if "next_funding_time" in df.columns and pd.notna(row["next_funding_time"]):
                    next_funding_time = millis_to_nanos(int(row["next_funding_time"]))
                
                funding_data = FundingRateData(
                    instrument_id=instrument_id,
                    funding_rate=Decimal(str(row["funding_rate"])),
                    next_funding_time=next_funding_time,
                    ts_event=ts_event,
                    ts_init=ts_init,
                )
                data_list.append(funding_data)
        else:
            raise DataLoadError(f"Unsupported data type: {data_type}")
        
        return data_list
        
    except Exception as e:
        if isinstance(e, DataLoadError):
            raise
        raise DataLoadError(f"Error loading custom data from {csv_path}: {e}")


def batch_load_custom_data(
    data_dir: Path,
    symbol: str,
    instrument_id: InstrumentId,
    data_types: List[str] = ["oi", "funding"]
) -> Dict[str, List]:
    """
    批量加载指定符号的所有自定义数据
    
    Parameters
    ----------
    data_dir : Path
        数据目录路径
    symbol : str
        交易对符号（如 "BTCUSDT"）
    instrument_id : InstrumentId
        NautilusTrader 合约标识符
    data_types : List[str], optional
        要加载的数据类型列表，默认 ["oi", "funding"]
        
    Returns
    -------
    Dict[str, List]
        按数据类型分组的数据字典
    """
    symbol_dir = data_dir / symbol
    result = {}
    
    for data_type in data_types:
        result[data_type] = []
        
        if not symbol_dir.exists():
            continue
        
        # 查找匹配的数据文件
        if data_type == "oi":
            pattern = "*-oi-*.csv"
        elif data_type == "funding":
            pattern = "*-funding-*.csv"
        else:
            continue
        
        data_files = list(symbol_dir.glob(pattern))
        
        for file_path in data_files:
            try:
                custom_data = load_custom_csv_data(file_path, data_type, instrument_id)
                result[data_type].extend(custom_data)
            except DataLoadError as e:
                print(f"⚠️ Failed to load {file_path}: {e}")
                continue
    
    return result


def clean_and_deduplicate_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    清洗和去重数据
    
    Parameters
    ----------
    df : pd.DataFrame
        原始数据框
        
    Returns
    -------
    pd.DataFrame
        清洗后的数据框
    """
    # 去除重复行
    df_clean = df.drop_duplicates()
    
    # 去除包含NaN的行
    df_clean = df_clean.dropna()
    
    # 如果有时间索引，去除重复的时间戳
    if hasattr(df_clean.index, 'duplicated'):
        df_clean = df_clean[~df_clean.index.duplicated(keep='first')]
    
    return df_clean


def get_data_summary(df: pd.DataFrame) -> Dict[str, Any]:
    """
    获取数据摘要信息
    
    Parameters
    ----------
    df : pd.DataFrame
        数据框
        
    Returns
    -------
    Dict[str, Any]
        数据摘要信息
    """
    summary = {
        "rows": len(df),
        "columns": list(df.columns),
        "start_time": df.index.min() if len(df) > 0 else None,
        "end_time": df.index.max() if len(df) > 0 else None,
        "missing_values": df.isnull().sum().to_dict(),
        "data_types": df.dtypes.to_dict(),
    }
    
    # 如果包含OHLCV数据，添加价格统计
    if all(col in df.columns for col in ["open", "high", "low", "close"]):
        summary["price_stats"] = {
            "min_price": float(df[["open", "high", "low", "close"]].min().min()),
            "max_price": float(df[["open", "high", "low", "close"]].max().max()),
            "avg_close": float(df["close"].mean()),
        }
    
    # 如果包含成交量数据
    if "volume" in df.columns:
        summary["volume_stats"] = {
            "total_volume": float(df["volume"].sum()),
            "avg_volume": float(df["volume"].mean()),
            "max_volume": float(df["volume"].max()),
        }
    
    return summary


class DataLoader:
    """
    统一数据加载器类
    
    提供便捷的数据加载和管理功能
    """
    
    def __init__(self, base_dir: Path):
        """
        初始化数据加载器
        
        Parameters
        ----------
        base_dir : Path
            数据基础目录
        """
        self.base_dir = base_dir
        self.raw_data_dir = base_dir / "data" / "raw"
    
    def load_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        exchange: str = "binance"
    ) -> pd.DataFrame:
        """
        加载指定符号的OHLCV数据
        
        Parameters
        ----------
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
            
        Returns
        -------
        pd.DataFrame
            OHLCV数据框
        """
        safe_symbol = symbol.replace("/", "")
        filename = f"{exchange.lower()}-{safe_symbol}-{timeframe}-{start_date}_{end_date}.csv"
        file_path = self.raw_data_dir / safe_symbol / filename
        
        return load_ohlcv_csv(file_path, start_date=start_date, end_date=end_date)
    
    def load_custom_data(
        self,
        symbol: str,
        instrument_id: InstrumentId,
        data_types: List[str] = ["oi", "funding"]
    ) -> Dict[str, List]:
        """
        加载指定符号的自定义数据
        
        Parameters
        ----------
        symbol : str
            交易对符号
        instrument_id : InstrumentId
            合约标识符
        data_types : List[str], optional
            数据类型列表，默认 ["oi", "funding"]
            
        Returns
        -------
        Dict[str, List]
            自定义数据字典
        """
        return batch_load_custom_data(self.raw_data_dir, symbol, instrument_id, data_types)
    
    def validate_data_availability(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        exchange: str = "binance"
    ) -> Tuple[bool, str | None]:
        """
        验证数据可用性
        
        Parameters
        ----------
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
            
        Returns
        -------
        Tuple[bool, str | None]
            (数据是否可用, 错误信息)
        """
        from utils.validation import check_data_exists
        
        return check_data_exists(
            symbol_str=symbol,
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe,
            exchange=exchange,
            base_dir=self.base_dir
        )


def load_csv_with_time_detection(
    csv_path: Union[str, Path],
    time_column: str | None = None
) -> pd.DataFrame:
    """
    简化的CSV数据加载函数，支持自动时间列检测
    
    这是 load_ohlcv_csv 的简化版本，主要用于测试和快速数据加载。
    
    Parameters
    ----------
    csv_path : Union[str, Path]
        CSV文件路径
    time_column : str | None, optional
        指定时间列名称，None表示自动检测
        
    Returns
    -------
    pd.DataFrame
        加载的数据框，如果检测到时间列会进行相应处理
        
    Raises
    ------
    DataLoadError
        当数据加载失败时
    """
    csv_path = Path(csv_path)
    
    if not csv_path.exists():
        print(f"Warning: CSV file not found: {csv_path}")
        return pd.DataFrame()
    
    try:
        # 先尝试基本加载
        df = pd.read_csv(csv_path)
        
        if df.empty:
            return df
        
        # 自动检测时间列（如果未指定）
        if time_column is None:
            try:
                time_column = detect_time_column(csv_path)
            except TimeColumnError:
                # 没有时间列，直接返回原始数据
                return df
        
        # 如果找到时间列，进行相应处理
        if time_column and time_column in df.columns:
            # 尝试转换datetime列
            if time_column.lower() == "datetime":
                try:
                    # 使用更智能的日期解析，支持混合格式
                    df[time_column] = pd.to_datetime(df[time_column], format='mixed', errors='coerce')
                    # 如果仍有解析错误，尝试使用infer方法
                    if df[time_column].isnull().any():
                        df[time_column] = pd.to_datetime(df[time_column], infer_datetime_format=True, errors='coerce')
                except Exception as e:
                    print(f"Warning: Failed to convert datetime column: {e}")
            # timestamp列保持原样（数值类型）
            
        return df
        
    except Exception as e:
        print(f"Warning: Error loading CSV from {csv_path}: {e}")
        return pd.DataFrame()