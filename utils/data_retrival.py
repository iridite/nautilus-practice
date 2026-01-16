import argparse
import time
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import pandas as pd


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Fetch OHLCV and Funding Rate data from Crypto Exchanges via CCXT."
    )

    # 1. 交易标的 (支持多个标的，以逗号分隔)
    parser.add_argument(
        "--symbol",
        "-s",
        type=str,
        required=True,
        help="Trading symbol(s), e.g., ETHUSDT or ETHUSDT,BTCUSDT",
    )

    # 2. 起始时间
    parser.add_argument(
        "--start", type=str, required=True, help="Start date (YYYY-MM-DD)"
    )

    # 结束时间 (默认为今天零点)
    today = (
        datetime.now()
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .strftime("%Y-%m-%d")
    )
    parser.add_argument(
        "--end",
        type=str,
        default=today,
        help="End date (YYYY-MM-DD), defaults to today 00:00",
    )

    # 3. 时间粒度
    parser.add_argument(
        "--timeframe",
        type=str,
        default="1h",
        help="Timeframe interval, e.g., 5m, 1h, 1d",
    )

    # 4. 指定交易所
    parser.add_argument(
        "--exchange",
        type=str,
        default="binance",
        choices=["binance", "okx"],
        help="Exchange ID (binance or okx). Default is binance.",
    )

    parser.add_argument(
        "--extra", "-e", action="store_true", help="Include funding rate data"
    )

    return parser.parse_args()


def get_ms_timestamp(date_str):
    """将 YYYY-MM-DD 字符串转换为毫秒级时间戳 (UTC)"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


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
    """
    通用重试助手函数。
    对于 IP 被封锁 (418) 的情况，增加更长的延迟。
    """
    for attempt in range(1, retries + 1):
        try:
            return func(*args, **kwargs)
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            err_msg = str(e)
            # 如果触发了 418 (I'm a teapot) 或者 -1003 (Banned)，说明请求太快或被封
            current_delay = (
                delay * 2 if "418" in err_msg or "-1003" in err_msg else delay
            )

            if attempt == retries:
                print(f"\n[!] Final attempt failed: {e}")
                raise e

            print(
                f"\n[!] Error: {e}. Retrying ({attempt}/{retries}) in {current_delay}s..."
            )
            time.sleep(current_delay)
    return None


def fetch_ohlcv_data(exchange, symbol, timeframe, since, limit_ms):
    """循环抓取 OHLCV 数据"""
    all_ohlcv = []
    current_since = since

    print(f"[*] [{exchange.id}] Fetching OHLCV for {symbol}...")

    while current_since < limit_ms:
        try:
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

            last_timestamp = ohlcv[-1][0]
            if last_timestamp < current_since:
                break

            new_data = [x for x in ohlcv if x[0] >= current_since]
            if not new_data:
                break

            all_ohlcv.extend(new_data)
            current_since = all_ohlcv[-1][0] + 1

            last_date = datetime.fromtimestamp(current_since / 1000, timezone.utc)
            print(f"    Fetched up to {last_date} ({len(all_ohlcv)} candles)", end="\r")

            if current_since >= limit_ms:
                break

            time.sleep(exchange.rateLimit / 1000)

        except Exception as e:
            print(f"\n[!] Error fetching OHLCV for {symbol}: {e}")
            break

    print(f"\n[*] OHLCV fetch complete. Total candles: {len(all_ohlcv)}")
    if not all_ohlcv:
        return pd.DataFrame()

    df = pd.DataFrame(
        all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    df = df[df["timestamp"] < limit_ms]
    return df


def fetch_funding_data(exchange, symbol, since, limit_ms):
    """循环抓取资金费率历史数据"""
    all_funding = []
    current_since = since

    if not exchange.has.get("fetchFundingRateHistory"):
        return pd.DataFrame()

    while current_since < limit_ms:
        try:
            limit_param = 100 if exchange.id == "okx" else 1000
            funding = retry_fetch(
                exchange.fetch_funding_rate_history,
                symbol,
                since=current_since,
                limit=limit_param,
            )

            if not funding:
                break

            new_funding = [f for f in funding if f["timestamp"] >= current_since]
            if not new_funding:
                break

            all_funding.extend(new_funding)
            current_since = new_funding[-1]["timestamp"] + 1

            if current_since >= limit_ms:
                break

            time.sleep(exchange.rateLimit / 1000)

        except Exception as e:
            print(f"\n[!] Error fetching Funding Rate for {symbol}: {e}")
            break

    if not all_funding:
        return pd.DataFrame()

    df = pd.DataFrame(
        [
            {"timestamp": f["timestamp"], "fundingRate": f["fundingRate"]}
            for f in all_funding
        ]
    )
    return df.drop_duplicates(subset=["timestamp"])


def process_symbol(exchange, raw_symbol, start_ms, end_ms, timeframe, extra, base_dir):
    ccxt_symbol, market_type = resolve_symbol_and_type(raw_symbol)

    if ccxt_symbol not in exchange.markets:
        print(
            f"[!] Error: Symbol '{ccxt_symbol}' not found in {exchange.id}. Skipping."
        )
        return

    ohlcv_df = fetch_ohlcv_data(exchange, ccxt_symbol, timeframe, start_ms, end_ms)
    if ohlcv_df.empty:
        return

    if market_type == "swap" and extra:
        funding_df = fetch_funding_data(exchange, ccxt_symbol, start_ms, end_ms)
        if not funding_df.empty:
            ohlcv_df = pd.merge(ohlcv_df, funding_df, on="timestamp", how="left")
        else:
            ohlcv_df["fundingRate"] = None

    ohlcv_df["datetime"] = pd.to_datetime(ohlcv_df["timestamp"], unit="ms")

    cols = ["datetime", "timestamp", "open", "high", "low", "close", "volume"]
    if "fundingRate" in ohlcv_df.columns:
        cols.append("fundingRate")

    ohlcv_df = ohlcv_df[cols]

    safe_symbol = raw_symbol.replace("/", "")
    output_dir = base_dir / "data" / "raw" / safe_symbol
    output_dir.mkdir(parents=True, exist_ok=True)

    start_str = datetime.fromtimestamp(start_ms / 1000, timezone.utc).strftime(
        "%Y-%m-%d"
    )
    end_str = datetime.fromtimestamp(end_ms / 1000, timezone.utc).strftime("%Y-%m-%d")
    filename = f"{exchange.id}-{safe_symbol}-{timeframe}-{start_str}_{end_str}.csv"
    output_path = output_dir / filename

    ohlcv_df.to_csv(output_path, index=False)
    print(f"    [√] Saved to: {output_path}")


def main():
    args = parse_arguments()
    base_dir = Path(__file__).resolve().parent.parent

    # 1. 初始化交易所 (启用频率限制)
    exchange_class = getattr(ccxt, args.exchange)
    exchange = exchange_class(
        {
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        }
    )

    # 2. 预先加载市场 (只加载一次)
    print(f"[*] Initializing exchange {args.exchange.upper()} and loading markets...")
    try:
        retry_fetch(exchange.load_markets)
    except Exception as e:
        print(f"[!] Critical error loading markets: {e}")
        return

    # 3. 解析所有需要抓取的标的
    symbols = [s.strip() for s in args.symbol.split(",")]
    start_ms = get_ms_timestamp(args.start)
    end_ms = get_ms_timestamp(args.end)

    print(f"--- Batch Job Configuration ---")
    print(f"Exchange: {args.exchange.upper()}")
    print(f"Symbols:  {len(symbols)} found")
    print(f"Range:    {args.start} to {args.end}")
    print(f"--------------------------------")

    # 4. 循环处理
    for symbol in symbols:
        try:
            process_symbol(
                exchange, symbol, start_ms, end_ms, args.timeframe, args.extra, base_dir
            )
            # 在不同币种之间增加额外延迟，进一步降低 IP 封锁风险
            time.sleep(1.0)
        except Exception as e:
            print(f"[!] Error processing {symbol}: {e}")
            continue

    print("\n[!] Batch processing complete.")


if __name__ == "__main__":
    main()
