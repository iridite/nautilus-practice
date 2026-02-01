"""
数据验证工具模块

提供通用的数据异常检测和验证功能，可被多个策略复用。
适用于 OI、Funding Rate、价格等市场数据的异常检测。
"""

import logging
from decimal import Decimal
from pathlib import Path
from typing import Optional

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

    def validate_oi(
        self, oi_value: Optional[Decimal], logger=None
    ) -> tuple[bool, Optional[str]]:
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
        # 检查 1: 数据有效性
        if oi_value is None or oi_value <= 0:
            error_msg = f"Invalid OI data: {oi_value}"
            if logger and self.enable_logging:
                logger.warning(f"⚠️  {error_msg}")
            return False, error_msg

        # 检查 2: 剧烈变化检测（换月、数据错误）
        if self._last_valid_value is not None and self._last_valid_value > 0:
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

        # 数据通过验证
        self._last_valid_value = oi_value
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
        if funding_annual is None:
            error_msg = "Invalid Funding Rate data: None"
            if logger and self.enable_logging:
                logger.warning(f"⚠️  {error_msg}")
            return False, error_msg

        # 检查 2: 异常值检测
        if abs(float(funding_annual)) > max_abs_value:
            error_msg = (
                f"Abnormal Funding Rate: {funding_annual:.2f}% (annual), "
                f"exceeds ±{max_abs_value}% threshold. Possible data error."
            )
            if logger and self.enable_logging:
                logger.warning(f"⚠️  {error_msg}")
            return False, error_msg

        # 检查 3: 剧烈变化检测
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

        # 数据通过验证
        self._last_valid_value = funding_annual
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
        if price is None or price <= 0:
            error_msg = f"Invalid price data: {price}"
            if logger and self.enable_logging:
                logger.warning(f"⚠️  {error_msg}")
            return False, error_msg

        # 检查 2: 价格范围
        if min_price is not None and price < min_price:
            error_msg = f"Price {price} below minimum {min_price}"
            if logger and self.enable_logging:
                logger.warning(f"⚠️  {error_msg}")
            return False, error_msg

        if max_price is not None and price > max_price:
            error_msg = f"Price {price} above maximum {max_price}"
            if logger and self.enable_logging:
                logger.warning(f"⚠️  {error_msg}")
            return False, error_msg

        # 检查 3: 剧烈变化检测
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

        # 数据通过验证
        self._last_valid_value = price
        return True, None

    def reset(self):
        """重置验证器状态"""
        self._last_valid_value = None


def validate_multi_instrument_alignment(
    primary_csv: Path,
    secondary_csv: Path,
    min_alignment_rate: float = 0.95,
    logger=None
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
    import pandas as pd

    try:
        # 检查文件存在性
        if not primary_csv.exists():
            error_msg = f"主标的数据文件不存在: {primary_csv}"
            if logger:
                logger.error(error_msg)
            return False, error_msg

        if not secondary_csv.exists():
            error_msg = f"辅助标的数据文件不存在: {secondary_csv}"
            if logger:
                logger.error(error_msg)
            return False, error_msg

        # 加载时间戳列（自动检测列名）
        primary_df = pd.read_csv(primary_csv)
        secondary_df = pd.read_csv(secondary_csv)

        # 检测时间列名
        time_cols = ['timestamp', 'datetime', 'time', 'date']
        primary_time_col = None
        secondary_time_col = None

        for col in time_cols:
            if col in primary_df.columns:
                primary_time_col = col
                break

        for col in time_cols:
            if col in secondary_df.columns:
                secondary_time_col = col
                break

        if not primary_time_col:
            error_msg = f"主标的数据缺少时间列: {primary_csv}"
            if logger:
                logger.error(error_msg)
            return False, error_msg

        if not secondary_time_col:
            error_msg = f"辅助标的数据缺少时间列: {secondary_csv}"
            if logger:
                logger.error(error_msg)
            return False, error_msg

        # 提取时间戳集合
        primary_timestamps = set(primary_df[primary_time_col])
        secondary_timestamps = set(secondary_df[secondary_time_col])

        # 计算对齐情况
        common_timestamps = primary_timestamps & secondary_timestamps
        primary_count = len(primary_timestamps)
        secondary_count = len(secondary_timestamps)
        common_count = len(common_timestamps)

        # 计算对齐率（基于主标的）
        alignment_rate = common_count / primary_count if primary_count > 0 else 0.0

        # 记录详细信息
        if logger:
            logger.info(
                f"数据对齐检查: "
                f"主标的={primary_count}条, "
                f"辅助标的={secondary_count}条, "
                f"共同={common_count}条, "
                f"对齐率={alignment_rate:.1%}"
            )

        # 检查对齐率
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

        # 对齐率合格
        if logger:
            logger.info(f"✅ 数据对齐验证通过: {alignment_rate:.1%}")

        return True, None

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
        logger.info("⏩ Skipping data validation")
        return

    logger.info("📊 Data Validation")

    venue = adapter.get_venue().lower()
    start_date = adapter.get_start_date()
    end_date = adapter.get_end_date()
    timeframe = adapter.get_main_timeframe()

    # 从策略配置获取交易对象列表
    symbols_to_check = universe_symbols if universe_symbols else set(adapter._get_trading_symbols())

    missing_symbols = []
    for symbol in symbols_to_check:
        exists, _ = check_single_data_file(
            symbol.split(":")[0], start_date, end_date, timeframe, venue, base_dir
        )
        if not exists:
            missing_symbols.append(symbol.split(":")[0])

    if missing_symbols:
        logger.info(f"📥 {len(missing_symbols)} symbols need data")
        run_batch_data_retrieval(
            missing_symbols, start_date, end_date, timeframe, venue, base_dir
        )
    else:
        logger.info("✅ All data files present\n")


def _check_multi_instrument_alignment(adapter, base_dir: Path, venue: str, timeframe: str):
    """检查多标的数据对齐（如果策略需要）"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        # 获取策略配置
        config = adapter.build_backtest_config()
        strategy_params = config.strategy.params if hasattr(config.strategy, 'params') else config.strategy

        # 检查是否有辅助标的配置（如 btc_instrument_id）
        btc_instrument_id = getattr(strategy_params, 'btc_instrument_id', None)
        if not btc_instrument_id:
            return  # 策略不需要多标的对齐检查

        # 提取主标的和BTC标的的symbol
        symbols = adapter._get_trading_symbols()
        primary_symbol = symbols[0].split(":")[0] if symbols else None
        if not primary_symbol:
            return
        btc_symbol = btc_instrument_id.split(".")[0] if "." in btc_instrument_id else "BTCUSDT-PERP"

        # 构建CSV文件路径
        data_dir = Path(base_dir) / "data" / "raw"
        primary_csv = data_dir / f"{primary_symbol}_{timeframe}.csv"
        btc_csv = data_dir / f"{btc_symbol}_{timeframe}.csv"

        # 执行对齐检查
        logger.debug(f"🔍 检查多标的数据对齐: {primary_symbol} vs {btc_symbol}")
        is_aligned, error_msg = validate_multi_instrument_alignment(
            primary_csv, btc_csv, min_alignment_rate=0.95, logger=logger
        )

        if not is_aligned:
            logger.error(f"⚠️  数据对齐警告: {error_msg}")
            logger.info("   建议: 检查数据源或重新下载数据")
        else:
            logger.info("✅ 数据对齐验证通过")

    except Exception as e:
        logger.warning(f"多标的对齐检查失败: {e}")
