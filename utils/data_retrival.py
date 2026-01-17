import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import ccxt
import pandas as pd
from nautilus_trader.model.enums import BarAggregation
from tqdm import tqdm

from config.definitions import DataConfig


def get_ms_timestamp(date_str: str) -> int:
    """将 YYYY-MM-DD 字符串转换为毫秒级时间戳 (UTC)"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def parse_timeframe(timeframe: str) -> tuple[BarAggregation, int]:
    """将 ccxt timeframe 转换为 Nautilus BarAggregation 和 period"""
    unit = timeframe[-1]
    period = int(timeframe[:-1]) if len(timeframe) > 1 else 1

    if unit == "m":
        return BarAggregation.MINUTE, period
    if unit == "h":
        return BarAggregation.HOUR, period
    if unit == "d":
        return BarAggregation.DAY, period
    if unit == "w":
        return BarAggregation.WEEK, period
    return BarAggregation.MINUTE, 1


def resolve_symbol_and_type(input_symbol):
    """
    解析输入标的，返回 (ccxt_unified_symbol, market_type)
    """
    if "/" in input_symbol:
        return input_symbol, "spot"
    else:
        if input_symbol.upper().endswith("USDT"):
            base = input_symbol.upper().replace("USDT", "")
            ccxt_symbol = f"{base}/USDT:USDT"
            return ccxt_symbol, "swap"
        elif input_symbol.upper().endswith("USD"):
            base = input_symbol.upper().replace("USD", "")
            ccxt_symbol = f"{base}/USD:{base}"
            return ccxt_symbol, "swap"
        else:
            return input_symbol, "swap"


def retry_fetch(func, *args, retries=3, delay=5, **kwargs):
    for attempt in range(1, retries + 1):
        try:
            return func(*args, **kwargs)
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            err_msg = str(e)
            current_delay = (
                delay * 2 if "418" in err_msg or "-1003" in err_msg else delay
            )
            if attempt == retries:
                raise e
            time.sleep(current_delay)
    return None


def fetch_ohlcv_data(exchange, symbol, timeframe, since, limit_ms):
    all_ohlcv = []
    current_since = since
    while current_since < limit_ms:
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
) -> List[DataConfig]:
    """
    函数式调用：批量抓取数据并返回 DataConfig 列表。
    """
    # 1. 初始化交易所
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

    # 使用 tqdm 进度条
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

            # 构建文件名和路径
            filename = (
                f"{exchange.id}-{safe_symbol}-{timeframe}-{start_date}_{end_date}.csv"
            )
            relative_path = f"{safe_symbol}/{filename}"
            output_path = base_dir / "data" / "raw" / relative_path

            # 更新进度条描述
            pbar.set_postfix_str(f"{raw_symbol}", refresh=True)

            # 检查是否需要下载
            if not (output_path.exists() and output_path.stat().st_size > 10 * 1024):
                df = fetch_ohlcv_data(
                    exchange, ccxt_symbol, timeframe, start_ms, end_ms
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

            # 生成 DataConfig
            configs.append(
                DataConfig(
                    csv_file_name=relative_path,
                    bar_aggregation=agg,
                    bar_period=period,
                    label="main" if len(symbols) == 1 else "universe",
                )
            )

    # 打印完成摘要
    print(
        f"✅ Data retrieval complete: {len(configs)}/{total} symbols "
        f"(fetched: {fetched_count}, cached: {skipped_count})"
    )

    return configs
