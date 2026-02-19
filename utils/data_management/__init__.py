"""
数据管理模块

提供数据获取、验证和管理的统一接口。

主要功能：
- OHLCV 数据获取和管理
- OI/Funding Rate 数据获取和管理
- 数据验证和完整性检查
"""

from .data_fetcher import BinanceFetcher, CoinGeckoFetcher, DataFetcher
from .data_limits import (
    check_data_availability,
    get_recommended_date_range,
    validate_strategy_data_requirements,
)
from .data_loader import (
    DataLoader,
    clean_and_deduplicate_data,
    create_nautilus_bars,
    detect_time_column,
    get_data_summary,
    load_csv_with_time_detection,
    load_custom_csv_data,
    load_ohlcv_csv,
    load_ohlcv_parquet,
    load_ohlcv_auto,
)
from .data_manager import DataManager, fetch_data_with_retry, run_batch_data_retrieval
from .data_retrieval import (
    batch_fetch_ohlcv,
    batch_fetch_oi_and_funding,
    fetch_binance_funding_rate_history,
    fetch_binance_oi_history,
    fetch_ohlcv_data,
    fetch_okx_funding_rate_history,
    fetch_okx_oi_history,
)
from .data_validator import DataValidator, prepare_data_feeds

__all__ = [
    # Fetcher manager
    "run_batch_data_retrieval",
    "fetch_data_with_retry",
    # Validator
    "prepare_data_feeds",
    # Data fetcher
    "DataFetcher",
    "BinanceFetcher",
    "CoinGeckoFetcher",
    # Data limits
    "check_data_availability",
    "get_recommended_date_range",
    "validate_strategy_data_requirements",
    # Data loader
    "DataLoader",
    "load_ohlcv_csv",
    "load_ohlcv_parquet",
    "load_ohlcv_auto",
    "load_csv_with_time_detection",
    "load_custom_csv_data",
    "create_nautilus_bars",
    "detect_time_column",
    "clean_and_deduplicate_data",
    "get_data_summary",
    # Data manager
    "DataManager",
    # Data retrieval
    "batch_fetch_ohlcv",
    "batch_fetch_oi_and_funding",
    "fetch_ohlcv_data",
    "fetch_binance_oi_history",
    "fetch_okx_oi_history",
    "fetch_binance_funding_rate_history",
    "fetch_okx_funding_rate_history",
    # Data validator
    "DataValidator",
]
