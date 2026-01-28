"""
共享自定义数据加载模块

提供 OI 和 Funding Rate 数据的统一加载接口，避免代码重复。
"""

from decimal import Decimal
from pathlib import Path
from typing import List

import pandas as pd
from nautilus_trader.core.nautilus_pyo3 import millis_to_nanos

from backtest.data_validator import DataValidator
from backtest.exceptions import CustomDataError
from utils.custom_data import FundingRateData, OpenInterestData


class CustomDataLoader:
    """自定义数据加载器"""

    @staticmethod
    def load_oi_data(oi_files: List[Path], instrument_id) -> List[OpenInterestData]:
        """
        加载 Open Interest 数据（向量化优化）

        Args:
            oi_files: OI 数据文件列表
            instrument_id: 标的 ID

        Returns:
            List[OpenInterestData]: OI 数据列表
        """
        oi_data_list = []

        for oi_file in oi_files:
            try:
                df = pd.read_csv(oi_file)
                df = df.sort_values("timestamp")

                # 数据质量验证
                issues = DataValidator.validate_dataframe(
                    df, oi_file, expected_interval_ms=3_600_000
                )
                for issue in issues:
                    if issue.severity == "error":
                        raise CustomDataError(
                            f"OI data quality error: {issue.message}",
                            data_type="open_interest"
                        )

                # 向量化处理
                timestamps = df["timestamp"].astype(int).values
                oi_values = df["open_interest"].astype(str).values

                # 验证时间戳单调性
                if len(timestamps) > 1 and (timestamps[1:] < timestamps[:-1]).any():
                    print(f"⚠️ Warning: Non-monotonic timestamp in {oi_file.name}")

                # 批量创建数据对象
                for i in range(len(df)):
                    ts_event = millis_to_nanos(timestamps[i])
                    oi_data = OpenInterestData(
                        instrument_id=instrument_id,
                        open_interest=Decimal(oi_values[i]),
                        ts_event=ts_event,
                        ts_init=ts_event,
                    )
                    oi_data_list.append(oi_data)

            except CustomDataError:
                raise
            except Exception as e:
                raise CustomDataError(
                    f"Failed to load OI file {oi_file.name}: {e}",
                    data_type="open_interest",
                    cause=e
                )

        return oi_data_list

    @staticmethod
    def load_funding_data(
        funding_files: List[Path], instrument_id
    ) -> List[FundingRateData]:
        """
        加载 Funding Rate 数据（向量化优化）

        Args:
            funding_files: Funding Rate 数据文件列表
            instrument_id: 标的 ID

        Returns:
            List[FundingRateData]: Funding Rate 数据列表
        """
        funding_data_list = []

        for funding_file in funding_files:
            try:
                df = pd.read_csv(funding_file)
                df = df.sort_values("timestamp")

                # 数据质量验证
                issues = DataValidator.validate_dataframe(
                    df, funding_file, expected_interval_ms=28_800_000
                )
                for issue in issues:
                    if issue.severity == "error":
                        raise CustomDataError(
                            f"Funding data quality error: {issue.message}",
                            data_type="funding_rate"
                        )

                # 向量化处理
                timestamps = df["timestamp"].astype(int).values
                funding_values = df["funding_rate"].astype(str).values

                # 验证时间戳单调性
                if len(timestamps) > 1 and (timestamps[1:] < timestamps[:-1]).any():
                    print(f"⚠️ Warning: Non-monotonic timestamp in {funding_file.name}")

                # 批量创建数据对象
                for i in range(len(df)):
                    ts_event = millis_to_nanos(timestamps[i])
                    funding_data = FundingRateData(
                        instrument_id=instrument_id,
                        funding_rate=Decimal(funding_values[i]),
                        next_funding_time=None,
                        ts_event=ts_event,
                        ts_init=ts_event,
                    )
                    funding_data_list.append(funding_data)

            except CustomDataError:
                raise
            except Exception as e:
                raise CustomDataError(
                    f"Failed to load Funding file {funding_file.name}: {e}",
                    data_type="funding_rate",
                    cause=e
                )

        return funding_data_list
