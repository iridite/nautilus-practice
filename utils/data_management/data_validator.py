"""
数据验证工具模块

提供通用的数据异常检测和验证功能，可被多个策略复用。
适用于 OI、Funding Rate、价格等市场数据的异常检测。
"""

"""数据验证模块 - 检查回测所需数据是否完整"""

import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

import pandas as pd

from backtest.tui_manager import get_tui, is_tui_enabled
from utils.filename_parser import FilenameParser
from utils.instrument_helpers import normalize_symbol_to_internal

logger = logging.getLogger(__name__)


class DataValidator:
    """
    数据验证器

    功能：
    - 检测数据有效性（NaN、None、0、负数）
    - 检测数据剧烈变化（换月、数据错误）
    - 检测异常值（超出合理范围）
    - 提供灵活的阈值配置
    """

    def __init__(
        self,
        spike_threshold: float = 0.5,
        enable_logging: bool = True,
    ):
        """
        初始化数据验证器

        Parameters
        ----------
        spike_threshold : float
            数据突变阈值（默认 50%）
        enable_logging : bool
            是否启用日志记录
        """
        self.spike_threshold = spike_threshold
        self.enable_logging = enable_logging
        self._last_valid_value: Optional[Decimal] = None

    def _check_oi_validity(self, oi_value: Optional[Decimal], logger) -> tuple[bool, Optional[str]]:
        """检查OI数据有效性"""
        if oi_value is None or oi_value <= 0:
            error_msg = f"Invalid OI data: {oi_value}"
            if logger and self.enable_logging:
                logger.warning(f"⚠️  {error_msg}")
            return False, error_msg
        return True, None

    def _check_oi_spike(self, oi_value: Decimal, logger) -> tuple[bool, Optional[str]]:
        """检查OI剧烈变化"""
        if self._last_valid_value is None or self._last_valid_value <= 0:
            return True, None

        change_pct = abs(float((oi_value - self._last_valid_value) / self._last_valid_value))
        if change_pct > self.spike_threshold:
            error_msg = (
                f"OI spike detected: {change_pct:.1%} change "
                f"(from {self._last_valid_value:.0f} to {oi_value:.0f}). "
                f"Possible contract roll or data error."
            )
            if logger and self.enable_logging:
                logger.warning(f"⚠️  {error_msg}")
            return False, error_msg
        return True, None

    def validate_oi(self, oi_value: Optional[Decimal], logger=None) -> tuple[bool, Optional[str]]:
        """
        验证 OI（持仓量）数据

        Parameters
        ----------
        oi_value : Optional[Decimal]
            OI 数据值
        logger : Logger, optional
            日志记录器

        Returns
        -------
        tuple[bool, Optional[str]]
            (是否有效, 错误信息)
        """
        is_valid, error_msg = self._check_oi_validity(oi_value, logger)
        if not is_valid:
            return False, error_msg
        if oi_value is None:
            return False, error_msg

        is_valid, error_msg = self._check_oi_spike(oi_value, logger)
        if not is_valid:
            return False, error_msg

        self._last_valid_value = oi_value
        return True, None

    def _check_funding_none(
        self, funding_annual: Optional[Decimal], logger
    ) -> tuple[bool, Optional[str]]:
        """检查资金费率是否为None"""
        if funding_annual is None:
            error_msg = "Invalid Funding Rate data: None"
            if logger and self.enable_logging:
                logger.warning(f"⚠️  {error_msg}")
            return False, error_msg
        return True, None

    def _check_funding_abnormal(
        self, funding_annual: Decimal, max_abs_value: float, logger
    ) -> tuple[bool, Optional[str]]:
        """检查资金费率是否超出正常范围"""
        if abs(float(funding_annual)) > max_abs_value:
            error_msg = (
                f"Abnormal Funding Rate: {funding_annual:.2f}% (annual), "
                f"exceeds ±{max_abs_value}% threshold. Possible data error."
            )
            if logger and self.enable_logging:
                logger.warning(f"⚠️  {error_msg}")
            return False, error_msg
        return True, None

    def _check_funding_spike(
        self, funding_annual: Decimal, spike_threshold: float, logger
    ) -> tuple[bool, Optional[str]]:
        """检查资金费率是否有剧烈变化"""
        if self._last_valid_value is not None:
            change = abs(float(funding_annual - self._last_valid_value))
            if change > spike_threshold:
                error_msg = (
                    f"Funding Rate spike detected: {change:.1f}% change "
                    f"(from {self._last_valid_value:.2f}% to {funding_annual:.2f}%). "
                    f"Possible data error."
                )
                if logger and self.enable_logging:
                    logger.warning(f"⚠️  {error_msg}")
                return False, error_msg
        return True, None

    def validate_funding_rate(
        self,
        funding_annual: Optional[Decimal],
        max_abs_value: float = 500.0,
        spike_threshold: float = 200.0,
        logger=None,
    ) -> tuple[bool, Optional[str]]:
        """
        验证 Funding Rate（资金费率）数据

        Parameters
        ----------
        funding_annual : Optional[Decimal]
            年化资金费率
        max_abs_value : float
            最大绝对值（默认 ±500%）
        spike_threshold : float
            突变阈值（默认 200%）
        logger : Logger, optional
            日志记录器

        Returns
        -------
        tuple[bool, Optional[str]]
            (是否有效, 错误信息)
        """
        # 检查 1: 数据有效性
        is_valid, error_msg = self._check_funding_none(funding_annual, logger)
        if not is_valid:
            return False, error_msg
        if funding_annual is None:
            return False, error_msg

        # 检查 2: 异常值检测
        is_valid, error_msg = self._check_funding_abnormal(funding_annual, max_abs_value, logger)
        if not is_valid:
            return False, error_msg

        # 检查 3: 剧烈变化检测
        is_valid, error_msg = self._check_funding_spike(funding_annual, spike_threshold, logger)
        if not is_valid:
            return False, error_msg

        # 数据通过验证
        self._last_valid_value = funding_annual
        return True, None

    def _check_price_validity(self, price: Optional[Decimal], logger) -> tuple[bool, Optional[str]]:
        """检查价格有效性"""
        if price is None or price <= 0:
            error_msg = f"Invalid price data: {price}"
            if logger and self.enable_logging:
                logger.warning(f"⚠️  {error_msg}")
            return False, error_msg
        return True, None

    def _check_price_min_range(
        self, price: Decimal, min_price: Optional[Decimal], logger
    ) -> tuple[bool, Optional[str]]:
        """检查价格最小范围"""
        if min_price is not None and price < min_price:
            error_msg = f"Price {price} below minimum {min_price}"
            if logger and self.enable_logging:
                logger.warning(f"⚠️  {error_msg}")
            return False, error_msg
        return True, None

    def _check_price_max_range(
        self, price: Decimal, max_price: Optional[Decimal], logger
    ) -> tuple[bool, Optional[str]]:
        """检查价格最大范围"""
        if max_price is not None and price > max_price:
            error_msg = f"Price {price} above maximum {max_price}"
            if logger and self.enable_logging:
                logger.warning(f"⚠️  {error_msg}")
            return False, error_msg
        return True, None

    def _check_price_spike(self, price: Decimal, logger) -> tuple[bool, Optional[str]]:
        """检查价格剧烈变化"""
        if self._last_valid_value is not None and self._last_valid_value > 0:
            change_pct = abs(float((price - self._last_valid_value) / self._last_valid_value))
            if change_pct > self.spike_threshold:
                error_msg = (
                    f"Price spike detected: {change_pct:.1%} change "
                    f"(from {self._last_valid_value:.2f} to {price:.2f}). "
                    f"Possible data error or circuit breaker."
                )
                if logger and self.enable_logging:
                    logger.warning(f"⚠️  {error_msg}")
                return False, error_msg
        return True, None

    def validate_price(
        self,
        price: Optional[Decimal],
        min_price: Optional[Decimal] = None,
        max_price: Optional[Decimal] = None,
        logger=None,
    ) -> tuple[bool, Optional[str]]:
        """
        验证价格数据

        Parameters
        ----------
        price : Optional[Decimal]
            价格数据
        min_price : Optional[Decimal]
            最小合理价格
        max_price : Optional[Decimal]
            最大合理价格
        logger : Logger, optional
            日志记录器

        Returns
        -------
        tuple[bool, Optional[str]]
            (是否有效, 错误信息)
        """
        # 检查 1: 数据有效性
        is_valid, error = self._check_price_validity(price, logger)
        if not is_valid:
            return False, error
        if price is None:
            return False, error

        # 检查 2: 价格最小范围
        is_valid, error = self._check_price_min_range(price, min_price, logger)
        if not is_valid:
            return False, error

        # 检查 3: 价格最大范围
        is_valid, error = self._check_price_max_range(price, max_price, logger)
        if not is_valid:
            return False, error

        # 检查 4: 剧烈变化检测
        is_valid, error = self._check_price_spike(price, logger)
        if not is_valid:
            return False, error

        # 数据通过验证
        self._last_valid_value = price
        return True, None

    def reset(self):
        """重置验证器状态"""
        self._last_valid_value = None


def _check_file_exists(file_path: Path, file_type: str, logger) -> tuple[bool, Optional[str]]:
    """检查文件是否存在"""
    if not file_path.exists():
        error_msg = f"{file_type}数据文件不存在: {file_path}"
        if logger:
            logger.error(error_msg)
        return False, error_msg
    return True, None


def _detect_time_column(
    df: pd.DataFrame, file_path: Path, file_type: str, logger
) -> tuple[Optional[str], Optional[str]]:
    """检测数据框中的时间列"""
    time_cols = ["timestamp", "datetime", "time", "date"]
    for col in time_cols:
        if col in df.columns:
            return col, None

    error_msg = f"{file_type}数据缺少时间列: {file_path}"
    if logger:
        logger.error(error_msg)
    return None, error_msg


def _calculate_alignment_stats(
    primary_timestamps: set, secondary_timestamps: set
) -> tuple[int, int, int, float]:
    """计算对齐统计信息"""
    common_timestamps = primary_timestamps & secondary_timestamps
    primary_count = len(primary_timestamps)
    secondary_count = len(secondary_timestamps)
    common_count = len(common_timestamps)
    alignment_rate = common_count / primary_count if primary_count > 0 else 0.0
    return primary_count, secondary_count, common_count, alignment_rate


def _log_alignment_info(
    logger, primary_count: int, secondary_count: int, common_count: int, alignment_rate: float
) -> None:
    """记录对齐信息"""
    if logger:
        logger.info(
            f"数据对齐检查: "
            f"主标的={primary_count}条, "
            f"辅助标的={secondary_count}条, "
            f"共同={common_count}条, "
            f"对齐率={alignment_rate:.1%}"
        )


def _check_alignment_threshold(
    alignment_rate: float,
    min_alignment_rate: float,
    primary_csv: Path,
    secondary_csv: Path,
    primary_count: int,
    secondary_count: int,
    common_count: int,
    logger,
) -> tuple[bool, Optional[str]]:
    """检查对齐率是否达到阈值"""
    if alignment_rate < min_alignment_rate:
        error_msg = (
            f"数据对齐率过低: {alignment_rate:.1%} < {min_alignment_rate:.1%}\n"
            f"主标的: {primary_csv.name} ({primary_count}条)\n"
            f"辅助标的: {secondary_csv.name} ({secondary_count}条)\n"
            f"共同时间戳: {common_count}条\n"
            f"建议: 检查数据源或重新下载数据"
        )
        if logger:
            logger.warning(f"⚠️  {error_msg}")
        return False, error_msg

    if logger:
        logger.info(f"✅ 数据对齐验证通过: {alignment_rate:.1%}")
    return True, None


def _normalize_timeframe_for_filename(timeframe: str) -> str:
    """将不同时间框架格式归一化为 CSV 文件命名使用的格式。"""
    if not timeframe:
        return "1d"

    tf = timeframe.strip().lower()

    # 已是常见格式: 1m / 1h / 1d
    if "-" not in tf and tf[-1:] in {"m", "h", "d"}:
        return tf

    # 兼容 Nautilus 风格: 1-DAY / 4-HOUR / 15-MINUTE
    if "-" in tf:
        parts = [p for p in tf.split("-") if p]
        if len(parts) >= 2 and parts[0].isdigit():
            unit_map = {"minute": "m", "hour": "h", "day": "d"}
            unit = unit_map.get(parts[1])
            if unit:
                return f"{parts[0]}{unit}"

    return tf


def _normalize_raw_symbol(symbol_or_instrument: str) -> str:
    """将 symbol / instrument_id 归一化为 raw CSV 目录使用的 symbol。"""
    raw = (symbol_or_instrument or "").strip().upper()
    if "." in raw:
        raw = raw.split(".", 1)[0]
    if ":" in raw:
        raw = raw.split(":", 1)[0]

    try:
        return normalize_symbol_to_internal(raw)
    except Exception:
        return raw.replace("/", "")


def _resolve_alignment_csv_path(
    base_dir: Path,
    symbol_or_instrument: str,
    venue: str,
    timeframe: str,
    start_date: str,
    end_date: str,
) -> Path:
    """解析多标对齐检查所需 CSV 路径，优先精确匹配，其次选可覆盖区间文件。"""
    normalized_tf = _normalize_timeframe_for_filename(timeframe)
    symbol = _normalize_raw_symbol(symbol_or_instrument)

    symbol_dir = Path(base_dir) / "data" / "raw" / symbol
    expected = symbol_dir / f"{venue.lower()}-{symbol}-{normalized_tf}-{start_date}_{end_date}.csv"
    if expected.exists():
        return expected

    # 回退：选择同 symbol/timeframe 下能覆盖目标日期区间的 CSV
    candidates = sorted(symbol_dir.glob(f"{venue.lower()}-{symbol}-{normalized_tf}-*.csv"))
    if not candidates:
        return expected

    req_start = datetime.strptime(start_date, "%Y-%m-%d").date()
    req_end = datetime.strptime(end_date, "%Y-%m-%d").date()

    covering_files = []
    for candidate in candidates:
        parsed = FilenameParser.parse(candidate.name)
        if parsed is None:
            continue
        try:
            file_start = datetime.strptime(parsed.start_date, "%Y-%m-%d").date()
            file_end = datetime.strptime(parsed.end_date, "%Y-%m-%d").date()
        except ValueError:
            continue

        if file_start <= req_start and file_end >= req_end:
            range_days = (file_end - file_start).days
            covering_files.append((range_days, candidate))

    if covering_files:
        covering_files.sort(key=lambda x: x[0])
        return covering_files[0][1]

    return expected


def validate_multi_instrument_alignment(
    primary_csv: Path, secondary_csv: Path, min_alignment_rate: float = 0.95, logger=None
) -> tuple[bool, Optional[str]]:
    """
    验证多标的数据时间戳对齐

    用于检查策略需要的多个标的数据是否时间同步，防止未来函数。
    例如：DK_Alpha_Trend策略需要主标的(ETH)和BTC数据对齐。

    Parameters
    ----------
    primary_csv : Path
        主标的CSV文件路径
    secondary_csv : Path
        辅助标的CSV文件路径（如BTC）
    min_alignment_rate : float
        最小对齐率阈值（默认95%）
    logger : Logger, optional
        日志记录器

    Returns
    -------
    tuple[bool, Optional[str]]
        (是否对齐, 错误信息)

    Examples
    --------
    >>> is_aligned, error = validate_multi_instrument_alignment(
    ...     Path("data/raw/ETHUSDT-PERP_1-DAY.csv"),
    ...     Path("data/raw/BTCUSDT-PERP_1-DAY.csv")
    ... )
    >>> if not is_aligned:
    ...     print(f"数据对齐问题: {error}")
    """
    try:
        # 检查文件存在性
        exists, error = _check_file_exists(primary_csv, "主标的", logger)
        if not exists:
            return False, error

        exists, error = _check_file_exists(secondary_csv, "辅助标的", logger)
        if not exists:
            return False, error

        # 加载数据
        primary_df = pd.read_csv(primary_csv)
        secondary_df = pd.read_csv(secondary_csv)

        # 检测时间列
        primary_time_col, error = _detect_time_column(primary_df, primary_csv, "主标的", logger)
        if error:
            return False, error

        secondary_time_col, error = _detect_time_column(
            secondary_df, secondary_csv, "辅助标的", logger
        )
        if error:
            return False, error

        # 提取时间戳集合
        primary_timestamps = set(primary_df[primary_time_col])
        secondary_timestamps = set(secondary_df[secondary_time_col])

        # 计算对齐统计
        primary_count, secondary_count, common_count, alignment_rate = _calculate_alignment_stats(
            primary_timestamps, secondary_timestamps
        )

        # 记录对齐信息
        _log_alignment_info(logger, primary_count, secondary_count, common_count, alignment_rate)

        # 检查对齐率阈值
        return _check_alignment_threshold(
            alignment_rate,
            min_alignment_rate,
            primary_csv,
            secondary_csv,
            primary_count,
            secondary_count,
            common_count,
            logger,
        )

    except Exception as e:
        error_msg = f"数据对齐验证失败: {e}"
        if logger:
            logger.error(error_msg)
        return False, error_msg


def prepare_data_feeds(args, adapter, base_dir, universe_symbols: set):
    """准备数据流（验证或获取）"""
    from utils.data_file_checker import check_single_data_file

    from .data_manager import run_batch_data_retrieval

    if args.skip_data_check:
        tui = get_tui()
        if is_tui_enabled():
            tui.add_log("Skipping data validation", "INFO")
        else:
            logger.info("⏩ Skipping data validation")
        return

    tui = get_tui()
    use_tui = is_tui_enabled()

    if use_tui:
        tui.start_phase("Data Validation", total=None)
    else:
        logger.info("📊 Data Validation")

    venue = adapter.get_venue().lower()
    start_date = adapter.get_start_date()
    end_date = adapter.get_end_date()
    timeframe = adapter.get_main_timeframe()

    # 从策略配置获取交易对象列表
    symbols_to_check = universe_symbols if universe_symbols else set(adapter._get_trading_symbols())

    if use_tui:
        tui.start_phase("Checking Data Files", total=len(symbols_to_check))

    missing_symbols = []
    strategy_name = adapter.get_strategy_name()
    for idx, symbol in enumerate(symbols_to_check, 1):
        exists, _ = check_single_data_file(
            symbol.split(":")[0],
            start_date,
            end_date,
            timeframe,
            venue,
            base_dir,
            strategy_name=strategy_name,
        )
        if not exists:
            missing_symbols.append(symbol.split(":")[0])

        if use_tui:
            tui.update_progress(description=f"Checking {symbol.split(':')[0]}...")

    if missing_symbols:
        if use_tui:
            tui.add_log(f"{len(missing_symbols)} symbols need data", "INFO")
            tui.start_phase("Fetching Missing Data", total=len(missing_symbols))
        else:
            logger.info(f"📥 {len(missing_symbols)} symbols need data")

        run_batch_data_retrieval(missing_symbols, start_date, end_date, timeframe, venue, base_dir)
    else:
        if use_tui:
            tui.add_log("All data files present", "INFO")
        else:
            logger.info("✅ All data files present")

    # 检查多标的数据对齐（如果策略需要）
    _check_multi_instrument_alignment(adapter, base_dir, venue, timeframe)


def _check_multi_instrument_alignment(adapter, base_dir: Path, venue: str, timeframe: str):
    """检查多标的数据对齐（如果策略需要）"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        # 获取策略配置
        config = adapter.build_backtest_config()
        strategy_params = (
            config.strategy.params if hasattr(config.strategy, "params") else config.strategy
        )

        # 检查是否有辅助标的配置（如 btc_instrument_id）
        btc_instrument_id = getattr(strategy_params, "btc_instrument_id", None)
        if not btc_instrument_id:
            return  # 策略不需要多标的对齐检查

        # 提取主标的和BTC标的的symbol
        symbols = adapter._get_trading_symbols()
        primary_symbol = symbols[0].split(":")[0] if symbols else None
        if not primary_symbol:
            return
        btc_symbol = btc_instrument_id.split(".")[0] if "." in btc_instrument_id else "BTCUSDT-PERP"

        # 构建 CSV 文件路径（遵循 data/raw/{symbol}/{exchange}-{symbol}-{tf}-{start}_{end}.csv）
        start_date = adapter.get_start_date()
        end_date = adapter.get_end_date()
        primary_csv = _resolve_alignment_csv_path(
            base_dir, primary_symbol, venue, timeframe, start_date, end_date
        )
        btc_csv = _resolve_alignment_csv_path(
            base_dir, btc_symbol, venue, timeframe, start_date, end_date
        )

        # 执行对齐检查
        tui = get_tui()
        use_tui = is_tui_enabled()

        if use_tui:
            tui.add_log(f"检查多标的数据对齐: {primary_symbol} vs {btc_symbol}", "INFO")
        else:
            logger.info(f"🔍 检查多标的数据对齐: {primary_symbol} vs {btc_symbol}")

        is_aligned, error_msg = validate_multi_instrument_alignment(
            primary_csv, btc_csv, min_alignment_rate=0.95, logger=logger
        )

        if not is_aligned:
            if use_tui:
                tui.add_log(f"数据对齐警告: {error_msg}", "ERROR")
                tui.add_log("建议: 检查数据源或重新下载数据", "INFO")
            else:
                logger.error(f"⚠️  数据对齐警告: {error_msg}")
                logger.info("   建议: 检查数据源或重新下载数据")
        else:
            if use_tui:
                tui.add_log("数据对齐验证通过", "INFO")
            else:
                logger.info("✅ 数据对齐验证通过")

    except Exception as e:
        tui = get_tui()
        if is_tui_enabled():
            tui.add_log(f"多标的对齐检查失败: {e}", "WARNING")
        else:
            logger.warning(f"多标的对齐检查失败: {e}")
