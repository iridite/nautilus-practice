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
    OIDataValidator,
    analyze_universe_data_coverage,
    check_data_exists,
    check_funding_data_exists,
    check_oi_data_exists,
    check_parquet_data_coverage,
    check_single_data_file,
    check_single_data_file_enhanced,
    validate_funding_data_structure,
    validate_oi_data_structure,
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


def check_strategy_data_dependencies(
    strategy_config,
    start_date: str,
    end_date: str,
    base_dir: Path,
    universe_symbols: set = None
) -> dict:
    """检查策略数据依赖并返回缺失的数据任务"""
    tasks = {
        "oi_tasks": {},
        "funding_tasks": {},
        "missing_count": 0,
        "warnings": []
    }

    # 获取策略所需的数据类型
    data_types = getattr(strategy_config, 'data_types', [])
    if not data_types:
        return tasks

    print(f"🔍 检查策略数据依赖: {len(data_types)} 个数据类型")

    # 获取策略相关的符号列表
    strategy_symbols = set()

    if hasattr(strategy_config, 'data_feeds') and strategy_config.data_feeds:
        for feed in strategy_config.data_feeds:
            try:
                symbol_quote = feed.csv_file_name.split("/")[0]
                strategy_symbols.add(symbol_quote)
            except Exception:
                continue

    if universe_symbols:
        for symbol in universe_symbols:
            symbol_str = symbol.split(":")[0]
            strategy_symbols.add(symbol_str)

    if hasattr(strategy_config, 'instrument_id') and strategy_config.instrument_id:
        try:
            symbol_part = strategy_config.instrument_id.split('.')[1].split('-')[0]
            strategy_symbols.add(symbol_part)
        except Exception:
            pass

    if not strategy_symbols:
        print("⚠️ 未找到符号")
        return tasks

    print(f"📊 检查 {len(strategy_symbols)} 个符号的数据依赖")

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


def execute_oi_funding_data_fetch(
    tasks: dict,
    base_dir: Path,
    preferred_exchange: str = "auto",
    max_retries: int = 3,
    force_fetch: bool = False
) -> dict:
    """
    执行 OI 和 Funding Rate 数据获取（带智能重试和错误恢复）

    Parameters
    ----------
    tasks : dict
        数据获取任务字典
    base_dir : Path
        基础目录
    preferred_exchange : str, optional
        首选交易所，默认 "auto"
    max_retries : int, optional
        最大重试次数，默认 3
    force_fetch : bool, optional
        是否强制重新获取，默认 False

    Returns
    -------
    dict
        获取结果统计
    """
    results = {"oi_files": 0, "funding_files": 0, "errors": [], "retries": 0, "fallbacks": 0}

    # 支持的交易所列表（按优先级排序）
    if preferred_exchange == "auto":
        supported_exchanges = ["binance", "okx"]
    elif preferred_exchange in ["binance", "okx"]:
        supported_exchanges = [preferred_exchange, "binance" if preferred_exchange == "okx" else "okx"]
    else:
        supported_exchanges = ["binance", "okx"]

    # 执行 OI 数据获取
    for (exchange, period, start_date, end_date), symbols in tasks["oi_tasks"].items():
        if not symbols:
            continue

        symbols_list = sorted(list(symbols))
        success = False
        current_exchange = exchange

        # 尝试从指定交易所获取数据
        for attempt in range(max_retries):
            print(f"📊 Fetching OI data: {current_exchange} {period} for {len(symbols_list)} symbols (attempt {attempt + 1}/{max_retries})")

            try:
                fetch_results = batch_fetch_oi_and_funding(
                    symbols=symbols_list,
                    start_date=start_date,
                    end_date=end_date,
                    exchange_id=current_exchange,
                    base_dir=base_dir,
                    oi_period=period
                )

                oi_files_count = len(fetch_results.get("oi_files", []))
                if oi_files_count > 0:
                    results["oi_files"] += oi_files_count
                    print(f"✅ Successfully fetched {oi_files_count} OI files from {current_exchange}")
                    success = True
                    break
                else:
                    print(f"⚠️ No OI files downloaded from {current_exchange} (attempt {attempt + 1})")

            except Exception as e:
                error_msg = f"Attempt {attempt + 1} failed for OI data from {current_exchange}: {e}"
                print(f"❌ {error_msg}")
                results["retries"] += 1

                if attempt < max_retries - 1:
                    print(f"🔄 Retrying in 5 seconds...")
                    import time
                    time.sleep(5)

        # 如果主交易所失败，尝试备用交易所
        if not success and current_exchange in supported_exchanges:
            fallback_exchanges = [ex for ex in supported_exchanges if ex != current_exchange]

            for fallback_exchange in fallback_exchanges:
                print(f"🔄 Trying fallback exchange: {fallback_exchange}")
                results["fallbacks"] += 1

                try:
                    fetch_results = batch_fetch_oi_and_funding(
                        symbols=symbols_list,
                        start_date=start_date,
                        end_date=end_date,
                        exchange_id=fallback_exchange,
                        base_dir=base_dir,
                        oi_period=period
                    )

                    oi_files_count = len(fetch_results.get("oi_files", []))
                    if oi_files_count > 0:
                        results["oi_files"] += oi_files_count
                        print(f"✅ Successfully fetched {oi_files_count} OI files from fallback {fallback_exchange}")
                        success = True
                        break

                except Exception as e:
                    print(f"❌ Fallback {fallback_exchange} also failed: {e}")

        if not success:
            error_msg = f"All attempts failed for OI data: {exchange} {period} ({len(symbols_list)} symbols)"
            results["errors"].append(error_msg)

    # 执行 Funding Rate 数据获取（类似的重试逻辑）
    for (exchange, start_date, end_date), symbols in tasks["funding_tasks"].items():
        if not symbols:
            continue

        symbols_list = sorted(list(symbols))
        success = False
        current_exchange = exchange

        # 尝试从指定交易所获取数据
        for attempt in range(max_retries):
            print(f"💰 Fetching Funding Rate data: {current_exchange} for {len(symbols_list)} symbols (attempt {attempt + 1}/{max_retries})")

            try:
                fetch_results = batch_fetch_oi_and_funding(
                    symbols=symbols_list,
                    start_date=start_date,
                    end_date=end_date,
                    exchange_id=current_exchange,
                    base_dir=base_dir,
                    oi_period="1h"  # Funding rate 不依赖周期
                )

                funding_files_count = len(fetch_results.get("funding_files", []))
                if funding_files_count > 0:
                    results["funding_files"] += funding_files_count
                    print(f"✅ Successfully fetched {funding_files_count} Funding Rate files from {current_exchange}")
                    success = True
                    break
                else:
                    print(f"⚠️ No Funding Rate files downloaded from {current_exchange} (attempt {attempt + 1})")

            except Exception as e:
                error_msg = f"Attempt {attempt + 1} failed for Funding Rate data from {current_exchange}: {e}"
                print(f"❌ {error_msg}")
                results["retries"] += 1

                if attempt < max_retries - 1:
                    print(f"🔄 Retrying in 5 seconds...")
                    import time
                    time.sleep(5)

        # 如果主交易所失败，尝试备用交易所
        if not success and current_exchange in supported_exchanges:
            fallback_exchanges = [ex for ex in supported_exchanges if ex != current_exchange]

            for fallback_exchange in fallback_exchanges:
                print(f"🔄 Trying fallback exchange: {fallback_exchange}")
                results["fallbacks"] += 1

                try:
                    fetch_results = batch_fetch_oi_and_funding(
                        symbols=symbols_list,
                        start_date=start_date,
                        end_date=end_date,
                        exchange_id=fallback_exchange,
                        base_dir=base_dir,
                        oi_period="1h"
                    )

                    funding_files_count = len(fetch_results.get("funding_files", []))
                    if funding_files_count > 0:
                        results["funding_files"] += funding_files_count
                        print(f"✅ Successfully fetched {funding_files_count} Funding Rate files from fallback {fallback_exchange}")
                        success = True
                        break

                except Exception as e:
                    print(f"❌ Fallback {fallback_exchange} also failed: {e}")

        if not success:
            error_msg = f"All attempts failed for Funding Rate data: {exchange} ({len(symbols_list)} symbols)"
            results["errors"].append(error_msg)

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
    if args.command != "backtest" or args.skip_data:
        return

    print("\n" + "="*70)
    print("📊 DATA PREPARATION")
    print("="*70)

    current_config = adapter.get_config()
    existing_csvs = {feed.csv_file_name for feed in current_config.data_feeds}

    if args.smart_mode:
        print("🧠 Smart Data Management Mode")
        manager = SmartDataManager(base_dir)
        manager.analyze_and_optimize(
            auto_fix=args.auto_fix,
            report_path=args.data_quality_report
        )

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
    if args.command != "backtest" or args.skip_data or getattr(args, 'skip_oi_data', False):
        return

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
            max_retries=getattr(args, 'max_retries', 3),
            force_fetch=getattr(args, 'force_oi_fetch', False)
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
    if args.command == "backtest":
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

    if args.command == "backtest" and args.erase:
        adapter = get_adapter()
        strategy_name = adapter.get_strategy_name()
        catalog_path = BASE_DIR / "data" / "parquet" / strategy_name
        if catalog_path.exists():
            print(f"🗑️ Erasing catalog: {catalog_path}")
            shutil.rmtree(catalog_path)
            print("✅ Catalog erased")

    adapter = get_adapter()
    universe_symbols = load_universe_symbols(adapter, BASE_DIR)

    prepare_data_feeds(args, adapter, BASE_DIR, universe_symbols)
    check_and_fetch_strategy_data(args, adapter, BASE_DIR, universe_symbols)
    update_instrument_definitions(adapter, BASE_DIR, universe_symbols)

    run_backtest(args, adapter)

if __name__ == "__main__":
    main()
