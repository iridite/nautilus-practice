"""
OI 和 Funding Rate 数据适配器

用于在 NautilusTrader 回测引擎中加载和处理 Open Interest 和 Funding Rate 数据。
将 CSV 格式的原始数据转换为 NautilusTrader 自定义数据类型。
"""

import logging
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

import pandas as pd
from nautilus_trader.core.nautilus_pyo3 import millis_to_nanos
from nautilus_trader.model.identifiers import InstrumentId

from utils.custom_data import FundingRateData, OpenInterestData

logger = logging.getLogger(__name__)


class OIFundingDataLoader:
    """
    OI 和 Funding Rate 数据加载器

    从 CSV 文件读取数据并转换为 NautilusTrader 自定义数据类型
    """

    def __init__(self, base_dir: Path):
        """
        初始化数据加载器

        Parameters
        ----------
        base_dir : Path
            数据文件的基础目录（通常是项目根目录）
        """
        self.base_dir = base_dir
        self.data_dir = base_dir / "data" / "raw"

    def _find_available_oi_files(self, symbol: str, exchange: str = "binance") -> list:
        """查找可用的 OI 数据文件"""
        safe_symbol = symbol.replace("/", "")
        symbol_dir = self.data_dir / safe_symbol

        if not symbol_dir.exists():
            return []

        oi_files = list(symbol_dir.glob(f"{exchange}-{safe_symbol}-oi-*.csv"))
        return sorted(oi_files)

    def _build_oi_file_path(
        self, symbol: str, exchange: str, period: str, start_date: str, end_date: str
    ) -> Path:
        """构建OI数据文件路径"""
        safe_symbol = symbol.replace("/", "")
        filename = f"{exchange}-{safe_symbol}-oi-{period}-{start_date}_{end_date}.csv"
        return self.data_dir / safe_symbol / filename

    def _log_missing_oi_file(self, file_path: Path, symbol: str, exchange: str):
        """记录缺失的OI文件信息"""
        logger.warning(f"⚠️  OI data file not found: {file_path}")

        available_files = self._find_available_oi_files(symbol, exchange)
        if available_files:
            logger.info(f"💡 Found {len(available_files)} available OI file(s):")
            for f in available_files[:5]:
                logger.info(f"   - {f.name}")
            if len(available_files) > 5:
                logger.info(f"   ... and {len(available_files) - 5} more")
        else:
            safe_symbol = symbol.replace("/", "")
            logger.error(f"❌ No OI data files found for {symbol} in {self.data_dir / safe_symbol}")

    def _validate_oi_dataframe(self, df: pd.DataFrame, file_path: Path) -> bool:
        """验证OI数据格式"""
        if "timestamp" not in df.columns or "open_interest" not in df.columns:
            logger.warning(f"Warning: Invalid OI data format in {file_path}")
            return False
        return True

    def _convert_row_to_oi_data(self, row, instrument_id: InstrumentId) -> OpenInterestData:
        """将DataFrame行转换为OpenInterestData对象"""
        ts_ms = int(row["timestamp"])
        ts_event = millis_to_nanos(ts_ms)
        ts_init = ts_event
        oi = Decimal(str(row["open_interest"]))

        return OpenInterestData(
            instrument_id=instrument_id,
            open_interest=oi,
            ts_event=ts_event,
            ts_init=ts_init,
        )

    def load_oi_data(
        self,
        symbol: str,
        instrument_id: InstrumentId,
        start_date: str,
        end_date: str,
        exchange: str = "binance",
        period: str = "1h",
    ) -> List[OpenInterestData]:
        """
        加载 Open Interest 数据

        Parameters
        ----------
        symbol : str
            交易对符号（如 "BTCUSDT"）
        instrument_id : InstrumentId
            NautilusTrader 合约标识符
        start_date : str
            开始日期（YYYY-MM-DD）
        end_date : str
            结束日期（YYYY-MM-DD）
        exchange : str
            交易所名称（默认 "binance"）
        period : str
            数据周期（默认 "1h"）

        Returns
        -------
        List[OpenInterestData]
            OI 数据列表，按时间戳排序
        """
        file_path = self._build_oi_file_path(symbol, exchange, period, start_date, end_date)

        if not file_path.exists():
            self._log_missing_oi_file(file_path, symbol, exchange)
            return []

        try:
            df = pd.read_csv(file_path)

            if not self._validate_oi_dataframe(df, file_path):
                return []

            oi_data_list = [
                self._convert_row_to_oi_data(row, instrument_id) for _, row in df.iterrows()
            ]

            logger.info(f"✅ Loaded {len(oi_data_list)} OI data points for {symbol}")
            return oi_data_list

        except Exception as e:
            logger.error(f"Error loading OI data from {file_path}: {e}")
            return []

    def _find_available_funding_files(self, symbol: str, exchange: str = "binance") -> list:
        """查找可用的 Funding Rate 数据文件"""
        safe_symbol = symbol.replace("/", "")
        symbol_dir = self.data_dir / safe_symbol

        if not symbol_dir.exists():
            return []

        funding_files = list(symbol_dir.glob(f"{exchange}-{safe_symbol}-funding-*.csv"))
        return sorted(funding_files)

    def _build_funding_file_path(
        self, symbol: str, exchange: str, start_date: str, end_date: str
    ) -> Path:
        """构建Funding数据文件路径"""
        safe_symbol = symbol.replace("/", "")
        filename = f"{exchange}-{safe_symbol}-funding-{start_date}_{end_date}.csv"
        return self.data_dir / safe_symbol / filename

    def _log_file_not_found(self, file_path: Path, symbol: str, exchange: str) -> None:
        """记录文件未找到的警告信息"""
        logger.warning(f"⚠️  Funding data file not found: {file_path}")

        # 查找可用的替代文件
        available_files = self._find_available_funding_files(symbol, exchange)
        if available_files:
            logger.info(f"💡 Found {len(available_files)} available Funding file(s):")
            for f in available_files[:5]:  # 只显示前5个
                logger.info(f"   - {f.name}")
            if len(available_files) > 5:
                logger.info(f"   ... and {len(available_files) - 5} more")
        else:
            safe_symbol = symbol.replace("/", "")
            logger.error(
                f"❌ No Funding data files found for {symbol} in {self.data_dir / safe_symbol}"
            )

    def _validate_funding_dataframe(self, df: pd.DataFrame, file_path: Path) -> bool:
        """验证Funding数据DataFrame格式"""
        if "timestamp" not in df.columns or "funding_rate" not in df.columns:
            logger.warning(f"Warning: Invalid funding data format in {file_path}")
            return False
        return True

    def _parse_next_funding_time(self, row: pd.Series, df: pd.DataFrame) -> Optional[int]:
        """解析下次资金费率结算时间"""
        if "next_funding_time" in df.columns and pd.notna(row["next_funding_time"]):
            return millis_to_nanos(int(row["next_funding_time"]))
        return None

    def _convert_row_to_funding_data(
        self, row: pd.Series, df: pd.DataFrame, instrument_id: InstrumentId
    ) -> FundingRateData:
        """将DataFrame行转换为FundingRateData对象"""
        ts_ms = int(row["timestamp"])
        ts_event = millis_to_nanos(ts_ms)
        ts_init = ts_event

        funding_rate = Decimal(str(row["funding_rate"]))
        next_funding_time = self._parse_next_funding_time(row, df)

        return FundingRateData(
            instrument_id=instrument_id,
            funding_rate=funding_rate,
            next_funding_time=next_funding_time,
            ts_event=ts_event,
            ts_init=ts_init,
        )

    def _parse_funding_dataframe(
        self, df: pd.DataFrame, instrument_id: InstrumentId
    ) -> List[FundingRateData]:
        """解析DataFrame为FundingRateData列表"""
        funding_data_list = []
        for _, row in df.iterrows():
            funding_data = self._convert_row_to_funding_data(row, df, instrument_id)
            funding_data_list.append(funding_data)
        return funding_data_list

    def load_funding_data(
        self,
        symbol: str,
        instrument_id: InstrumentId,
        start_date: str,
        end_date: str,
        exchange: str = "binance",
    ) -> List[FundingRateData]:
        """
        加载 Funding Rate 数据

        Parameters
        ----------
        symbol : str
            交易对符号（如 "BTCUSDT"）
        instrument_id : InstrumentId
            NautilusTrader 合约标识符
        start_date : str
            开始日期（YYYY-MM-DD）
        end_date : str
            结束日期（YYYY-MM-DD）
        exchange : str
            交易所名称（默认 "binance"）

        Returns
        -------
        List[FundingRateData]
            Funding Rate 数据列表，按时间戳排序
        """
        file_path = self._build_funding_file_path(symbol, exchange, start_date, end_date)

        if not file_path.exists():
            self._log_file_not_found(file_path, symbol, exchange)
            return []

        try:
            df = pd.read_csv(file_path)

            if not self._validate_funding_dataframe(df, file_path):
                return []

            funding_data_list = self._parse_funding_dataframe(df, instrument_id)

            logger.info(f"Loaded {len(funding_data_list)} Funding Rate data points for {symbol}")
            return funding_data_list

        except Exception as e:
            logger.error(f"Error loading Funding data from {file_path}: {e}")
            return []

    def load_all_custom_data(
        self,
        symbol: str,
        instrument_id: InstrumentId,
        start_date: str,
        end_date: str,
        exchange: str = "binance",
        oi_period: str = "1h",
    ) -> dict:
        """
        一次性加载所有自定义数据（OI + Funding Rate）

        Parameters
        ----------
        symbol : str
            交易对符号
        instrument_id : InstrumentId
            NautilusTrader 合约标识符
        start_date : str
            开始日期
        end_date : str
            结束日期
        exchange : str
            交易所名称
        oi_period : str
            OI 数据周期

        Returns
        -------
        dict
            包含 'oi' 和 'funding' 键的字典
        """
        oi_data = self.load_oi_data(
            symbol=symbol,
            instrument_id=instrument_id,
            start_date=start_date,
            end_date=end_date,
            exchange=exchange,
            period=oi_period,
        )

        funding_data = self.load_funding_data(
            symbol=symbol,
            instrument_id=instrument_id,
            start_date=start_date,
            end_date=end_date,
            exchange=exchange,
        )

        return {
            "oi": oi_data,
            "funding": funding_data,
        }


def merge_custom_data_with_bars(
    oi_data: List[OpenInterestData],
    funding_data: List[FundingRateData],
) -> List:
    """
    将 OI 和 Funding Rate 数据合并成统一的时间序列

    Parameters
    ----------
    oi_data : List[OpenInterestData]
        OI 数据列表
    funding_data : List[FundingRateData]
        Funding Rate 数据列表

    Returns
    -------
    List
        按时间戳排序的混合数据列表
    """
    # 合并两种数据类型
    all_data = []
    all_data.extend(oi_data)
    all_data.extend(funding_data)

    # 按时间戳排序
    all_data.sort(key=lambda x: x.ts_event)

    return all_data


def validate_data_alignment(
    oi_data: List[OpenInterestData],
    funding_data: List[FundingRateData],
    bar_count: int,
    tolerance_hours: int = 1,
) -> dict:
    """
    验证自定义数据与 OHLCV 数据的对齐情况

    Parameters
    ----------
    oi_data : List[OpenInterestData]
        OI 数据列表
    funding_data : List[FundingRateData]
        Funding Rate 数据列表
    bar_count : int
        OHLCV Bar 数量
    tolerance_hours : int
        时间容差（小时）

    Returns
    -------
    dict
        验证结果
    """
    result = {
        "valid": True,
        "warnings": [],
        "oi_count": len(oi_data),
        "funding_count": len(funding_data),
        "bar_count": bar_count,
    }

    # 检查 OI 数据数量
    if len(oi_data) == 0:
        result["valid"] = False
        result["warnings"].append("No OI data available")
    elif abs(len(oi_data) - bar_count) > tolerance_hours:
        result["warnings"].append(
            f"OI data count ({len(oi_data)}) differs significantly from bar count ({bar_count})"
        )

    # 检查 Funding Rate 数据数量
    expected_funding_count = bar_count // 8  # 每 8 小时一次
    if len(funding_data) == 0:
        result["valid"] = False
        result["warnings"].append("No Funding Rate data available")
    elif abs(len(funding_data) - expected_funding_count) > tolerance_hours:
        result["warnings"].append(
            f"Funding data count ({len(funding_data)}) differs from expected ({expected_funding_count})"
        )

    return result


def _get_supported_exchanges(preferred_exchange: str) -> list:
    """获取支持的交易所列表"""
    if preferred_exchange == "auto":
        return ["binance", "okx"]

    if preferred_exchange in ["binance", "okx"]:
        fallback = "okx" if preferred_exchange == "binance" else "binance"
        return [preferred_exchange, fallback]

    return ["binance", "okx"]


def _process_data_task(
    data_type: str,
    symbols: set,
    exchange: str,
    start_date: str,
    end_date: str,
    period: str,
    base_dir: Path,
    max_retries: int,
    supported_exchanges: list,
) -> tuple:
    """处理单个数据获取任务"""
    from utils.data_management.data_manager import fetch_data_with_retry

    if not symbols:
        return 0, 0, 0, None

    symbols_list = sorted(list(symbols))
    return fetch_data_with_retry(
        data_type,
        symbols_list,
        exchange,
        start_date,
        end_date,
        period,
        base_dir,
        max_retries,
        supported_exchanges,
    )


def _update_results(
    results: dict, files: int, retries: int, fallbacks: int, error: str, file_key: str
):
    """更新结果统计"""
    results[file_key] += files
    results["retries"] += retries
    results["fallbacks"] += fallbacks
    if error:
        results["errors"].append(error)


def execute_oi_funding_data_fetch(
    tasks: dict, base_dir: Path, preferred_exchange: str = "auto", max_retries: int = 3
) -> dict:
    """
    执行 OI 和 Funding Rate 数据获取（带智能重试和错误恢复）

    Parameters
    ----------
    tasks : dict
        数据获取任务字典，包含 oi_tasks 和 funding_tasks
    base_dir : Path
        项目基础目录
    preferred_exchange : str
        首选交易所，默认 "auto"
    max_retries : int
        最大重试次数，默认 3

    Returns
    -------
    dict
        执行结果统计
    """
    results = {"oi_files": 0, "funding_files": 0, "errors": [], "retries": 0, "fallbacks": 0}
    supported_exchanges = _get_supported_exchanges(preferred_exchange)

    # 处理 OI 数据
    for (exchange, period, start_date, end_date), symbols in tasks["oi_tasks"].items():
        files, retries, fallbacks, error = _process_data_task(
            "oi",
            symbols,
            exchange,
            start_date,
            end_date,
            period,
            base_dir,
            max_retries,
            supported_exchanges,
        )
        _update_results(results, files, retries, fallbacks, error, "oi_files")

    # 处理 Funding 数据
    for (exchange, start_date, end_date), symbols in tasks["funding_tasks"].items():
        files, retries, fallbacks, error = _process_data_task(
            "funding",
            symbols,
            exchange,
            start_date,
            end_date,
            "1h",
            base_dir,
            max_retries,
            supported_exchanges,
        )
        _update_results(results, files, retries, fallbacks, error, "funding_files")

    return results


# 使用示例
if __name__ == "__main__":
    from pathlib import Path

    from nautilus_trader.model.identifiers import InstrumentId

    # 初始化加载器
    base_dir = Path(__file__).parent.parent
    loader = OIFundingDataLoader(base_dir)

    # 加载数据
    symbol = "BTCUSDT"
    instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")

    custom_data = loader.load_all_custom_data(
        symbol=symbol,
        instrument_id=instrument_id,
        start_date="2024-01-01",
        end_date="2024-12-31",
        exchange="binance",
        oi_period="1h",
    )

    logger.info("\n📊 Custom Data Summary:")
    logger.info(f"  OI Data Points: {len(custom_data['oi'])}")
    logger.info(f"  Funding Rate Data Points: {len(custom_data['funding'])}")

    # 合并数据
    merged = merge_custom_data_with_bars(custom_data["oi"], custom_data["funding"])
    logger.info(f"  Total Custom Data Points: {len(merged)}")
