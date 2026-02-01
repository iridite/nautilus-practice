import time
from datetime import datetime

import ccxt

# 使用统一的工具函数
from utils import fetch_ohlcv_data, get_ms_timestamp, get_project_root

# 获取项目根目录
PROJECT_ROOT = get_project_root()


def get_all_binance_usdt_spot_symbols():
    """
    获取币安所有永续 USDT 交易对
    """
    print("[*] Fetching all USDT perp symbols from Binance...")
    exchange = ccxt.binance()
    markets = exchange.load_markets()

    symbols = []
    for symbol, market in markets.items():
        # 筛选：永续合约 + 以 USDT 结算 + 激活状态
        if market["swap"] and market["quote"] == "USDT" and market["active"]:
            symbols.append(symbol)

    print(f"[*] Found {len(symbols)} USDT spot symbols.")
    return symbols


def main():
    # 配置
    exchange_id = "binance"
    timeframe = "1d"
    start_date = "2020-01-01"
    end_date = datetime.now().strftime("%Y-%m-%d")

    # 根目录数据文件夹
    data_root = PROJECT_ROOT / "data" / "top"
    data_root.mkdir(parents=True, exist_ok=True)

    # 1. 获取所有币种
    all_symbols = get_all_binance_usdt_spot_symbols()

    # 初始化交易所用于下载
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class(
        {
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }
    )

    start_ms = get_ms_timestamp(start_date)
    end_ms = get_ms_timestamp(end_date)

    # 2. 循环下载
    success_count = 0
    fail_count = 0

    total = len(all_symbols)
    for i, symbol in enumerate(all_symbols):
        safe_symbol = symbol.replace("/", "")
        file_path = data_root / f"{safe_symbol}_{timeframe}.csv"

        # 如果文件已存在且大小不为0，可以跳过（或者根据需要重新下载）
        if file_path.exists() and file_path.stat().st_size > 0:
            print(f"[{i + 1}/{total}] Skip {symbol}, file already exists.")
            success_count += 1
            continue

        print(f"\n[{i + 1}/{total}] Processing {symbol}...")

        try:
            # 使用 data_retrival.py 中的核心逻辑，启用自动数据源切换
            df = fetch_ohlcv_data(exchange, symbol, timeframe, start_ms, end_ms, source="auto")

            if not df.empty:
                # 按照要求，CSV 包含字段：timestamp, open, high, low, close, volume
                # fetch_ohlcv_data 返回的已经是这些字段
                df.to_csv(file_path, index=False)
                print(f"[√] Saved {symbol} to {file_path}")
                success_count += 1
            else:
                print(f"[!] No data for {symbol}")
                fail_count += 1

        except Exception as e:
            print(f"[!] Error processing {symbol}: {e}")
            fail_count += 1

        # 适当休眠，尊重频率限制
        time.sleep(exchange.rateLimit / 1000)

    print("\n" + "=" * 30)
    print("Task Completed.")
    print(f"Total Symbols: {total}")
    print(f"Success: {success_count}")
    print(f"Failed: {fail_count}")
    print(f"Data saved in: {data_root}")
    print("=" * 30)


if __name__ == "__main__":
    main()
