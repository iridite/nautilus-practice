"""数据验证模块"""

from pathlib import Path

from config.settings import get_end_date, get_start_date, get_venue
from utils.validation import check_single_data_file


def prepare_data_feeds(args, adapter, base_dir: Path, universe_symbols: set):
    """准备数据流（验证或获取）"""
    from data.fetcher_manager import run_batch_data_retrieval

    if args.skip_data_check:
        print("⏩ Skipping data validation")
        return

    print("="*70)
    print("📊 Data Validation")
    print("="*70)

    venue = get_venue().lower()
    start_date = get_start_date()
    end_date = get_end_date()
    timeframe = adapter.get_main_timeframe()

    symbols_to_check = universe_symbols if universe_symbols else {adapter.get_primary_symbol()}

    missing_symbols = []
    for symbol in symbols_to_check:
        exists, _ = check_single_data_file(
            symbol.split(":")[0], start_date, end_date, timeframe, venue, base_dir
        )
        if not exists:
            missing_symbols.append(symbol.split(":")[0])

    if missing_symbols:
        print(f"📥 {len(missing_symbols)} symbols need data")
        run_batch_data_retrieval(
            missing_symbols, start_date, end_date, timeframe, venue, base_dir
        )
    else:
        print("✅ All data files present")

    print("="*70 + "\n")
