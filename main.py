import argparse
import json
import subprocess
import sys
from pathlib import Path

# Add workspace root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from backtest.engine_high import run_high_level
from backtest.engine_low import run_low_level
from config.settings import (
    END_DATE,
    START_DATE,
    current_config,
)
from utils.fetch_instrument import update_instruments


def check_data_exists(symbol_str, start_date, end_date, timeframe, exchange):
    """
    Checks if the OHLCV data file already exists and is valid.
    """
    filename = (
        f"{exchange.lower()}-{symbol_str}-{timeframe}-{start_date}_{end_date}.csv"
    )
    filepath = BASE_DIR / "data" / "raw" / symbol_str / filename
    if filepath.exists() and filepath.stat().st_size > 500 * 1024:
        return True
    return False


def run_batch_data_retrieval(symbols, start_date, end_date, timeframe, exchange):
    """
    Executes the data retrieval script for a batch of symbols.
    """
    if not symbols:
        return

    cmd = [
        "uv",
        "run",
        "utils/data_retrival.py",
        "--symbol",
        ",".join(symbols),
        "--start",
        start_date,
        "--end",
        end_date,
        "--timeframe",
        timeframe,
        "--exchange",
        exchange.lower(),
    ]

    print(f"\n[Data] Fetching/Updating data for {len(symbols)} symbols...")
    print(f"      Command: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error during batch data retrieval: {e}")
    except Exception as e:
        print(f"❌ Unexpected error during batch data retrieval: {e}")


def main():
    parser = argparse.ArgumentParser(description="Nautilus Trader Unified Runner")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Backtest Command
    bt_parser = subparsers.add_parser("backtest", help="Run backtest")
    bt_parser.add_argument(
        "--type",
        choices=["high", "low"],
        default="high",
        help="Backtest engine type (high-level node or low-level engine)",
    )
    bt_parser.add_argument(
        "--skip-data",
        action="store_true",
        help="Skip automatic data retrieval",
    )

    # Sandbox Command
    sb_parser = subparsers.add_parser(
        "sandbox", help="Run sandbox (Not implemented yet)"
    )

    # Live Command
    live_parser = subparsers.add_parser(
        "live", help="Run live trading (Not implemented yet)"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 检测是否有关联的 Universe 文件
    universe_symbols = set()
    if args.command == "backtest":
        params = current_config.strategy.params
        u_name = (
            params.get("universe_filename")
            if isinstance(params, dict)
            else getattr(params, "universe_filename", None)
        )
        if u_name:
            u_path = BASE_DIR / "data" / u_name
            if u_path.exists():
                try:
                    with open(u_path, "r") as f:
                        u_data = json.load(f)
                        for month_list in u_data.values():
                            universe_symbols.update(month_list)
                    print(
                        f"🌌 Universe detected: {len(universe_symbols)} symbols found."
                    )
                except Exception as e:
                    print(f"⚠️ Failed to load universe file: {e}")

    # 1. Automatic Data Retrieval (Only for backtest if not skipped)
    if args.command == "backtest" and not args.skip_data:
        print("==========================================")
        print("🔍 Checking & Retrieving Data in batches...")

        # 任务分组: (exchange, timeframe, start, end) -> set(symbols)
        tasks = {}

        # 1.1 遍历 data_feeds 收集需要更新的行情数据
        for feed in current_config.data_feeds:
            try:
                parts = feed.csv_file_name.split("/")
                symbol_quote = parts[0]
                file_parts = parts[1].split("-")
                exchange = file_parts[0]
                timeframe = file_parts[2]

                if not check_data_exists(
                    symbol_quote, START_DATE, END_DATE, timeframe, exchange
                ):
                    key = (exchange, timeframe, START_DATE, END_DATE)
                    tasks.setdefault(key, set()).add(symbol_quote)
                else:
                    print(f"✅ Data exists for {symbol_quote} ({exchange} {timeframe})")
            except Exception as e:
                print(f"⚠️ Failed to parse data feed config: {feed.label}, error: {e}")

        # 1.2 如果存在 Universe，为其中的每个币种补充到任务列表 (使用 main feed 的参数)
        if universe_symbols:
            main_feed = next(
                (f for f in current_config.data_feeds if f.label == "main"), None
            )
            if main_feed:
                try:
                    parts = main_feed.csv_file_name.split("/")
                    file_parts = parts[1].split("-")
                    exchange = file_parts[0]
                    timeframe = file_parts[2]

                    for symbol in sorted(list(universe_symbols)):
                        symbol_str = symbol.split(":")[0]  # SOLUSDT:USDT -> SOLUSDT
                        if not check_data_exists(
                            symbol_str, START_DATE, END_DATE, timeframe, exchange
                        ):
                            key = (exchange, timeframe, START_DATE, END_DATE)
                            tasks.setdefault(key, set()).add(symbol_str)
                except Exception as e:
                    print(f"⚠️ Failed to process universe data retrieval logic: {e}")

        # 1.3 执行批量抓取
        for (exchange, timeframe, start, end), symbols in tasks.items():
            run_batch_data_retrieval(
                sorted(list(symbols)), start, end, timeframe, exchange
            )

        print("==========================================\n")

    # 2. Fetch & Update Instruments
    try:
        instrument_ids = {current_config.instrument.instrument_id}
        for feed in current_config.data_feeds:
            if feed.instrument_id:
                instrument_ids.add(feed.instrument_id)

        for symbol in universe_symbols:
            raw_pair = symbol.split(":")[0]
            clean_base = raw_pair.replace("USDT", "")
            venue = current_config.instrument.venue_name
            inst_id = f"{clean_base}-USDT-SWAP.{venue}"
            instrument_ids.add(inst_id)

        print(
            f"🔄 Updating instrument definitions for: {len(instrument_ids)} instruments"
        )
        update_instruments(list(instrument_ids))
    except Exception as e:
        print(f"\t ⚠️ Failed to update instruments: {e}")
        print("\t Continuing with existing local files (if any)...")

    # 3. Execute Commands
    if args.command == "backtest":
        if args.type == "high":
            run_high_level(current_config, BASE_DIR)
        elif args.type == "low":
            run_low_level(current_config, BASE_DIR)

    elif args.command == "sandbox":
        print("🚧 Sandbox mode integration pending...")

    elif args.command == "live":
        print("🚧 Live mode integration pending...")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
