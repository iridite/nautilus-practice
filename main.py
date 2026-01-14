import argparse
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
    MAIN_TIMEFRAME,
    QUOTE,
    START_DATE,
    SYMBOL,
    TREND_TIMEFRAME,
    VENUE,
    current_config,
)
from utils.fetch_instrument import update_instruments


def run_data_retrieval(symbol_str, start_date, end_date, timeframe, exchange):
    """
    Executes the data retrieval script via uv run if the file doesn't exist or is too small.
    """
    # 拼接预期的文件名与路径
    filename = (
        f"{exchange.lower()}-{symbol_str}-{timeframe}-{start_date}_{end_date}.csv"
    )
    filepath = BASE_DIR / "data" / "raw" / symbol_str / filename

    # 检测文件是否存在且大小 > 500KB
    if filepath.exists() and filepath.stat().st_size > 500 * 1024:
        print(
            f"✅ 行情数据已存在且有效: {filename} ({filepath.stat().st_size / 1024:.2f} KB). 跳过抓取。"
        )
        return

    cmd = [
        "uv",
        "run",
        "utils/data_retrival.py",
        "--symbol",
        symbol_str,
        "--start",
        start_date,
        "--end",
        end_date,
        "--timeframe",
        timeframe,
        "--exchange",
        exchange.lower(),
    ]

    print(f"\n[Data] Fetching/Updating data: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error fetching data: {e}")
        # We don't exit here to allow attempting backtest with existing data if any
    except Exception as e:
        print(f"❌ Unexpected error during data retrieval: {e}")


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

    # 1. Automatic Data Retrieval (Only for backtest if not skipped)
    if args.command == "backtest" and not args.skip_data:
        print("==========================================")
        print("🔍 Checking & Retrieving Data...")

        symbol_str = f"{SYMBOL}{QUOTE}"
        timeframes = [MAIN_TIMEFRAME]
        if TREND_TIMEFRAME and TREND_TIMEFRAME != MAIN_TIMEFRAME:
            timeframes.append(TREND_TIMEFRAME)

        for tf in timeframes:
            run_data_retrieval(symbol_str, START_DATE, END_DATE, tf, VENUE)
        print("==========================================\n")

    # 2. Fetch & Update Instruments
    # This ensures we have the latest instrument definitions from the exchange
    try:
        instrument_id: str = current_config.instrument.instrument_id
        print(f"🔄 Updating instrument definitions for: {instrument_id}")
        update_instruments([instrument_id])
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
