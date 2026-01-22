import time
from pathlib import Path
from typing import List

import ccxt
import pandas as pd
from tqdm import tqdm

from config.definitions import DataConfig
from utils.network import retry_fetch
from utils.symbol_parser import parse_timeframe, resolve_symbol_and_type
from utils.time_helpers import get_ms_timestamp


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
