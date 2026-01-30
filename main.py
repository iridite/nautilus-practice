import argparse
import json
import shutil
import sys
from pathlib import Path

from tqdm import tqdm

# Add workspace root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from backtest.engine_high import run_high_level
from backtest.engine_low import run_low_level
from config.adapter import DataConfig
from config.settings import (
    get_adapter,
    get_end_date,
    get_start_date,
    get_venue,
    run_file_cleanup,
)
from scripts.fetch_instrument import update_instruments
from utils.config_helpers import parse_universe_symbols
from utils.data_retrival import batch_fetch_ohlcv, batch_fetch_oi_and_funding
from utils.smart_data_manager import SmartDataManager
from utils.validation import (
    check_funding_data_exists,
    check_oi_data_exists,
    check_single_data_file,
)


def run_batch_data_retrieval(
    symbols, start_date, end_date, timeframe, exchange
) -> list:
    """
    直接调用 Python 函数进行数据抓取。
    """
    if not symbols:
        return []

    print(
        f"\nFetching/Updating raw trade pair data for {len(symbols)} symbols via functional call..."
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


def _extract_strategy_symbols(strategy_config, universe_symbols: set) -> set:
    """提取策略相关的符号列表"""
    symbols = set()

    if hasattr(strategy_config, 'data_feeds') and strategy_config.data_feeds:
        for feed in strategy_config.data_feeds:
            try:
                symbols.add(feed.csv_file_name.split("/")[0])
            except Exception:
                pass

    if universe_symbols:
        symbols.update(s.split(":")[0] for s in universe_symbols)

    if hasattr(strategy_config, 'instrument_id') and strategy_config.instrument_id:
        try:
            symbols.add(strategy_config.instrument_id.split('.')[1].split('-')[0])
        except Exception:
            pass

    return symbols


def check_strategy_data_dependencies(
    strategy_config,
    start_date: str,
    end_date: str,
    base_dir: Path,
    universe_symbols: set = None
) -> dict:
    """检查策略数据依赖并返回缺失的数据任务"""
    tasks = {"oi_tasks": {}, "funding_tasks": {}, "missing_count": 0, "warnings": []}

    data_types = getattr(strategy_config, 'data_types', [])
    if not data_types:
        return tasks

    strategy_symbols = _extract_strategy_symbols(strategy_config, universe_symbols)
    if not strategy_symbols:
        return tasks

    print(f"🔍 检查 {len(strategy_symbols)} 个符号的 {len(data_types)} 种数据类型")

    # 检查每个数据类型
    for data_type in data_types:
        if data_type == "oi":
            exists, missing_files = check_oi_data_exists(
                list(strategy_symbols), start_date, end_date, "1h", "binance", base_dir
            )
            if not exists:
                key = ("binance", "1h", start_date, end_date)
                if key not in tasks["oi_tasks"]:
                    tasks["oi_tasks"][key] = set()
                for file_path in missing_files:
                    try:
                        symbol = file_path.split('/')[-2]
                        tasks["oi_tasks"][key].add(symbol)
                        tasks["missing_count"] += 1
                    except Exception:
                        continue

        elif data_type == "funding":
            exists, missing_files = check_funding_data_exists(
                list(strategy_symbols), start_date, end_date, "binance", base_dir
            )
            if not exists:
                key = ("binance", start_date, end_date)
                if key not in tasks["funding_tasks"]:
                    tasks["funding_tasks"][key] = set()
                for file_path in missing_files:
                    try:
                        symbol = file_path.split('/')[-2]
                        tasks["funding_tasks"][key].add(symbol)
                        tasks["missing_count"] += 1
                    except Exception:
                        continue

    return tasks


def _fetch_data_with_retry(
    data_type: str,
    symbols: list,
    exchange: str,
    start_date: str,
    end_date: str,
    period: str,
    base_dir: Path,
    max_retries: int,
    supported_exchanges: list
) -> tuple:
    """带重试和回退的数据获取"""
    import time

    for attempt in range(max_retries):
        try:
            fetch_results = batch_fetch_oi_and_funding(
                symbols=symbols,
                start_date=start_date,
                end_date=end_date,
                exchange_id=exchange,
                base_dir=base_dir,
                oi_period=period
            )

            files_count = len(fetch_results.get(f"{data_type}_files", []))
            if files_count > 0:
                return files_count, 0, 0, None

        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                # 尝试回退交易所
                fallback_exchanges = [ex for ex in supported_exchanges if ex != exchange]
                for fallback in fallback_exchanges:
                    try:
                        fetch_results = batch_fetch_oi_and_funding(
                            symbols=symbols,
                            start_date=start_date,
                            end_date=end_date,
                            exchange_id=fallback,
                            base_dir=base_dir,
                            oi_period=period
                        )
                        files_count = len(fetch_results.get(f"{data_type}_files", []))
                        if files_count > 0:
                            return files_count, attempt + 1, 1, None
                    except:
                        continue

                return 0, attempt + 1, 0, f"All attempts failed for {data_type}: {exchange}"

    return 0, max_retries, 0, None


def execute_oi_funding_data_fetch(
    tasks: dict,
    base_dir: Path,
    preferred_exchange: str = "auto",
    max_retries: int = 3
) -> dict:
    """执行 OI 和 Funding Rate 数据获取（带智能重试和错误恢复）"""
    results = {"oi_files": 0, "funding_files": 0, "errors": [], "retries": 0, "fallbacks": 0}

    supported_exchanges = (
        ["binance", "okx"] if preferred_exchange == "auto"
        else [preferred_exchange, "okx" if preferred_exchange == "binance" else "binance"]
        if preferred_exchange in ["binance", "okx"]
        else ["binance", "okx"]
    )

    # 处理 OI 数据
    for (exchange, period, start_date, end_date), symbols in tasks["oi_tasks"].items():
        if not symbols:
            continue

        symbols_list = sorted(list(symbols))
        files, retries, fallbacks, error = _fetch_data_with_retry(
            "oi", symbols_list, exchange, start_date, end_date, period,
            base_dir, max_retries, supported_exchanges
        )

        results["oi_files"] += files
        results["retries"] += retries
        results["fallbacks"] += fallbacks
        if error:
            results["errors"].append(error)

    # 处理 Funding 数据
    for (exchange, start_date, end_date), symbols in tasks["funding_tasks"].items():
        if not symbols:
            continue

        symbols_list = sorted(list(symbols))
        files, retries, fallbacks, error = _fetch_data_with_retry(
            "funding", symbols_list, exchange, start_date, end_date, "1h",
            base_dir, max_retries, supported_exchanges
        )

        results["funding_files"] += files
        results["retries"] += retries
        results["fallbacks"] += fallbacks
        if error:
            results["errors"].append(error)

    return results


def get_default_venue_and_type():
    """获取默认的交易所和标的类型"""
    adapter = get_adapter()
    return adapter.get_venue(), "USDT", "SWAP"


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="Nautilus Trader Unified Runner")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    bt_parser = subparsers.add_parser("backtest", help="Run backtest")
    bt_parser.add_argument("--type", choices=["high", "low"], default="high")
    bt_parser.add_argument("--skip-data", action="store_true")
    bt_parser.add_argument("--erase", action="store_true")
    bt_parser.add_argument("--skip-oi-data", action="store_true")
    bt_parser.add_argument("--force-oi-fetch", action="store_true")
    bt_parser.add_argument("--oi-exchange", choices=["binance", "okx", "auto"], default="auto")
    bt_parser.add_argument("--max-retries", type=int, default=3)
    bt_parser.add_argument("--smart-mode", action="store_true")
    bt_parser.add_argument("--auto-fix", action="store_true")
    bt_parser.add_argument("--data-quality-report", type=str)

    subparsers.add_parser("sandbox", help="Run sandbox (Not implemented yet)")
    subparsers.add_parser("live", help="Run live trading (Not implemented yet)")

    return parser.parse_args()


def load_universe_symbols(adapter, base_dir: Path) -> set:
    """加载Universe符号"""
    universe_symbols = set()
    params = adapter.get_strategy_parameters()
    u_name = params.get("universe_filename") or params.get("universe_filepath")

    if u_name:
        u_path = Path(u_name) if Path(u_name).is_absolute() else base_dir / "data" / Path(u_name).name
        if u_path.exists():
            try:
                with open(u_path, "r") as f:
                    data = json.load(f)
                    universe_symbols = set(data.get("symbols", []))
                    print(f"📊 Universe: {len(universe_symbols)} symbols")
            except Exception as e:
                print(f"⚠️ Failed to load universe: {e}")

    return universe_symbols


def prepare_data_feeds(args, adapter, base_dir: Path, universe_symbols: set):
    """准备数据feeds"""
    print("\n" + "="*70)
    print("📊 DATA PREPARATION")
    print("="*70)

    current_config = adapter.get_config()
    existing_csvs = {feed.csv_file_name for feed in current_config.data_feeds}

    symbols = set()
    if universe_symbols:
        symbols.update(universe_symbols)
    else:
        for feed in current_config.data_feeds:
            try:
                symbol = feed.csv_file_name.split("/")[0]
                symbols.add(symbol)
            except Exception:
                continue

    if symbols:
        start = get_start_date()
        end = get_end_date()
        timeframe = current_config.bar_type.spec.aggregation.value
        exchange = get_venue()

        missing = []
        for symbol in symbols:
            csv_name = f"{symbol}/{exchange}-{symbol}-{timeframe}-{start}_{end}.csv"
            if csv_name not in existing_csvs:
                if not check_single_data_file(symbol, start, end, timeframe, exchange, base_dir):
                    missing.append(symbol)

        if missing:
            print(f"⚠️ {len(missing)} symbols missing data")
            new_configs = run_batch_data_retrieval(sorted(missing), start, end, timeframe, exchange)
            for nc in new_configs:
                if nc.csv_file_name not in existing_csvs:
                    current_config.data_feeds.append(nc)
                    existing_csvs.add(nc.csv_file_name)
            print("✅ Data completion finished")
        else:
            print("✅ All data files exist")

    print("="*70 + "\n")


def check_and_fetch_strategy_data(args, adapter, base_dir: Path, universe_symbols: set):
    """检查并获取策略所需数据"""
    print("\n" + "="*70)
    print("📊 STRATEGY DATA DEPENDENCIES")
    print("="*70)

    current_config = adapter.get_config()
    strategy_tasks = check_strategy_data_dependencies(
        current_config.strategy.params if hasattr(current_config.strategy, 'params') else current_config.strategy,
        get_start_date(),
        get_end_date(),
        base_dir,
        universe_symbols
    )

    if strategy_tasks["missing_count"] > 0:
        print(f"📊 {strategy_tasks['missing_count']} missing data files")

        fetch_results = execute_oi_funding_data_fetch(
            strategy_tasks,
            base_dir,
            preferred_exchange=getattr(args, 'oi_exchange', 'auto'),
            max_retries=getattr(args, 'max_retries', 3)
        )

        total_files = fetch_results["oi_files"] + fetch_results["funding_files"]
        if total_files > 0:
            print(f"✅ Downloaded {total_files} files")
    else:
        print("✅ All strategy data satisfied")

    print("="*70 + "\n")


def update_instrument_definitions(adapter, base_dir: Path, universe_symbols: set):
    """更新instrument定义"""
    try:
        instrument_ids = set()
        current_config = adapter.get_config()

        if current_config.instrument:
            instrument_ids.add(current_config.instrument.instrument_id)

        for feed in current_config.data_feeds:
            if feed.instrument_id:
                instrument_ids.add(feed.instrument_id)

        if universe_symbols:
            venue, base_currency, inst_type = get_default_venue_and_type()
            universe_inst_ids = parse_universe_symbols(universe_symbols, venue, base_currency, inst_type)
            instrument_ids.update(universe_inst_ids)

        if instrument_ids:
            print(f"🔄 Updating {len(instrument_ids)} instruments")
            update_instruments(list(instrument_ids))
    except Exception as e:
        print(f"⚠️ Failed to update instruments: {e}")


def run_backtest(args, adapter):
    """执行回测"""
    try:
        run_file_cleanup()
        if args.type == "high":
            run_high_level()
        else:
            run_low_level()
    except Exception as e:
        print(f"❌ Backtest failed: {e}")
        sys.exit(1)


def main():
    args = parse_arguments()

    if args.command != "backtest":
        print("⚠️ Only backtest command is supported")
        return

    adapter = get_adapter()

    if args.erase:
        catalog_path = BASE_DIR / "data" / "parquet" / adapter.get_strategy_name()
        if catalog_path.exists():
            shutil.rmtree(catalog_path)
            print("✅ Catalog erased")

    universe_symbols = load_universe_symbols(adapter, BASE_DIR)

    if not args.skip_data:
        prepare_data_feeds(args, adapter, BASE_DIR, universe_symbols)
        if not getattr(args, 'skip_oi_data', False):
            check_and_fetch_strategy_data(args, adapter, BASE_DIR, universe_symbols)

    update_instrument_definitions(adapter, BASE_DIR, universe_symbols)
    run_backtest(args, adapter)

if __name__ == "__main__":
    main()
