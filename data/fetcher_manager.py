"""数据获取管理模块"""

from pathlib import Path

from utils.data_retrival import batch_fetch_ohlcv, batch_fetch_oi_and_funding


def run_batch_data_retrieval(
    symbols, start_date, end_date, timeframe, exchange, base_dir: Path
) -> list:
    """直接调用 Python 函数进行数据抓取"""
    if not symbols:
        return []

    print(
        f"\nFetching/Updating raw trade pair data for {len(symbols)} symbols via functional call..."
    )
    try:
        data_configs = batch_fetch_ohlcv(
            symbols=sorted(list(symbols)),
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe,
            exchange_id=exchange,
            base_dir=base_dir,
        )
        return data_configs
    except Exception as e:
        print(f"❌ Error during data retrieval: {e}")
        return []


def fetch_data_with_retry(
    data_type: str,
    symbols: list,
    exchange: str,
    start_date: str,
    end_date: str,
    period: str,
    base_dir: Path,
    max_retries: int,
    supported_exchanges: list
) -> tuple[int, int, int, str | None]:
    """带重试的数据获取"""
    files_count = 0
    retries_count = 0
    fallbacks_count = 0
    error_msg = None

    for attempt in range(max_retries):
        try:
            current_exchange = supported_exchanges[min(attempt, len(supported_exchanges) - 1)]

            if data_type == "oi":
                result = batch_fetch_oi_and_funding(
                    symbols=symbols,
                    start_date=start_date,
                    end_date=end_date,
                    period=period,
                    exchange_id=current_exchange,
                    base_dir=base_dir,
                    data_types=["oi"],
                )
            else:
                result = batch_fetch_oi_and_funding(
                    symbols=symbols,
                    start_date=start_date,
                    end_date=end_date,
                    period=period,
                    exchange_id=current_exchange,
                    base_dir=base_dir,
                    data_types=["funding"],
                )

            if result:
                files_count = len(result)
                if attempt > 0:
                    retries_count = attempt
                if current_exchange != exchange:
                    fallbacks_count = 1
                break

        except Exception as e:
            error_msg = str(e)
            if attempt < max_retries - 1:
                continue
            else:
                break

    return files_count, retries_count, fallbacks_count, error_msg
