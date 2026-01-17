import argparse
import json
import sys
from pathlib import Path

# Add workspace root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from backtest.engine_high import run_high_level
from backtest.engine_low import run_low_level
from config.definitions import InstrumentConfig, InstrumentType
from config.settings import (
    END_DATE,
    INSTRUMENT_TYPE,
    START_DATE,
    VENUE,
    current_config,
)
from utils.data_retrival import batch_fetch_ohlcv
from utils.fetch_instrument import update_instruments


def check_data_exists(symbol_str, start_date, end_date, timeframe, exchange):
    """
    Checks if the OHLCV data file already exists and is valid.
    """
    safe_symbol = symbol_str.replace("/", "")
    filename = (
        f"{exchange.lower()}-{safe_symbol}-{timeframe}-{start_date}_{end_date}.csv"
    )
    filepath = BASE_DIR / "data" / "raw" / safe_symbol / filename
    if filepath.exists() and filepath.stat().st_size > 10 * 1024:
        return True
    elif filepath.exists() and filepath.stat().st_size < 10 * 1024:
        print(
            f"⚠️ Data file for {symbol_str} ({exchange} {timeframe}) is un seemingly small"
        )
        return True
    elif not filepath.exists():
        print(f"⚠️ Data file for {symbol_str} ({exchange} {timeframe}) does not exist.")
        return False
    return False


def run_batch_data_retrieval(
    symbols, start_date, end_date, timeframe, exchange
) -> list:
    """
    直接调用 Python 函数进行数据抓取。
    """
    if not symbols:
        return []

    print(
        f"\n[Data] Fetching/Updating data for {len(symbols)} symbols via functional call..."
    )
    try:
        # 直接调用重构后的函数
        data_configs = batch_fetch_ohlcv(
            symbols=sorted(list(symbols)),
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe,
            exchange_id=exchange,
            base_dir=BASE_DIR,
        )
        return data_configs
    except Exception as e:
        print(f"❌ Error during data retrieval: {e}")
        return []


def get_default_venue_and_type():
    """
    获取默认的交易所和标的类型。
    优先从 current_config.instrument 读取，如果为 None 则从全局设置读取。
    """
    if current_config.instrument:
        return (
            current_config.instrument.venue_name,
            current_config.instrument.base_currency,
            current_config.instrument.type,
        )
    else:
        # 多标的模式：从全局设置读取默认值
        return VENUE, "USDT", INSTRUMENT_TYPE


def parse_universe_symbols(universe_symbols, venue, base_currency, inst_type):
    """
    从 Universe 符号列表中解析出 InstrumentID 列表。

    Args:
        universe_symbols: Universe 中的符号集合 (如 {"SOLUSDT:USDT", "BTCUSDT:USDT", ...})
        venue: 交易所名称
        base_currency: 基准货币
        inst_type: 标的类型

    Returns:
        set: Instrument ID 集合
    """
    instrument_ids = set()
    for symbol in universe_symbols:
        raw_pair = symbol.split(":")[0]  # SOLUSDT:USDT -> SOLUSDT
        # 提取 quote_currency (如 SOLUSDT -> SOL)
        clean_quote = raw_pair.replace(base_currency, "")

        # 使用 InstrumentConfig.get_id_for 动态生成符合交易所规范的 ID
        inst_id = InstrumentConfig.get_id_for(
            venue_name=venue,
            base_currency=base_currency,
            quote_currency=clean_quote,
            inst_type=inst_type,
        )
        instrument_ids.add(inst_id)

    return instrument_ids


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
        u_name = None
        if isinstance(params, dict):
            u_name = params.get("universe_filename") or params.get("universe_filepath")
        else:
            u_name = getattr(params, "universe_filename", None) or getattr(
                params, "universe_filepath", None
            )
        if u_name:
            u_path = (
                Path(u_name)
                if Path(u_name).is_absolute()
                else BASE_DIR / "data" / Path(u_name).name
            )
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
            # 尝试从 main feed 获取参数，如果没有则使用默认值
            main_feed = next(
                (f for f in current_config.data_feeds if f.label == "main"), None
            )

            # 获取默认参数
            venue, base_currency, inst_type = get_default_venue_and_type()

            if main_feed:
                try:
                    parts = main_feed.csv_file_name.split("/")
                    file_parts = parts[1].split("-")
                    exchange = file_parts[0]
                    timeframe = file_parts[2]
                except Exception as e:
                    print(f"⚠️ Failed to parse main feed, using defaults: {e}")
                    exchange = venue.lower()
                    timeframe = "1h"
            else:
                # 如果没有 main feed (纯 Universe 模式)，使用默认值
                exchange = venue.lower()
                timeframe = "1h"
                print(f"📌 No main feed found, using defaults: {exchange} {timeframe}")

            for symbol in sorted(list(universe_symbols)):
                symbol_str = symbol.split(":")[0]  # SOLUSDT:USDT -> SOLUSDT
                if not check_data_exists(
                    symbol_str, START_DATE, END_DATE, timeframe, exchange
                ):
                    key = (exchange, timeframe, START_DATE, END_DATE)
                    tasks.setdefault(key, set()).add(symbol_str)
                else:
                    # 使用单行刷新避免大量日志输出
                    sys.stdout.write(
                        f"\r✅ Data exists: {symbol_str} ({exchange} {timeframe}){' ' * 20}"
                    )
                    sys.stdout.flush()

        # 换行结束进度显示
        if universe_symbols:
            print()  # 确保后续输出不会覆盖进度行

        # 1.3 执行批量抓取并实时更新 current_config
        # 记录已经存在的 csv，防止重复添加
        existing_csvs = {f.csv_file_name for f in current_config.data_feeds}

        for (exchange, timeframe, start, end), symbols in tasks.items():
            new_configs = run_batch_data_retrieval(
                sorted(list(symbols)), start, end, timeframe, exchange
            )
            # 将抓取成功后生成的 DataConfig 注入到全局配置中
            for nc in new_configs:
                if nc.csv_file_name not in existing_csvs:
                    print(f"➕ Auto-injecting feed: {nc.csv_file_name}")
                    current_config.data_feeds.append(nc)
                    existing_csvs.add(nc.csv_file_name)

        print("==========================================\n")

    # 2. Fetch & Update Instruments
    try:
        instrument_ids = set()

        # 2.1 从 current_config.instrument 获取 (单标的模式)
        if current_config.instrument:
            instrument_ids.add(current_config.instrument.instrument_id)

        # 2.2 从 data_feeds 获取已定义的 instrument_id
        for feed in current_config.data_feeds:
            if feed.instrument_id:
                instrument_ids.add(feed.instrument_id)

        # 2.3 从 Universe 解析 Instrument IDs (多标的模式)
        if universe_symbols:
            venue, base_currency, inst_type = get_default_venue_and_type()
            universe_inst_ids = parse_universe_symbols(
                universe_symbols, venue, base_currency, inst_type
            )
            instrument_ids.update(universe_inst_ids)

        if instrument_ids:
            print(
                f"🔄 Updating instrument definitions for: {len(instrument_ids)} instruments"
            )
            update_instruments(list(instrument_ids))
        else:
            print("⚠️ No instruments to update.")

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
