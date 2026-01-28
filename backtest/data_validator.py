"""
数据质量验证模块

提供数据完整性、连续性和质量检查功能，防止回测偏差。
"""

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from pandas import DataFrame


class DataQualityIssue:
    """数据质量问题记录"""

    def __init__(self, severity: str, message: str, details: Optional[Dict] = None):
        self.severity = severity  # "error", "warning", "info"
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        prefix = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(self.severity, "•")
        return f"{prefix} {self.message}"


class DataValidator:
    """数据质量验证器"""

    @staticmethod
    def validate_dataframe(
        df: DataFrame,
        file_path: Optional[Path] = None,
        expected_interval_ms: Optional[int] = None,
    ) -> List[DataQualityIssue]:
        """
        验证DataFrame数据质量

        Args:
            df: 待验证的DataFrame
            file_path: 文件路径（用于错误信息）
            expected_interval_ms: 预期时间间隔（毫秒）

        Returns:
            List[DataQualityIssue]: 发现的问题列表
        """
        issues = []
        file_name = file_path.name if file_path else "data"

        # 1. 检查空数据
        if len(df) == 0:
            issues.append(DataQualityIssue("error", f"{file_name}: Empty dataset"))
            return issues

        # 2. 检查缺失值
        null_counts = df.isnull().sum()
        if null_counts.any():
            null_cols = null_counts[null_counts > 0].to_dict()
            issues.append(DataQualityIssue(
                "warning",
                f"{file_name}: Contains NaN values",
                {"columns": null_cols}
            ))

        # 3. 检查时间戳列
        time_col = None
        for col in ["timestamp", "datetime", "time"]:
            if col in df.columns:
                time_col = col
                break

        if time_col is None:
            issues.append(DataQualityIssue("error", f"{file_name}: No timestamp column found"))
            return issues

        # 4. 检查时间戳单调性
        timestamps = df[time_col].values
        if len(timestamps) > 1:
            diffs = timestamps[1:] - timestamps[:-1]
            if (diffs < 0).any():
                issues.append(DataQualityIssue(
                    "error",
                    f"{file_name}: Non-monotonic timestamps detected"
                ))

        # 5. 检查时间间隔连续性
        if expected_interval_ms and len(timestamps) > 1:
            time_diffs = timestamps[1:] - timestamps[:-1]
            gaps = time_diffs[time_diffs > expected_interval_ms * 1.5]
            if len(gaps) > 0:
                issues.append(DataQualityIssue(
                    "warning",
                    f"{file_name}: Found {len(gaps)} time gaps",
                    {"max_gap_ms": int(gaps.max()), "expected_ms": expected_interval_ms}
                ))

        # 6. 检查OHLCV数据异常值（如果存在）
        if all(col in df.columns for col in ["open", "high", "low", "close"]):
            # 检查 high >= low
            invalid_hl = df["high"] < df["low"]
            if invalid_hl.any():
                issues.append(DataQualityIssue(
                    "error",
                    f"{file_name}: Invalid OHLC (high < low)",
                    {"count": int(invalid_hl.sum())}
                ))

            # 检查价格为0或负数
            price_cols = ["open", "high", "low", "close"]
            for col in price_cols:
                if (df[col] <= 0).any():
                    issues.append(DataQualityIssue(
                        "error",
                        f"{file_name}: Invalid {col} prices (<=0)",
                        {"count": int((df[col] <= 0).sum())}
                    ))

        return issues

    @staticmethod
    def validate_time_range(
        df: DataFrame,
        start_date: Optional[str],
        end_date: Optional[str],
        time_col: str = "timestamp",
    ) -> List[DataQualityIssue]:
        """
        验证数据时间范围覆盖

        Args:
            df: DataFrame
            start_date: 期望开始日期
            end_date: 期望结束日期
            time_col: 时间列名

        Returns:
            List[DataQualityIssue]: 发现的问题列表
        """
        issues = []

        if time_col not in df.columns or len(df) == 0:
            return issues

        if start_date:
            start_ts = pd.Timestamp(start_date).value // 1_000_000  # 转为毫秒
            actual_start = df[time_col].min()
            if actual_start > start_ts:
                issues.append(DataQualityIssue(
                    "warning",
                    f"Data starts later than requested: {pd.Timestamp(actual_start, unit='ms')}"
                ))

        if end_date:
            end_ts = pd.Timestamp(end_date).value // 1_000_000
            actual_end = df[time_col].max()
            if actual_end < end_ts:
                issues.append(DataQualityIssue(
                    "warning",
                    f"Data ends earlier than requested: {pd.Timestamp(actual_end, unit='ms')}"
                ))

        return issues

    @staticmethod
    def parse_interval_from_bar_type(bar_type_str: str) -> Optional[int]:
        """
        从bar_type字符串解析时间间隔（毫秒）

        Args:
            bar_type_str: 如 "1-HOUR", "15-MINUTE"

        Returns:
            Optional[int]: 时间间隔（毫秒），解析失败返回None
        """
        try:
            parts = bar_type_str.upper().split("-")
            if len(parts) < 2:
                return None

            value = int(parts[0])
            unit = parts[1]

            multipliers = {
                "SECOND": 1000,
                "MINUTE": 60_000,
                "HOUR": 3_600_000,
                "DAY": 86_400_000,
            }

            return value * multipliers.get(unit, 0)
        except (ValueError, IndexError):
            return None
