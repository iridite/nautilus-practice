"""
OI 和 Funding Rate 数据适配器

用于在 NautilusTrader 回测引擎中加载和处理 Open Interest 和 Funding Rate 数据。
将 CSV 格式的原始数据转换为 NautilusTrader 自定义数据类型。
"""

from decimal import Decimal
from pathlib import Path
from typing import List

import pandas as pd
from nautilus_trader.core.nautilus_pyo3 import millis_to_nanos
from nautilus_trader.model.identifiers import InstrumentId

from utils.custom_data import FundingRateData, OpenInterestData


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
        safe_symbol = symbol.replace("/", "")
        filename = f"{exchange}-{safe_symbol}-oi-{period}-{start_date}_{end_date}.csv"
        file_path = self.data_dir / safe_symbol / filename

        if not file_path.exists():
            print(f"Warning: OI data file not found: {file_path}")
            return []

        try:
            df = pd.read_csv(file_path)

            # 确保必需的列存在
            if "timestamp" not in df.columns or "open_interest" not in df.columns:
                print(f"Warning: Invalid OI data format in {file_path}")
                return []

            # 转换为 OpenInterestData 对象
            oi_data_list = []
            for _, row in df.iterrows():
                ts_ms = int(row["timestamp"])
                ts_event = millis_to_nanos(ts_ms)
                ts_init = ts_event  # 回测时假设数据获取时间与事件时间相同

                oi = Decimal(str(row["open_interest"]))

                oi_data = OpenInterestData(
                    instrument_id=instrument_id,
                    open_interest=oi,
                    ts_event=ts_event,
                    ts_init=ts_init,
                )
                oi_data_list.append(oi_data)

            print(f"✅ Loaded {len(oi_data_list)} OI data points for {symbol}")
            return oi_data_list

        except Exception as e:
            print(f"Error loading OI data from {file_path}: {e}")
            return []

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
        safe_symbol = symbol.replace("/", "")
        filename = f"{exchange}-{safe_symbol}-funding-{start_date}_{end_date}.csv"
        file_path = self.data_dir / safe_symbol / filename

        if not file_path.exists():
            print(f"Warning: Funding data file not found: {file_path}")
            return []

        try:
            df = pd.read_csv(file_path)

            # 确保必需的列存在
            if "timestamp" not in df.columns or "funding_rate" not in df.columns:
                print(f"Warning: Invalid funding data format in {file_path}")
                return []

            # 转换为 FundingRateData 对象
            funding_data_list = []
            for _, row in df.iterrows():
                ts_ms = int(row["timestamp"])
                ts_event = millis_to_nanos(ts_ms)
                ts_init = ts_event

                funding_rate = Decimal(str(row["funding_rate"]))

                # 下次资金费率结算时间（如果有的话）
                next_funding_time = None
                if "next_funding_time" in df.columns and pd.notna(
                    row["next_funding_time"]
                ):
                    next_funding_time = millis_to_nanos(int(row["next_funding_time"]))

                funding_data = FundingRateData(
                    instrument_id=instrument_id,
                    funding_rate=funding_rate,
                    next_funding_time=next_funding_time,
                    ts_event=ts_event,
                    ts_init=ts_init,
                )
                funding_data_list.append(funding_data)

            print(
                f"✅ Loaded {len(funding_data_list)} Funding Rate data points for {symbol}"
            )
            return funding_data_list

        except Exception as e:
            print(f"Error loading Funding data from {file_path}: {e}")
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

    print(f"\n📊 Custom Data Summary:")
    print(f"  OI Data Points: {len(custom_data['oi'])}")
    print(f"  Funding Rate Data Points: {len(custom_data['funding'])}")

    # 合并数据
    merged = merge_custom_data_with_bars(custom_data["oi"], custom_data["funding"])
    print(f"  Total Custom Data Points: {len(merged)}")
