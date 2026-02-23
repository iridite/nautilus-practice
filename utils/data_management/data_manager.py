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
- 数据质量检查
"""

import logging
from pathlib import Path
from typing import List, Tuple

import pandas as pd

from core.exceptions import DataValidationError
from utils.data_file_checker import check_single_data_file
from utils.symbol_parser import convert_timeframe_to_seconds

from .data_retrieval import batch_fetch_ohlcv, batch_fetch_oi_and_funding

logger = logging.getLogger(__name__)


class DataQualityChecker:
    """数据质量检查器"""

    def __init__(self, enable_logging: bool = True):
        """
        初始化数据质量检查器

        Args:
            enable_logging: 是否启用日志记录
        """
        self.enable_logging = enable_logging

    def check_missing_values(self, df: pd.DataFrame, symbol: str) -> List[str]:
        """
        检查缺失值

        Args:
            df: 数据DataFrame
            symbol: 交易对符号

        Returns:
            问题列表
        """
        issues = []
        if df.isnull().any().any():
            null_cols = df.columns[df.isnull().any()].tolist()
            null_counts = {col: df[col].isnull().sum() for col in null_cols}
            issue = f"数据包含缺失值: {null_counts}"
            issues.append(issue)
            if self.enable_logging:
                logger.warning(f"{symbol}: {issue}")
        return issues

    def check_timestamp_continuity(
        self, df: pd.DataFrame, symbol: str, timeframe: str
    ) -> List[str]:
        """
        检查时间戳连续性

        Args:
            df: 数据DataFrame
            symbol: 交易对符号
            timeframe: 时间周期

        Returns:
            问题列表
        """
        issues = []
        if "timestamp" not in df.columns:
            return issues

        if len(df) < 2:
            return issues

        # 计算预期时间间隔
        expected_interval = convert_timeframe_to_seconds(timeframe) * 1000  # 转换为毫秒

        # 检查时间戳间隔
        time_diff = df["timestamp"].diff()
        # 允许1.5倍的容差
        gaps = (time_diff > expected_interval * 1.5).sum()

        if gaps > 0:
            issue = f"数据有{gaps}个时间戳间隔异常"
            issues.append(issue)
            if self.enable_logging:
                logger.warning(f"{symbol}: {issue}")

        return issues

    def check_price_outliers(self, df: pd.DataFrame, symbol: str, sigma: float = 3.0) -> List[str]:
        """
        检查价格异常值（使用3-sigma规则）

        Args:
            df: 数据DataFrame
            symbol: 交易对符号
            sigma: 标准差倍数阈值

        Returns:
            问题列表
        """
        issues = []
        if "close" not in df.columns or len(df) < 10:
            return issues

        # 计算收益率
        returns = df["close"].pct_change().dropna()

        if len(returns) == 0:
            return issues

        returns_mean = returns.mean()
        returns_std = returns.std()

        if returns_std == 0 or pd.isna(returns_std):
            return issues

        # 检测异常值（使用标准化后的收益率）
        z_scores = abs((returns - returns_mean) / returns_std)
        outliers = (z_scores > sigma).sum()
        outlier_threshold = len(df) * 0.01  # 1%的数据

        if outliers > outlier_threshold:
            issue = f"数据有{outliers}个价格异常值 (>{sigma}σ)"
            issues.append(issue)
            if self.enable_logging:
                logger.warning(f"{symbol}: {issue}")

        return issues

    def check_volume_anomalies(
        self, df: pd.DataFrame, symbol: str, zero_threshold: float = 0.05
    ) -> List[str]:
        """
        检查成交量异常

        Args:
            df: 数据DataFrame
            symbol: 交易对符号
            zero_threshold: 零成交量阈值（占比）

        Returns:
            问题列表
        """
        issues = []
        if "volume" not in df.columns or len(df) == 0:
            return issues

        # 检查零成交量
        zero_volume = (df["volume"] == 0).sum()
        zero_ratio = zero_volume / len(df)

        if zero_ratio > zero_threshold:
            issue = f"数据有{zero_volume}个零成交量记录 ({zero_ratio:.1%})"
            issues.append(issue)
            if self.enable_logging:
                logger.warning(f"{symbol}: {issue}")

        return issues

    def check_data_completeness(
        self, df: pd.DataFrame, symbol: str, start_date: str, end_date: str, timeframe: str
    ) -> List[str]:
        """
        检查数据完整性

        Args:
            df: 数据DataFrame
            symbol: 交易对符号
            start_date: 开始日期
            end_date: 结束日期
            timeframe: 时间周期

        Returns:
            问题列表
        """
        issues = []
        if "timestamp" not in df.columns or len(df) == 0:
            return issues

        # 计算预期数据点数量
        from utils.time_helpers import get_ms_timestamp

        start_ms = get_ms_timestamp(start_date)
        end_ms = get_ms_timestamp(end_date)
        interval_ms = convert_timeframe_to_seconds(timeframe) * 1000

        expected_count = int((end_ms - start_ms) / interval_ms)
        actual_count = len(df)

        # 允许5%的容差（考虑交易所停机、节假日等）
        completeness_ratio = actual_count / expected_count if expected_count > 0 else 0

        if completeness_ratio < 0.95:
            issue = f"数据完整性不足: {actual_count}/{expected_count} ({completeness_ratio:.1%})"
            issues.append(issue)
            if self.enable_logging:
                logger.warning(f"{symbol}: {issue}")

        return issues

    def validate_data_quality(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        start_date: str = None,
        end_date: str = None,
        raise_on_error: bool = False,
    ) -> Tuple[bool, List[str]]:
        """
        验证数据质量（综合检查）

        Args:
            df: 数据DataFrame
            symbol: 交易对符号
            timeframe: 时间周期
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            raise_on_error: 是否在发现问题时抛出异常

        Returns:
            (是否通过, 问题列表)

        Raises:
            DataValidationError: 当raise_on_error=True且发现问题时
        """
        all_issues = []

        # 1. 检查缺失值
        all_issues.extend(self.check_missing_values(df, symbol))

        # 2. 检查时间戳连续性
        all_issues.extend(self.check_timestamp_continuity(df, symbol, timeframe))

        # 3. 检查价格异常值
        all_issues.extend(self.check_price_outliers(df, symbol))

        # 4. 检查成交量异常
        all_issues.extend(self.check_volume_anomalies(df, symbol))

        # 5. 检查数据完整性（如果提供了日期范围）
        if start_date and end_date:
            all_issues.extend(
                self.check_data_completeness(df, symbol, start_date, end_date, timeframe)
            )

        is_valid = len(all_issues) == 0

        if not is_valid and raise_on_error:
            raise DataValidationError(f"{symbol} 数据质量问题: {'; '.join(all_issues)}")

        return is_valid, all_issues


class DataManager:
    """统一数据管理器"""

    def __init__(self, base_dir: Path, enable_quality_check: bool = True):
        self.base_dir = base_dir
        self.data_dir = base_dir / "data" / "raw"
        self.enable_quality_check = enable_quality_check
        self.quality_checker = (
            DataQualityChecker(enable_logging=True) if enable_quality_check else None
        )

    def check_data_availability(
        self, symbols: List[str], start_date: str, end_date: str, timeframe: str, exchange: str
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
        max_retries: int = 3,
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
        auto_fetch: bool = True,
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

        result = self.fetch_missing_data(missing, start_date, end_date, timeframe, exchange)

        return result["success"] > 0

    def validate_data_file(
        self,
        file_path: Path,
        symbol: str,
        timeframe: str,
        start_date: str = None,
        end_date: str = None,
        raise_on_error: bool = False,
    ) -> Tuple[bool, List[str]]:
        """
        验证数据文件质量

        Args:
            file_path: 数据文件路径
            symbol: 交易对符号
            timeframe: 时间周期
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            raise_on_error: 是否在发现问题时抛出异常

        Returns:
            (是否通过, 问题列表)
        """
        if not self.enable_quality_check:
            return True, []

        if not file_path.exists():
            issue = f"文件不存在: {file_path}"
            if raise_on_error:
                raise DataValidationError(issue)
            return False, [issue]

        try:
            df = pd.read_csv(file_path)
            return self.quality_checker.validate_data_quality(
                df, symbol, timeframe, start_date, end_date, raise_on_error
            )
        except Exception as e:
            issue = f"读取文件失败: {e}"
            if raise_on_error:
                raise DataValidationError(issue, cause=e)
            return False, [issue]

    def batch_validate_data(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
        timeframe: str,
        exchange: str,
    ) -> dict:
        """
        批量验证数据质量

        Args:
            symbols: 交易对列表
            start_date: 开始日期
            end_date: 结束日期
            timeframe: 时间周期
            exchange: 交易所

        Returns:
            验证结果字典 {"passed": [...], "failed": {...}}
        """
        if not self.enable_quality_check:
            return {"passed": symbols, "failed": {}}

        passed = []
        failed = {}

        for symbol in symbols:
            safe_symbol = symbol.replace("/", "")
            filename = f"{exchange}-{safe_symbol}-{timeframe}-{start_date}_{end_date}.csv"
            file_path = self.data_dir / safe_symbol / filename

            is_valid, issues = self.validate_data_file(
                file_path, symbol, timeframe, start_date, end_date, raise_on_error=False
            )

            if is_valid:
                passed.append(symbol)
            else:
                failed[symbol] = issues

        if failed:
            logger.warning(f"数据质量检查: {len(passed)}/{len(symbols)} 通过")
            for symbol, issues in failed.items():
                logger.warning(f"  {symbol}: {'; '.join(issues)}")
        else:
            logger.info(f"数据质量检查: 全部通过 ({len(passed)}/{len(symbols)})")

        return {"passed": passed, "failed": failed}


def run_batch_data_retrieval(
    symbols, start_date, end_date, timeframe, exchange, base_dir: Path
) -> list:
    """直接调用 Python 函数进行数据抓取"""
    if not symbols:
        return []

    logger.info(
        f"Fetching/Updating raw trade pair data for {len(symbols)} symbols via functional call..."
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
    supported_exchanges: list,
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
