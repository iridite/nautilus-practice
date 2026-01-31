"""
数据验证工具模块

提供通用的数据异常检测和验证功能，可被多个策略复用。
适用于 OI、Funding Rate、价格等市场数据的异常检测。
"""

from decimal import Decimal
from typing import Optional


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





def prepare_data_feeds(args, adapter, base_dir, universe_symbols: set):
    """准备数据流（验证或获取）"""
    from pathlib import Path

    from core.settings import get_adapter
    from utils.validation import check_single_data_file

    from .data_manager import run_batch_data_retrieval

    if args.skip_data_check:
        print("⏩ Skipping data validation")
        return

    print("="*70)
    print("📊 Data Validation")
    print("="*70)

    venue = adapter.get_venue().lower()
    start_date = adapter.get_start_date()
    end_date = adapter.get_end_date()
    timeframe = adapter.get_main_timeframe()

    symbols_to_check = universe_symbols if universe_symbols else {adapter.get_primary_symbol()}

    missing_symbols = []
    for symbol in symbols_to_check:
        exists, _ = check_single_data_file(
            symbol.split(":")[0], start_date, end_date, timeframe, venue, base_dir
        )
        if not exists:
            missing_symbols.append(symbol.split(":")[0])

    if missing_symbols:
        print(f"📥 {len(missing_symbols)} symbols need data")
        run_batch_data_retrieval(
            missing_symbols, start_date, end_date, timeframe, venue, base_dir
        )
    else:
        print("✅ All data files present")

    print("="*70 + "\n")
