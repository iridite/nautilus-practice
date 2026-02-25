"""
数据获取工具模块

统一的数据获取接口，支持 OHLCV、OI 和 Funding Rate 数据。
"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Literal

import ccxt
import pandas as pd
from tqdm import tqdm

from backtest.tui_manager import get_tui, is_tui_enabled
from core.adapter import DataConfig
from utils.network import retry_fetch
from utils.symbol_parser import parse_timeframe, resolve_symbol_and_type
from utils.time_helpers import get_ms_timestamp

logger = logging.getLogger(__name__)

# 网络请求配置
MAX_ITERATIONS = 1000  # 最大迭代次数，防止无限循环

# 并发下载配置
# 可通过环境变量 NAUTILUS_MAX_WORKERS 控制并发数量
# 默认值: 10 (适合大多数网络环境)
# 建议范围: 5-20 (过高可能触发交易所 API 限流)
DEFAULT_MAX_WORKERS = int(os.getenv("NAUTILUS_MAX_WORKERS", "10"))


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


def _get_exchange_limit_param(exchange) -> int:
    """获取交易所特定的数据限制参数"""
    return 100 if exchange.id == "okx" else 1000


def _filter_new_ohlcv_data(ohlcv: list, current_since: int) -> list:
    """过滤出新的OHLCV数据（时间戳>=current_since）"""
    return [x for x in ohlcv if x[0] >= current_since]


def _convert_ohlcv_to_dataframe(all_ohlcv: list, limit_ms: int) -> pd.DataFrame:
    """将OHLCV数据列表转换为DataFrame并过滤时间范围"""
    if not all_ohlcv:
        return pd.DataFrame()
    df = pd.DataFrame(all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    return df[df["timestamp"] < limit_ms]


def _fetch_ohlcv_ccxt(exchange, symbol, timeframe, since, limit_ms):
    all_ohlcv = []
    current_since = since
    iteration_count = 0

    while current_since < limit_ms and iteration_count < MAX_ITERATIONS:
        iteration_count += 1
        limit_param = _get_exchange_limit_param(exchange)
        ohlcv = retry_fetch(
            exchange.fetch_ohlcv,
            symbol,
            timeframe,
            since=current_since,
            limit=limit_param,
        )

        if not ohlcv:
            break

        new_data = _filter_new_ohlcv_data(ohlcv, current_since)
        if not new_data:
            break

        all_ohlcv.extend(new_data)
        current_since = all_ohlcv[-1][0] + 1

        if current_since >= limit_ms:
            break

        time.sleep(exchange.rateLimit / 1000)

    if iteration_count >= MAX_ITERATIONS:
        logger.warning(f"Reached max iterations ({MAX_ITERATIONS}) for {symbol}")

    return _convert_ohlcv_to_dataframe(all_ohlcv, limit_ms)


def _fetch_single_symbol(
    raw_symbol: str,
    exchange_id: str,
    timeframe: str,
    start_ms: int,
    end_ms: int,
    base_dir: Path,
    start_date: str,
    end_date: str,
    agg,
    period: int,
    source: str,
    is_single: bool,
) -> tuple:
    """
    获取单个交易对的数据

    Returns:
        (DataConfig | None, status): DataConfig对象和状态信息
        status: 'fetched', 'cached', 'skipped', 'error'
    """
    # 每个线程创建自己的 exchange 实例以避免线程安全问题
    exchange_class = getattr(ccxt, exchange_id.lower())
    exchange = exchange_class({"enableRateLimit": True, "options": {"defaultType": "future"}})

    try:
        ccxt_symbol, market_type = resolve_symbol_and_type(raw_symbol)
    except Exception as e:
        tui = get_tui()
        if is_tui_enabled():
            tui.add_log(f"Failed to parse symbol {raw_symbol}: {e}, skipping", "WARNING")
        else:
            logger.warning(f"Failed to parse symbol {raw_symbol}: {e}, skipping")
        return None, "skipped"

    safe_symbol = raw_symbol.replace("/", "")
    filename = f"{exchange.id}-{safe_symbol}-{timeframe}-{start_date}_{end_date}.csv"
    relative_path = f"{safe_symbol}/{filename}"
    output_path = base_dir / "data" / "raw" / relative_path

    # 检查缓存
    if output_path.exists() and output_path.stat().st_size > 10 * 1024:
        config = DataConfig(
            csv_file_name=relative_path,
            bar_aggregation=agg,
            bar_period=period,
            label="main" if is_single else "universe",
        )
        return config, "cached"

    # 下载数据
    try:
        df = fetch_ohlcv_data(exchange, ccxt_symbol, timeframe, start_ms, end_ms, source=source)
        if not df.empty:
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(output_path, index=False)

            config = DataConfig(
                csv_file_name=relative_path,
                bar_aggregation=agg,
                bar_period=period,
                label="main" if is_single else "universe",
            )
            return config, "fetched"
        else:
            return None, "error"
    except Exception as e:
        logger.warning(f"Error fetching {raw_symbol}: {e}")
        return None, "error"


def batch_fetch_ohlcv(
    symbols: List[str],
    start_date: str,
    end_date: str,
    timeframe: str,
    exchange_id: str,
    base_dir: Path,
    extra: bool = False,
    source: str = "auto",
    max_workers: int = None,
) -> List[DataConfig]:
    """
    批量抓取 OHLCV 数据并返回 DataConfig 列表

    Args:
        max_workers: 并发下载的最大线程数，默认从环境变量 NAUTILUS_MAX_WORKERS 读取（默认10）
    """
    if max_workers is None:
        max_workers = DEFAULT_MAX_WORKERS

    start_ms = get_ms_timestamp(start_date)
    end_ms = get_ms_timestamp(end_date)
    agg, period = parse_timeframe(timeframe)

    configs = []
    total = len(symbols)
    fetched_count = 0
    cached_count = 0
    skipped_count = 0
    is_single = len(symbols) == 1

    tui = get_tui()
    use_tui = is_tui_enabled()

    if use_tui:
        # 使用 TUI 显示进度
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有下载任务
            future_to_symbol = {
                executor.submit(
                    _fetch_single_symbol,
                    raw_symbol,
                    exchange_id,
                    timeframe,
                    start_ms,
                    end_ms,
                    base_dir,
                    start_date,
                    end_date,
                    agg,
                    period,
                    source,
                    is_single,
                ): raw_symbol
                for raw_symbol in symbols
            }

            # 处理完成的任务
            for future in as_completed(future_to_symbol):
                raw_symbol = future_to_symbol[future]
                try:
                    config, status = future.result()
                    if config:
                        configs.append(config)

                    if status == "fetched":
                        fetched_count += 1
                    elif status == "cached":
                        cached_count += 1
                    elif status == "skipped":
                        skipped_count += 1

                    tui.update_progress(description=f"Downloading {raw_symbol}...")
                    tui.update_stat("fetched", fetched_count)
                    tui.update_stat("cached", cached_count)
                    tui.update_stat("skipped", skipped_count)
                except Exception as e:
                    logger.error(f"Error processing {raw_symbol}: {e}")
                    tui.add_log(f"Error: {raw_symbol}", "ERROR")
                    skipped_count += 1
                    tui.update_stat("skipped", skipped_count)
    else:
        # 使用 tqdm 进度条（传统模式）
        with tqdm(
            total=total,
            desc="📥 Fetching data",
            unit="symbol",
            ncols=80,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
        ) as pbar:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有下载任务
                future_to_symbol = {
                    executor.submit(
                        _fetch_single_symbol,
                        raw_symbol,
                        exchange_id,
                        timeframe,
                        start_ms,
                        end_ms,
                        base_dir,
                        start_date,
                        end_date,
                        agg,
                        period,
                        source,
                        is_single,
                    ): raw_symbol
                    for raw_symbol in symbols
                }

                # 处理完成的任务
                for future in as_completed(future_to_symbol):
                    raw_symbol = future_to_symbol[future]
                    try:
                        config, status = future.result()
                        if config:
                            configs.append(config)

                        if status == "fetched":
                            fetched_count += 1
                        elif status == "cached":
                            cached_count += 1
                        elif status == "skipped":
                            skipped_count += 1

                        pbar.set_postfix_str(f"{raw_symbol}", refresh=True)
                        pbar.update(1)
                    except Exception as e:
                        logger.error(f"Error processing {raw_symbol}: {e}")
                        skipped_count += 1
                        pbar.update(1)

    logger.info(
        f"Data retrieval complete: {len(configs)}/{total} symbols "
        f"(fetched: {fetched_count}, cached: {cached_count}, skipped: {skipped_count})"
    )

    return configs


def _build_binance_oi_params(symbol: str, period: str) -> dict:
    """构建Binance OI API请求参数"""
    return {
        "symbol": symbol.replace("/", "").replace(":USDT", ""),
        "period": period,
        "limit": 500,
    }


def _parse_binance_oi_item(item: dict, start_ms: int, end_ms: int) -> dict:
    """解析单个Binance OI数据项"""
    ts = int(item["timestamp"])
    if start_ms <= ts <= end_ms:
        return {
            "timestamp": ts,
            "open_interest": float(item["sumOpenInterest"]),
            "open_interest_value": float(item["sumOpenInterestValue"]),
        }
    return None


def _log_binance_oi_data_range(all_data: list, start_ms: int):
    """记录Binance OI数据范围信息"""
    from datetime import datetime

    oldest_ts = min(item["timestamp"] for item in all_data)
    newest_ts = max(item["timestamp"] for item in all_data)

    logger.info(
        f"ℹ️  Binance OI: Got {len(all_data)} records from "
        f"{datetime.fromtimestamp(oldest_ts / 1000).date()} to "
        f"{datetime.fromtimestamp(newest_ts / 1000).date()}"
    )

    if oldest_ts > start_ms:
        logger.warning(
            f"⚠️  Warning: Requested data from {datetime.fromtimestamp(start_ms / 1000).date()}, "
            f"but API only provides recent ~21 days"
        )


def _finalize_binance_oi_dataframe(all_data: list) -> pd.DataFrame:
    """将Binance OI数据列表转换为DataFrame"""
    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


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
        params = _build_binance_oi_params(symbol, period)
        response = retry_fetch(
            exchange.fapiDataGetOpenInterestHist,
            params=params,
        )

        if not response:
            logger.warning(f"⚠️  Binance OI API: No data returned for {symbol}")
            return pd.DataFrame()

        for item in response:
            parsed_item = _parse_binance_oi_item(item, start_ms, end_ms)
            if parsed_item:
                all_data.append(parsed_item)

        if all_data:
            _log_binance_oi_data_range(all_data, start_ms)

    except Exception as e:
        logger.error(f"❌ Error fetching Binance OI data: {e}")
        return pd.DataFrame()

    return _finalize_binance_oi_dataframe(all_data)


def _build_okx_oi_params(inst_id: str, period: str, current_end: int) -> dict:
    """构建OKX OI API请求参数"""
    return {
        "instId": inst_id,
        "period": period,
        "end": str(current_end),
        "limit": "100",
    }


def _parse_okx_oi_item(item: dict, start_ms: int) -> dict:
    """解析单个OKX OI数据项"""
    ts = int(item["ts"])
    if ts >= start_ms:
        return {
            "timestamp": ts,
            "open_interest": float(item["oi"]),
            "open_interest_value": float(item["oiVol"]),
        }
    return None


def _process_okx_oi_response(response: dict, start_ms: int) -> tuple[list, bool, int]:
    """
    处理OKX OI API响应

    Returns:
        tuple: (数据列表, 是否继续, 下一个结束时间戳)
    """
    if not response or "data" not in response:
        return [], False, 0

    data_list = response["data"]
    if not data_list:
        return [], False, 0

    parsed_data = []
    for item in data_list:
        parsed_item = _parse_okx_oi_item(item, start_ms)
        if parsed_item:
            parsed_data.append(parsed_item)

    should_continue = len(data_list) >= 100
    next_end = int(data_list[-1]["ts"]) - 1 if should_continue else 0

    return parsed_data, should_continue, next_end


def _finalize_okx_oi_dataframe(all_data: list) -> pd.DataFrame:
    """将OKX OI数据列表转换为DataFrame"""
    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    df = df.sort_values("timestamp").reset_index(drop=True)
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
            params = _build_okx_oi_params(inst_id, period, current_end)
            response = retry_fetch(
                exchange.publicGetRubikStatContractsOpenInterestHistory,
                params=params,
            )

            parsed_data, should_continue, next_end = _process_okx_oi_response(response, start_ms)
            all_data.extend(parsed_data)

            if not should_continue:
                break

            current_end = next_end
            time.sleep(exchange.rateLimit / 1000)

        except Exception as e:
            logger.error(f"Warning: Error fetching OKX OI data: {e}")
            break

    if iteration_count >= MAX_ITERATIONS:
        logger.warning(f"Reached max iterations ({MAX_ITERATIONS}) for OKX OI {symbol}")

    return _finalize_okx_oi_dataframe(all_data)


def _build_binance_funding_params(clean_symbol: str, current_start: int, end_ms: int) -> dict:
    """构建Binance Funding Rate API请求参数"""
    return {
        "symbol": clean_symbol,
        "startTime": current_start,
        "endTime": end_ms,
        "limit": 1000,
    }


def _parse_binance_funding_item(item: dict) -> dict:
    """解析单个Binance Funding Rate数据项"""
    return {
        "timestamp": int(item["fundingTime"]),
        "funding_rate": float(item["fundingRate"]),
    }


def _calculate_next_funding_start(all_data: list) -> int:
    """计算下一次资金费率查询的起始时间（8小时后）"""
    return all_data[-1]["timestamp"] + 8 * 3600 * 1000


def _finalize_binance_funding_dataframe(all_data: list) -> pd.DataFrame:
    """将Binance Funding Rate数据列表转换为DataFrame"""
    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df["funding_rate_annual"] = df["funding_rate"] * 3 * 365 * 100
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
            params = _build_binance_funding_params(clean_symbol, current_start, end_ms)
            response = retry_fetch(exchange.fapiPublicGetFundingRate, params=params)

            if not response:
                break

            for item in response:
                all_data.append(_parse_binance_funding_item(item))

            if len(response) < 1000:
                break

            current_start = _calculate_next_funding_start(all_data)
            time.sleep(exchange.rateLimit / 1000)

        except Exception as e:
            logger.error(f"Warning: Error fetching funding rate data: {e}")
            break

    if iteration_count >= MAX_ITERATIONS:
        logger.warning(f"Reached max iterations ({MAX_ITERATIONS}) for Binance Funding {symbol}")

    return _finalize_binance_funding_dataframe(all_data)


def _build_okx_funding_params(inst_id: str, current_end: int) -> dict:
    """构建OKX Funding Rate API请求参数"""
    return {
        "instId": inst_id,
        "before": str(current_end),
        "limit": "100",
    }


def _parse_okx_funding_item(item: dict, start_ms: int) -> dict:
    """解析单个OKX Funding Rate数据项"""
    ts = int(item["fundingTime"])
    if ts >= start_ms:
        return {
            "timestamp": ts,
            "funding_rate": float(item["fundingRate"]),
            "realized_rate": float(item.get("realizedRate", 0)),
        }
    return None


def _process_okx_funding_response(response: dict, start_ms: int) -> tuple[list, bool, int]:
    """
    处理OKX Funding Rate API响应

    Returns:
        tuple: (数据列表, 是否继续, 下一个结束时间戳)
    """
    if not response or "data" not in response:
        return [], False, 0

    data_list = response["data"]
    if not data_list:
        return [], False, 0

    parsed_data = []
    for item in data_list:
        parsed_item = _parse_okx_funding_item(item, start_ms)
        if parsed_item:
            parsed_data.append(parsed_item)

    should_continue = len(data_list) >= 100
    next_end = int(data_list[-1]["fundingTime"]) - 1 if should_continue else 0

    return parsed_data, should_continue, next_end


def _finalize_okx_funding_dataframe(all_data: list) -> pd.DataFrame:
    """将OKX Funding Rate数据列表转换为DataFrame"""
    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    df = df.sort_values("timestamp").reset_index(drop=True)
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
            params = _build_okx_funding_params(inst_id, current_end)
            response = retry_fetch(exchange.publicGetPublicFundingRateHistory, params=params)

            parsed_data, should_continue, next_end = _process_okx_funding_response(
                response, start_ms
            )
            all_data.extend(parsed_data)

            if not should_continue:
                break

            current_end = next_end
            time.sleep(exchange.rateLimit / 1000)

        except Exception as e:
            logger.error(f"Warning: Error fetching OKX funding rate data: {e}")
            break

    if iteration_count >= MAX_ITERATIONS:
        logger.warning(f"Reached max iterations ({MAX_ITERATIONS}) for OKX Funding {symbol}")

    return _finalize_okx_funding_dataframe(all_data)


def _initialize_exchange(exchange_id: str):
    """初始化交易所连接"""
    exchange_class = getattr(ccxt, exchange_id.lower())
    exchange = exchange_class({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    exchange.load_markets()
    return exchange


def _resolve_and_validate_symbol(
    raw_symbol: str, exchange, exchange_id: str
) -> tuple[str, str, str] | None:
    """解析并验证交易对符号"""
    try:
        ccxt_symbol, market_type = resolve_symbol_and_type(raw_symbol)
    except Exception as e:
        tui = get_tui()
        if is_tui_enabled():
            tui.add_log(f"Failed to parse symbol {raw_symbol}: {e}, skipping", "WARNING")
        else:
            logger.warning(f"\n[WARNING] Failed to parse symbol {raw_symbol}: {e}, skipping")
        return None

    if ccxt_symbol not in exchange.markets:
        logger.warning(f"\n[WARNING] {raw_symbol} not found in {exchange_id.upper()}, skipping")
        return None

    safe_symbol = raw_symbol.replace("/", "")
    return ccxt_symbol, market_type, safe_symbol


def _fetch_oi_data(
    exchange_id: str, exchange, ccxt_symbol: str, start_ms: int, end_ms: int, oi_period: str
):
    """获取OI数据"""
    if exchange_id == "binance":
        return fetch_binance_oi_history(exchange, ccxt_symbol, start_ms, end_ms, oi_period)
    elif exchange_id == "okx":
        return fetch_okx_oi_history(exchange, ccxt_symbol, start_ms, end_ms, oi_period.upper())
    return None


def _fetch_funding_data(exchange_id: str, exchange, ccxt_symbol: str, start_ms: int, end_ms: int):
    """获取Funding Rate数据"""
    if exchange_id == "binance":
        return fetch_binance_funding_rate_history(exchange, ccxt_symbol, start_ms, end_ms)
    elif exchange_id == "okx":
        return fetch_okx_funding_rate_history(exchange, ccxt_symbol, start_ms, end_ms)
    return None


def _save_data_to_csv(df, file_path: Path, results_key: str, results: dict):
    """保存数据到CSV文件"""
    if not df.empty:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(file_path, index=False)
        results[results_key].append(str(file_path))


def _should_fetch_file(file_path: Path) -> bool:
    """检查是否需要获取文件"""
    return not (file_path.exists() and file_path.stat().st_size > 1024)


def _process_oi_data(
    exchange_id: str,
    exchange,
    ccxt_symbol: str,
    safe_symbol: str,
    start_date: str,
    end_date: str,
    start_ms: int,
    end_ms: int,
    oi_period: str,
    base_dir: Path,
    results: dict,
    enable_oi: bool,
):
    """处理OI数据获取"""
    if not enable_oi:
        return

    oi_filename = f"{exchange_id}-{safe_symbol}-oi-{oi_period}-{start_date}_{end_date}.csv"
    oi_path = base_dir / "data" / "raw" / safe_symbol / oi_filename

    if _should_fetch_file(oi_path):
        oi_df = _fetch_oi_data(exchange_id, exchange, ccxt_symbol, start_ms, end_ms, oi_period)
        if oi_df is not None:
            _save_data_to_csv(oi_df, oi_path, "oi_files", results)


def _process_funding_data(
    exchange_id: str,
    exchange,
    ccxt_symbol: str,
    safe_symbol: str,
    start_date: str,
    end_date: str,
    start_ms: int,
    end_ms: int,
    base_dir: Path,
    results: dict,
):
    """处理Funding Rate数据获取"""
    funding_filename = f"{exchange_id}-{safe_symbol}-funding-{start_date}_{end_date}.csv"
    funding_path = base_dir / "data" / "raw" / safe_symbol / funding_filename

    if _should_fetch_file(funding_path):
        funding_df = _fetch_funding_data(exchange_id, exchange, ccxt_symbol, start_ms, end_ms)
        if funding_df is not None:
            _save_data_to_csv(funding_df, funding_path, "funding_files", results)


def _print_fetch_results(results: dict, enable_oi: bool):
    """打印获取结果"""
    if enable_oi:
        logger.info(
            f"OI/Funding data retrieval complete: "
            f"{len(results['oi_files'])} OI files, "
            f"{len(results['funding_files'])} Funding files"
        )
    else:
        logger.info(
            f"Funding data retrieval complete: "
            f"{len(results['funding_files'])} Funding files "
            f"(OI data fetching disabled)"
        )


def _fetch_single_symbol_oi_funding(
    raw_symbol: str,
    exchange_id: str,
    start_date: str,
    end_date: str,
    start_ms: int,
    end_ms: int,
    oi_period: str,
    base_dir: Path,
    enable_oi: bool,
) -> dict:
    """
    获取单个交易对的 OI 和 Funding Rate 数据

    Returns:
        dict: {"oi_files": [...], "funding_files": [...]}
    """
    # 每个线程创建自己的 exchange 实例
    exchange = _initialize_exchange(exchange_id)
    results = {"oi_files": [], "funding_files": []}

    symbol_info = _resolve_and_validate_symbol(raw_symbol, exchange, exchange_id)
    if symbol_info is None:
        return results

    ccxt_symbol, market_type, safe_symbol = symbol_info

    try:
        _process_oi_data(
            exchange_id,
            exchange,
            ccxt_symbol,
            safe_symbol,
            start_date,
            end_date,
            start_ms,
            end_ms,
            oi_period,
            base_dir,
            results,
            enable_oi,
        )

        _process_funding_data(
            exchange_id,
            exchange,
            ccxt_symbol,
            safe_symbol,
            start_date,
            end_date,
            start_ms,
            end_ms,
            base_dir,
            results,
        )
    except Exception as e:
        logger.warning(f"Error fetching OI/Funding for {raw_symbol}: {e}")

    return results


def batch_fetch_oi_and_funding(
    symbols: List[str],
    start_date: str,
    end_date: str,
    exchange_id: Literal["binance", "okx"] = "binance",
    base_dir: Path = Path("."),
    oi_period: str = "1h",
    max_workers: int = None,
) -> dict:
    """
    批量获取 OI 和 Funding Rate 数据（支持并发）

    注意：OI 数据获取已临时禁用
    原因：第三方 API 仅提供 21 天历史数据，不符合长期回测需求
    计划：将通过本地服务持续采集和存储 OI 数据

    Args:
        max_workers: 并发下载的最大线程数，默认从环境变量 NAUTILUS_MAX_WORKERS 读取（默认10）
    """
    if max_workers is None:
        max_workers = DEFAULT_MAX_WORKERS

    ENABLE_OI_FETCH = False

    start_ms = get_ms_timestamp(start_date)
    end_ms = get_ms_timestamp(end_date)
    results = {"oi_files": [], "funding_files": []}

    desc = (
        f"📊 Fetching Funding from {exchange_id.upper()}"
        if not ENABLE_OI_FETCH
        else f"📊 Fetching OI/Funding from {exchange_id.upper()}"
    )

    with tqdm(total=len(symbols), desc=desc, unit="symbol") as pbar:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有下载任务
            future_to_symbol = {
                executor.submit(
                    _fetch_single_symbol_oi_funding,
                    raw_symbol,
                    exchange_id,
                    start_date,
                    end_date,
                    start_ms,
                    end_ms,
                    oi_period,
                    base_dir,
                    ENABLE_OI_FETCH,
                ): raw_symbol
                for raw_symbol in symbols
            }

            # 处理完成的任务
            for future in as_completed(future_to_symbol):
                raw_symbol = future_to_symbol[future]
                try:
                    symbol_results = future.result()
                    results["oi_files"].extend(symbol_results["oi_files"])
                    results["funding_files"].extend(symbol_results["funding_files"])

                    pbar.set_postfix_str(f"{raw_symbol}", refresh=True)
                    pbar.update(1)
                except Exception as e:
                    logger.error(f"Error processing {raw_symbol}: {e}")
                    pbar.update(1)

    _print_fetch_results(results, ENABLE_OI_FETCH)
    return results
