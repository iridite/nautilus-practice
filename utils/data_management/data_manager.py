"""
数据管理器模块

提供统一的数据获取、验证和管理功能，符合行业标准实践。

核心功能：
- 数据完整性检查
- 自动数据获取
- 多数据源支持
- 错误处理和重试
- 批量数据获取管理
- 带重试的数据获取
"""

import logging
from pathlib import Path
from typing import List, Tuple

from utils.data_file_checker import check_single_data_file

from .data_retrieval import batch_fetch_ohlcv, batch_fetch_oi_and_funding

logger = logging.getLogger(__name__)

class DataManager:
    """统一数据管理器"""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.data_dir = base_dir / "data" / "raw"

    def check_data_availability(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
        timeframe: str,
        exchange: str
    ) -> Tuple[List[str], List[str]]:
        """
        检查数据可用性

        Returns:
            (available_symbols, missing_symbols)
        """
        available = []
        missing = []

        for symbol in symbols:
            exists, _ = check_single_data_file(
                symbol, start_date, end_date, timeframe, exchange, self.base_dir
            )
            if exists:
                available.append(symbol)
            else:
                missing.append(symbol)

        return available, missing

    def fetch_missing_data(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
        timeframe: str,
        exchange: str,
        max_retries: int = 3
    ) -> dict:
        """
        获取缺失数据

        Returns:
            {"success": int, "failed": int, "symbols": List[str]}
        """
        from utils.data_management import run_batch_data_retrieval

        try:
            run_batch_data_retrieval(
                symbols, start_date, end_date, timeframe, exchange, self.base_dir
            )
            return {"success": len(symbols), "failed": 0, "symbols": symbols}
        except Exception as e:
            return {"success": 0, "failed": len(symbols), "error": str(e)}

    def ensure_data_ready(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
        timeframe: str,
        exchange: str,
        auto_fetch: bool = True
    ) -> bool:
        """
        确保数据就绪

        Args:
            auto_fetch: 是否自动获取缺失数据

        Returns:
            是否所有数据就绪
        """
        available, missing = self.check_data_availability(
            symbols, start_date, end_date, timeframe, exchange
        )

        if not missing:
            return True

        if not auto_fetch:
            return False

        result = self.fetch_missing_data(
            missing, start_date, end_date, timeframe, exchange
        )

        return result["success"] > 0


def run_batch_data_retrieval(
    symbols, start_date, end_date, timeframe, exchange, base_dir: Path
) -> list:
    """直接调用 Python 函数进行数据抓取"""
    if not symbols:
        return []

    print(
        f"\nFetching/Updating raw trade pair data for {len(symbols)} symbols via functional call..."
    )
    try:
        data_configs = batch_fetch_ohlcv(
            symbols=sorted(list(symbols)),
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe,
            exchange_id=exchange,
            base_dir=base_dir,
        )
        return data_configs
    except Exception as e:
        logger.error(f"❌ Error during data retrieval: {e}")
        return []


def _get_current_exchange(attempt: int, supported_exchanges: list) -> str:
    """获取当前尝试使用的交易所"""
    return supported_exchanges[min(attempt, len(supported_exchanges) - 1)]


def _extract_files_count(result: dict, data_type: str) -> int:
    """提取文件数量"""
    if not result:
        return 0
    
    if data_type == "oi":
        return len(result.get("oi_files", []))
    else:
        return len(result.get("funding_files", []))


def _calculate_retry_stats(attempt: int, current_exchange: str, exchange: str) -> tuple[int, int]:
    """计算重试统计"""
    retries_count = attempt if attempt > 0 else 0
    fallbacks_count = 1 if current_exchange != exchange else 0
    return retries_count, fallbacks_count


def fetch_data_with_retry(
    data_type: str,
    symbols: list,
    exchange: str,
    start_date: str,
    end_date: str,
    period: str,
    base_dir: Path,
    max_retries: int,
    supported_exchanges: list
) -> tuple[int, int, int, str | None]:
    """带重试的数据获取"""
    files_count = 0
    retries_count = 0
    fallbacks_count = 0
    error_msg = None

    for attempt in range(max_retries):
        try:
            current_exchange = _get_current_exchange(attempt, supported_exchanges)

            result = batch_fetch_oi_and_funding(
                symbols=symbols,
                start_date=start_date,
                end_date=end_date,
                exchange_id=current_exchange,
                base_dir=base_dir,
                oi_period=period,
            )

            files_count = _extract_files_count(result, data_type)
            if files_count > 0:
                retries_count, fallbacks_count = _calculate_retry_stats(
                    attempt, current_exchange, exchange
                )
                break

        except Exception as e:
            error_msg = str(e)
            if attempt >= max_retries - 1:
                break

    return files_count, retries_count, fallbacks_count, error_msg
