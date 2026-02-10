"""
数据获取工具模块

统一的数据获取接口，支持 OHLCV、OI 和 Funding Rate 数据。
"""

import logging
import time
from pathlib import Path
from typing import List, Literal

import ccxt
import pandas as pd
from tqdm import tqdm

from core.adapter import DataConfig
from utils.network import retry_fetch
from utils.symbol_parser import parse_timeframe, resolve_symbol_and_type
from utils.time_helpers import get_ms_timestamp

logger = logging.getLogger(__name__)

# 网络请求配置
MAX_ITERATIONS = 1000  # 最大迭代次数，防止无限循环

def fetch_ohlcv_data(exchange, symbol, timeframe, since, limit_ms, source="auto"):
    """
    获取OHLCV数据，支持多数据源

    Args:
        source: 数据源 (ccxt/auto)，auto会在ccxt失败时自动切换到其他源
    """
    if source == "auto":
        try:
            return _fetch_ohlcv_ccxt(exchange, symbol, timeframe, since, limit_ms)
        except (IOError, ValueError, KeyError, ConnectionError) as e:
            logger.warning(f"CCXT fetch failed for {symbol}, falling back to DataFetcher: {e}")
            from .data_fetcher import DataFetcher
            fetcher = DataFetcher()
            df = fetcher.fetch_ohlcv(symbol, timeframe, since, limit_ms, source="auto")
            return df[df["timestamp"] < limit_ms] if not df.empty else df
    else:
        return _fetch_ohlcv_ccxt(exchange, symbol, timeframe, since, limit_ms)


def _fetch_ohlcv_ccxt(exchange, symbol, timeframe, since, limit_ms):
    all_ohlcv = []
    current_since = since
    iteration_count = 0
    while current_since < limit_ms and iteration_count < MAX_ITERATIONS:
        iteration_count += 1
        limit_param = 100 if exchange.id == "okx" else 1000
        ohlcv = retry_fetch(
            exchange.fetch_ohlcv,
            symbol,
            timeframe,
            since=current_since,
            limit=limit_param,
        )
        if not ohlcv:
            break
        new_data = [x for x in ohlcv if x[0] >= current_since]
        if not new_data:
            break
        all_ohlcv.extend(new_data)
        current_since = all_ohlcv[-1][0] + 1
        if current_since >= limit_ms:
            break
        time.sleep(exchange.rateLimit / 1000)

    if iteration_count >= MAX_ITERATIONS:
        logger.warning(f"Reached max iterations ({MAX_ITERATIONS}) for {symbol}")

    if not all_ohlcv:
        return pd.DataFrame()
    df = pd.DataFrame(
        all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    return df[df["timestamp"] < limit_ms]


def batch_fetch_ohlcv(
    symbols: List[str],
    start_date: str,
    end_date: str,
    timeframe: str,
    exchange_id: str,
    base_dir: Path,
    extra: bool = False,
    source: str = "auto",
) -> List[DataConfig]:
    """批量抓取 OHLCV 数据并返回 DataConfig 列表"""
    exchange_class = getattr(ccxt, exchange_id.lower())
    exchange = exchange_class(
        {"enableRateLimit": True, "options": {"defaultType": "future"}}
    )
    exchange.load_markets()

    start_ms = get_ms_timestamp(start_date)
    end_ms = get_ms_timestamp(end_date)
    agg, period = parse_timeframe(timeframe)

    configs = []
    total = len(symbols)
    fetched_count = 0
    skipped_count = 0

    with tqdm(
        symbols,
        desc="📥 Fetching data",
        unit="symbol",
        ncols=80,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
    ) as pbar:
        for raw_symbol in pbar:
            ccxt_symbol, market_type = resolve_symbol_and_type(raw_symbol)
            safe_symbol = raw_symbol.replace("/", "")

            filename = (
                f"{exchange.id}-{safe_symbol}-{timeframe}-{start_date}_{end_date}.csv"
            )
            relative_path = f"{safe_symbol}/{filename}"
            output_path = base_dir / "data" / "raw" / relative_path

            pbar.set_postfix_str(f"{raw_symbol}", refresh=True)

            if not (output_path.exists() and output_path.stat().st_size > 10 * 1024):
                df = fetch_ohlcv_data(
                    exchange, ccxt_symbol, timeframe, start_ms, end_ms, source=source
                )
                if not df.empty:
                    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    df.to_csv(output_path, index=False)
                    fetched_count += 1
                else:
                    continue
            else:
                skipped_count += 1

            configs.append(
                DataConfig(
                    csv_file_name=relative_path,
                    bar_aggregation=agg,
                    bar_period=period,
                    label="main" if len(symbols) == 1 else "universe",
                )
            )

    print(
        f"✅ Data retrieval complete: {len(configs)}/{total} symbols "
        f"(fetched: {fetched_count}, cached: {skipped_count})"
    )

    return configs


def fetch_binance_oi_history(
    exchange: ccxt.binance,
    symbol: str,
    start_ms: int,
    end_ms: int,
    period: str = "1h",
) -> pd.DataFrame:
    """获取 Binance 永续合约持仓量历史数据"""
    all_data = []

    try:
        params = {
            "symbol": symbol.replace("/", "").replace(":USDT", ""),
            "period": period,
            "limit": 500,
        }

        response = retry_fetch(
            exchange.fapiDataGetOpenInterestHist,
            params=params,
        )

        if not response:
            logger.warning(f"⚠️  Binance OI API: No data returned for {symbol}")
            return pd.DataFrame()

        for item in response:
            ts = int(item["timestamp"])
            if start_ms <= ts <= end_ms:
                all_data.append(
                    {
                        "timestamp": ts,
                        "open_interest": float(item["sumOpenInterest"]),
                        "open_interest_value": float(item["sumOpenInterestValue"]),
                    }
                )

        if all_data:
            oldest_ts = min(item["timestamp"] for item in all_data)
            newest_ts = max(item["timestamp"] for item in all_data)
            from datetime import datetime
            logger.info(f"ℹ️  Binance OI: Got {len(all_data)} records from {datetime.fromtimestamp(oldest_ts/1000).date()} to {datetime.fromtimestamp(newest_ts/1000).date()}")
            if oldest_ts > start_ms:
                logger.warning(f"⚠️  Warning: Requested data from {datetime.fromtimestamp(start_ms/1000).date()}, but API only provides recent ~21 days")

    except Exception as e:
        logger.error(f"❌ Error fetching Binance OI data: {e}")
        return pd.DataFrame()

    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def fetch_okx_oi_history(
    exchange: ccxt.okx, symbol: str, start_ms: int, end_ms: int, period: str = "1H"
) -> pd.DataFrame:
    """获取 OKX 永续合约持仓量历史数据"""
    all_data = []
    current_end = end_ms
    iteration_count = 0
    inst_id = symbol.replace("/", "-")

    while current_end > start_ms and iteration_count < MAX_ITERATIONS:
        iteration_count += 1
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

            current_end = int(data_list[-1]["ts"]) - 1
            time.sleep(exchange.rateLimit / 1000)

        except Exception as e:
            logger.error(f"Warning: Error fetching OKX OI data: {e}")
            break

    if iteration_count >= MAX_ITERATIONS:
        logger.warning(f"Reached max iterations ({MAX_ITERATIONS}) for OKX OI {symbol}")

    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def fetch_binance_funding_rate_history(
    exchange: ccxt.binance, symbol: str, start_ms: int, end_ms: int
) -> pd.DataFrame:
    """获取 Binance 永续合约资金费率历史数据"""
    all_data = []
    current_start = start_ms
    iteration_count = 0
    clean_symbol = symbol.replace("/", "").replace(":USDT", "")

    while current_start < end_ms and iteration_count < MAX_ITERATIONS:
        iteration_count += 1
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

            current_start = all_data[-1]["timestamp"] + 8 * 3600 * 1000
            time.sleep(exchange.rateLimit / 1000)

        except Exception as e:
            logger.error(f"Warning: Error fetching funding rate data: {e}")
            break

    if iteration_count >= MAX_ITERATIONS:
        logger.warning(f"Reached max iterations ({MAX_ITERATIONS}) for Binance Funding {symbol}")

    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df["funding_rate_annual"] = df["funding_rate"] * 3 * 365 * 100
    return df


def fetch_okx_funding_rate_history(
    exchange: ccxt.okx, symbol: str, start_ms: int, end_ms: int
) -> pd.DataFrame:
    """获取 OKX 永续合约资金费率历史数据"""
    all_data = []
    current_end = end_ms
    iteration_count = 0
    inst_id = symbol.replace("/", "-")

    while current_end > start_ms and iteration_count < MAX_ITERATIONS:
        iteration_count += 1
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
            logger.error(f"Warning: Error fetching OKX funding rate data: {e}")
            break

    if iteration_count >= MAX_ITERATIONS:
        logger.warning(f"Reached max iterations ({MAX_ITERATIONS}) for OKX Funding {symbol}")

    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df["funding_rate_annual"] = df["funding_rate"] * 3 * 365 * 100
    return df


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

    注意：OI 数据获取已临时禁用
    原因：第三方 API 仅提供 21 天历史数据，不符合长期回测需求
    计划：将通过本地服务持续采集和存储 OI 数据
    """

    # ⚠️ OI 数据获取已临时禁用
    # 等待本地 OI 数据采集服务设计完成后重新启用
    ENABLE_OI_FETCH = False

    exchange_class = getattr(ccxt, exchange_id.lower())
    exchange = exchange_class(
        {"enableRateLimit": True, "options": {"defaultType": "swap"}}
    )
    exchange.load_markets()

    start_ms = get_ms_timestamp(start_date)
    end_ms = get_ms_timestamp(end_date)

    results = {"oi_files": [], "funding_files": []}

    desc = f"📊 Fetching Funding from {exchange_id.upper()}" if not ENABLE_OI_FETCH else f"📊 Fetching OI/Funding from {exchange_id.upper()}"
    with tqdm(
        symbols,
        desc=desc,
        unit="symbol",
    ) as pbar:
        for raw_symbol in pbar:
            pbar.set_postfix_str(f"{raw_symbol}", refresh=True)

            # Use shared symbol resolver to get a ccxt-compatible symbol and market type
            # resolve_symbol_and_type returns (ccxt_symbol, market_type)
            ccxt_symbol, market_type = resolve_symbol_and_type(raw_symbol)

            if ccxt_symbol not in exchange.markets:
                logger.warning(f"\n[WARNING] {raw_symbol} not found in {exchange_id.upper()}, skipping")
                continue

            safe_symbol = raw_symbol.replace("/", "")

            # 获取 OI 数据（已禁用）
            if ENABLE_OI_FETCH:
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

            # 获取 Funding Rate 数据
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

            time.sleep(0.2)

    if ENABLE_OI_FETCH:
        print(
            f"✅ OI/Funding data retrieval complete: "
            f"{len(results['oi_files'])} OI files, "
            f"{len(results['funding_files'])} Funding files"
        )
    else:
        print(
            f"✅ Funding data retrieval complete: "
            f"{len(results['funding_files'])} Funding files "
            f"(OI data fetching disabled)"
        )

    return results
