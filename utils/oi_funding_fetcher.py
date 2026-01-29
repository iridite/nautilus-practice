"""
Open Interest 和 Funding Rate 数据获取工具

支持从 Binance 和 OKX 交易所获取持仓量和资金费率历史数据。
数据将与 OHLCV 数据对齐，用于回测和实时交易。
"""

import time
from pathlib import Path
from typing import List, Literal

import ccxt
import pandas as pd
from tqdm import tqdm

from utils.network import retry_fetch
from utils.time_helpers import get_ms_timestamp


def fetch_binance_oi_history(
    exchange: ccxt.binance,
    symbol: str,
    start_ms: int,
    end_ms: int,
    period: str = "1h",
) -> pd.DataFrame:
    """
    获取 Binance 永续合约持仓量历史数据

    Parameters
    ----------
    exchange : ccxt.binance
        CCXT Binance 交易所实例
    symbol : str
        交易对符号（如 "BTC/USDT:USDT"）
    start_ms : int
        开始时间戳（毫秒）
    end_ms : int
        结束时间戳（毫秒）
    period : str
        时间周期（"5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"）

    Returns
    -------
    pd.DataFrame
        包含 timestamp, open_interest 列的数据框
    """
    # Binance API 限制：每次最多返回 500 条数据
    all_data = []
    current_start = start_ms

    while current_start < end_ms:
        try:
            # Binance OI History API 参数
            params = {
                "symbol": symbol.replace("/", "").replace(":USDT", ""),
                "period": period,
                "startTime": current_start,
                "limit": 500,
            }

            # 使用 fapiDataGetOpenInterestHist
            response = retry_fetch(
                exchange.fapiDataGetOpenInterestHist,
                params=params,
            )

            if not response:
                break

            for item in response:
                all_data.append(
                    {
                        "timestamp": int(item["timestamp"]),
                        "open_interest": float(item["sumOpenInterest"]),
                        "open_interest_value": float(item["sumOpenInterestValue"]),
                    }
                )

            if len(response) < 500:
                break

            # 更新下一个批次的起始时间
            current_start = all_data[-1]["timestamp"] + _period_to_ms(period)
            time.sleep(exchange.rateLimit / 1000)

        except Exception as e:
            print(f"Warning: Error fetching OI data: {e}")
            break

    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def fetch_okx_oi_history(
    exchange: ccxt.okx, symbol: str, start_ms: int, end_ms: int, period: str = "1H"
) -> pd.DataFrame:
    """
    获取 OKX 永续合约持仓量历史数据

    Parameters
    ----------
    exchange : ccxt.okx
        CCXT OKX 交易所实例
    symbol : str
        交易对符号（如 "BTC/USDT:USDT"）
    start_ms : int
        开始时间戳（毫秒）
    end_ms : int
        结束时间戳（毫秒）
    period : str
        时间周期（"5m", "15m", "30m", "1H", "2H", "4H"）

    Returns
    -------
    pd.DataFrame
        包含 timestamp, open_interest 列的数据框
    """
    # OKX API 限制：每次最多返回 100 条数据
    all_data = []
    current_end = end_ms

    # OKX 的 instId 格式
    inst_id = symbol.replace("/", "-")

    while current_end > start_ms:
        try:
            params = {
                "instId": inst_id,
                "period": period,
                "end": str(current_end),
                "limit": "100",
            }

            response = retry_fetch(
                exchange.publicGetRubikStatContractsOpenInterestHistory,
                params=params,
            )

            if not response or "data" not in response:
                break

            data_list = response["data"]
            if not data_list:
                break

            for item in data_list:
                ts = int(item["ts"])
                if ts >= start_ms:
                    all_data.append(
                        {
                            "timestamp": ts,
                            "open_interest": float(item["oi"]),
                            "open_interest_value": float(item["oiVol"]),
                        }
                    )

            if len(data_list) < 100:
                break

            # 更新下一个批次的结束时间（OKX 是倒序获取）
            current_end = int(data_list[-1]["ts"]) - 1
            time.sleep(exchange.rateLimit / 1000)

        except Exception as e:
            print(f"Warning: Error fetching OKX OI data: {e}")
            break

    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def fetch_binance_funding_rate_history(
    exchange: ccxt.binance, symbol: str, start_ms: int, end_ms: int
) -> pd.DataFrame:
    """
    获取 Binance 永续合约资金费率历史数据

    Parameters
    ----------
    exchange : ccxt.binance
        CCXT Binance 交易所实例
    symbol : str
        交易对符号（如 "BTC/USDT:USDT"）
    start_ms : int
        开始时间戳（毫秒）
    end_ms : int
        结束时间戳（毫秒）

    Returns
    -------
    pd.DataFrame
        包含 timestamp, funding_rate 列的数据框
    """
    all_data = []
    current_start = start_ms

    clean_symbol = symbol.replace("/", "").replace(":USDT", "")

    while current_start < end_ms:
        try:
            params = {
                "symbol": clean_symbol,
                "startTime": current_start,
                "endTime": end_ms,
                "limit": 1000,
            }

            response = retry_fetch(exchange.fapiPublicGetFundingRate, params=params)

            if not response:
                break

            for item in response:
                all_data.append(
                    {
                        "timestamp": int(item["fundingTime"]),
                        "funding_rate": float(item["fundingRate"]),
                    }
                )

            if len(response) < 1000:
                break

            # 资金费率每 8 小时一次
            current_start = all_data[-1]["timestamp"] + 8 * 3600 * 1000
            time.sleep(exchange.rateLimit / 1000)

        except Exception as e:
            print(f"Warning: Error fetching funding rate data: {e}")
            break

    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df["funding_rate_annual"] = df["funding_rate"] * 3 * 365 * 100  # 年化百分比
    return df


def fetch_okx_funding_rate_history(
    exchange: ccxt.okx, symbol: str, start_ms: int, end_ms: int
) -> pd.DataFrame:
    """
    获取 OKX 永续合约资金费率历史数据

    Parameters
    ----------
    exchange : ccxt.okx
        CCXT OKX 交易所实例
    symbol : str
        交易对符号（如 "BTC/USDT:USDT"）
    start_ms : int
        开始时间戳（毫秒）
    end_ms : int
        结束时间戳（毫秒）

    Returns
    -------
    pd.DataFrame
        包含 timestamp, funding_rate 列的数据框
    """
    all_data = []
    current_end = end_ms

    inst_id = symbol.replace("/", "-")

    while current_end > start_ms:
        try:
            params = {
                "instId": inst_id,
                "before": str(current_end),
                "limit": "100",
            }

            response = retry_fetch(
                exchange.publicGetPublicFundingRateHistory, params=params
            )

            if not response or "data" not in response:
                break

            data_list = response["data"]
            if not data_list:
                break

            for item in data_list:
                ts = int(item["fundingTime"])
                if ts >= start_ms:
                    all_data.append(
                        {
                            "timestamp": ts,
                            "funding_rate": float(item["fundingRate"]),
                            "realized_rate": float(item.get("realizedRate", 0)),
                        }
                    )

            if len(data_list) < 100:
                break

            current_end = int(data_list[-1]["fundingTime"]) - 1
            time.sleep(exchange.rateLimit / 1000)

        except Exception as e:
            print(f"Warning: Error fetching OKX funding rate data: {e}")
            break

    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df["funding_rate_annual"] = df["funding_rate"] * 3 * 365 * 100  # 年化百分比
    return df


def _period_to_ms(period: str) -> int:
    """将时间周期转换为毫秒"""
    unit = period[-1].lower()
    value = int(period[:-1]) if len(period) > 1 else 1

    if unit == "m":
        return value * 60 * 1000
    elif unit == "h":
        return value * 3600 * 1000
    elif unit == "d":
        return value * 24 * 3600 * 1000
    else:
        return 3600 * 1000  # 默认 1 小时


def align_oi_with_ohlcv(
    oi_df: pd.DataFrame, ohlcv_df: pd.DataFrame, method: str = "ffill"
) -> pd.DataFrame:
    """
    将 OI 数据与 OHLCV 数据对齐

    Parameters
    ----------
    oi_df : pd.DataFrame
        持仓量数据框（需包含 timestamp 列）
    ohlcv_df : pd.DataFrame
        OHLCV 数据框（需包含 timestamp 列）
    method : str
        对齐方法（"ffill" 前向填充 或 "interpolate" 线性插值）

    Returns
    -------
    pd.DataFrame
        对齐后的数据框
    """
    if oi_df.empty or ohlcv_df.empty:
        return pd.DataFrame()

    # 设置索引为时间戳
    oi_indexed = oi_df.set_index("timestamp")
    ohlcv_indexed = ohlcv_df.set_index("timestamp")

    # 合并数据（以 OHLCV 时间戳为准）
    merged = ohlcv_indexed.join(oi_indexed, how="left", rsuffix="_oi")

    # 填充缺失值
    if method == "ffill":
        merged["open_interest"] = merged["open_interest"].ffill()
        merged["open_interest_value"] = merged["open_interest_value"].ffill()
    elif method == "interpolate":
        merged["open_interest"] = merged["open_interest"].interpolate(method="linear")
        merged["open_interest_value"] = merged["open_interest_value"].interpolate(
            method="linear"
        )

    # 重置索引
    merged = merged.reset_index()

    return merged


def align_funding_with_ohlcv(
    funding_df: pd.DataFrame, ohlcv_df: pd.DataFrame
) -> pd.DataFrame:
    """
    将 Funding Rate 数据与 OHLCV 数据对齐

    资金费率每 8 小时更新一次，需要前向填充到每个 Bar

    Parameters
    ----------
    funding_df : pd.DataFrame
        资金费率数据框（需包含 timestamp 列）
    ohlcv_df : pd.DataFrame
        OHLCV 数据框（需包含 timestamp 列）

    Returns
    -------
    pd.DataFrame
        对齐后的数据框
    """
    if funding_df.empty or ohlcv_df.empty:
        return pd.DataFrame()

    # 设置索引为时间戳
    funding_indexed = funding_df.set_index("timestamp")
    ohlcv_indexed = ohlcv_df.set_index("timestamp")

    # 合并数据（以 OHLCV 时间戳为准）
    merged = ohlcv_indexed.join(funding_indexed, how="left", rsuffix="_fr")

    # 前向填充资金费率
    merged["funding_rate"] = merged["funding_rate"].ffill()
    merged["funding_rate_annual"] = merged["funding_rate_annual"].ffill()

    # 重置索引
    merged = merged.reset_index()

    return merged


def batch_fetch_oi_and_funding(
    symbols: List[str],
    start_date: str,
    end_date: str,
    exchange_id: Literal["binance", "okx"] = "binance",
    base_dir: Path = Path("."),
    oi_period: str = "1h",
) -> dict:
    """
    批量获取 OI 和 Funding Rate 数据

    Parameters
    ----------
    symbols : List[str]
        交易对列表（如 ["BTCUSDT", "ETHUSDT"]）
    start_date : str
        开始日期（YYYY-MM-DD）
    end_date : str
        结束日期（YYYY-MM-DD）
    exchange_id : str
        交易所 ID（"binance" 或 "okx"）
    base_dir : Path
        基础目录
    oi_period : str
        OI 数据周期

    Returns
    -------
    dict
        包含文件路径的字典
    """
    # 初始化交易所
    exchange_class = getattr(ccxt, exchange_id.lower())
    exchange = exchange_class(
        {"enableRateLimit": True, "options": {"defaultType": "swap"}}
    )
    exchange.load_markets()

    start_ms = get_ms_timestamp(start_date)
    end_ms = get_ms_timestamp(end_date)

    results = {"oi_files": [], "funding_files": []}

    with tqdm(
        symbols,
        desc=f"📊 Fetching OI/Funding from {exchange_id.upper()}",
        unit="symbol",
    ) as pbar:
        for raw_symbol in pbar:
            pbar.set_postfix_str(f"{raw_symbol}", refresh=True)

            # 构建 CCXT 符号
            if raw_symbol.upper().endswith("USDT"):
                base = raw_symbol.upper().replace("USDT", "")
                ccxt_symbol = f"{base}/USDT:USDT"
            else:
                ccxt_symbol = raw_symbol

            safe_symbol = raw_symbol.replace("/", "")

            # === 获取 OI 数据 ===
            oi_filename = f"{exchange_id}-{safe_symbol}-oi-{oi_period}-{start_date}_{end_date}.csv"
            oi_path = base_dir / "data" / "raw" / safe_symbol / oi_filename

            if not (oi_path.exists() and oi_path.stat().st_size > 1024):
                if exchange_id == "binance":
                    oi_df = fetch_binance_oi_history(
                        exchange, ccxt_symbol, start_ms, end_ms, oi_period
                    )
                elif exchange_id == "okx":
                    oi_df = fetch_okx_oi_history(
                        exchange, ccxt_symbol, start_ms, end_ms, oi_period.upper()
                    )
                else:
                    continue

                if not oi_df.empty:
                    oi_path.parent.mkdir(parents=True, exist_ok=True)
                    oi_df.to_csv(oi_path, index=False)
                    results["oi_files"].append(str(oi_path))

            # === 获取 Funding Rate 数据 ===
            funding_filename = (
                f"{exchange_id}-{safe_symbol}-funding-{start_date}_{end_date}.csv"
            )
            funding_path = base_dir / "data" / "raw" / safe_symbol / funding_filename

            if not (funding_path.exists() and funding_path.stat().st_size > 1024):
                if exchange_id == "binance":
                    funding_df = fetch_binance_funding_rate_history(
                        exchange, ccxt_symbol, start_ms, end_ms
                    )
                elif exchange_id == "okx":
                    funding_df = fetch_okx_funding_rate_history(
                        exchange, ccxt_symbol, start_ms, end_ms
                    )
                else:
                    continue

                if not funding_df.empty:
                    funding_path.parent.mkdir(parents=True, exist_ok=True)
                    funding_df.to_csv(funding_path, index=False)
                    results["funding_files"].append(str(funding_path))

            time.sleep(0.2)  # 避免触发 API 限速

    print(
        f"✅ OI/Funding data retrieval complete: "
        f"{len(results['oi_files'])} OI files, "
        f"{len(results['funding_files'])} Funding files"
    )

    return results


if __name__ == "__main__":
    # 使用示例
    from pathlib import Path

    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    start = "2024-01-01"
    end = "2024-12-31"

    results = batch_fetch_oi_and_funding(
        symbols=symbols,
        start_date=start,
        end_date=end,
        exchange_id="binance",
        base_dir=Path(__file__).parent.parent,
        oi_period="1h",
    )

    print(f"Downloaded {len(results['oi_files'])} OI files")
    print(f"Downloaded {len(results['funding_files'])} Funding files")
