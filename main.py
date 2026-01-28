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
from config.definitions import InstrumentConfig, InstrumentType
from config.settings import (
    build_backtest_config,
    get_end_date,
    get_instrument_type,
    get_start_date,
    get_venue,
    run_file_cleanup,
)
from scripts.fetch_instrument import update_instruments
from strategy.base import DataDependency
from utils.config_helpers import parse_universe_symbols
from utils.data_retrival import batch_fetch_ohlcv
from utils.oi_funding_fetcher import batch_fetch_oi_and_funding
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
    """
    检查策略的数据依赖并返回缺失的数据任务

    Parameters
    ----------
    strategy_config
        策略配置对象
    start_date : str
        开始日期
    end_date : str
        结束日期
    base_dir : Path
        基础目录
    universe_symbols : set, optional
        Universe 符号集合

    Returns
    -------
    dict
        包含缺失数据任务的字典
    """
    tasks = {
        "oi_tasks": {},      # (exchange, period, start, end) -> set(symbols)
        "funding_tasks": {}, # (exchange, start, end) -> set(symbols)
        "missing_count": 0,
        "warnings": []
    }

    # 特殊处理：为 OIDivergenceStrategy 硬编码数据依赖
    strategy_name = getattr(strategy_config, '__class__', None)
    if strategy_name and 'OIDivergence' in str(strategy_name):
        from strategy.base import DataDependency
        if not hasattr(strategy_config, 'data_dependencies') or not strategy_config.data_dependencies:
            strategy_config.data_dependencies = [
                DataDependency(
                    data_type="oi",
                    required=True,
                    period="1h",
                    auto_fetch=True
                ),
                DataDependency(
                    data_type="funding",
                    required=True,
                    auto_fetch=True
                )
            ]

    # 检查策略是否有数据依赖声明
    if not hasattr(strategy_config, 'data_dependencies') or not strategy_config.data_dependencies:
        return tasks

    print(f"🔍 Checking strategy data dependencies: {len(strategy_config.data_dependencies)} dependencies found")

    # 获取策略相关的符号列表
    strategy_symbols = set()

    # 从 data_feeds 获取符号
    if hasattr(strategy_config, 'data_feeds') and strategy_config.data_feeds:
        for feed in strategy_config.data_feeds:
            try:
                symbol_quote = feed.csv_file_name.split("/")[0]
                strategy_symbols.add(symbol_quote)
            except Exception:
                continue

    # 从 universe 获取符号
    if universe_symbols:
        for symbol in universe_symbols:
            symbol_str = symbol.split(":")[0]  # SOLUSDT:USDT -> SOLUSDT
            strategy_symbols.add(symbol_str)

    # 从单标的配置获取符号
    if hasattr(strategy_config, 'instrument_id') and strategy_config.instrument_id:
        try:
            # 从 instrument_id 提取符号 (如 BINANCE.BTCUSDT-PERP -> BTCUSDT)
            symbol_part = strategy_config.instrument_id.split('.')[1].split('-')[0]
            strategy_symbols.add(symbol_part)
        except Exception:
            pass

    if not strategy_symbols:
        print("⚠️ No symbols found for strategy data dependency check")
        return tasks

    print(f"📊 Checking data dependencies for {len(strategy_symbols)} symbols: {sorted(list(strategy_symbols))}")

    # 检查每个数据依赖
    for dep in strategy_config.data_dependencies:
        if not dep.auto_fetch:
            continue

        # 确定要检查的符号列表
        check_symbols = dep.symbols if dep.symbols else strategy_symbols

        # 确定交易所和周期
        exchange = dep.exchange or getattr(strategy_config, 'default_data_exchange', 'binance')
        period = dep.period or getattr(strategy_config, 'default_data_period', '1h')

        if dep.data_type == "oi":
            # 检查 OI 数据
            exists, missing_files = check_oi_data_exists(
                list(check_symbols), start_date, end_date, period, exchange, base_dir
            )

            if not exists:
                key = (exchange, period, start_date, end_date)
                if key not in tasks["oi_tasks"]:
                    tasks["oi_tasks"][key] = set()

                # 从缺失文件路径中提取符号
                for file_path in missing_files:
                    try:
                        # 从路径中提取符号: .../BTCUSDT/binance-BTCUSDT-oi-1h-2024-01-01_2024-12-31.csv
                        symbol = file_path.split('/')[-2]
                        tasks["oi_tasks"][key].add(symbol)
                        tasks["missing_count"] += 1
                    except Exception:
                        continue

        elif dep.data_type == "funding":
            # 检查 Funding Rate 数据
            exists, missing_files = check_funding_data_exists(
                list(check_symbols), start_date, end_date, exchange, base_dir
            )

            if not exists:
                key = (exchange, start_date, end_date)
                if key not in tasks["funding_tasks"]:
                    tasks["funding_tasks"][key] = set()

                # 从缺失文件路径中提取符号
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
    """
    获取默认的交易所和标的类型。
    优先从 current_config.instrument 读取，如果为 None 则从全局设置读取。
    """
    current_config = build_backtest_config()
    if current_config.instrument:
        return (
            current_config.instrument.venue_name,
            current_config.instrument.base_currency,
            current_config.instrument.type,
        )
    else:
        # 多标的模式：从全局设置读取默认值
        return get_venue(), "USDT", get_instrument_type()


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
    bt_parser.add_argument(
        "--erase",
        action="store_true",
        help="Erase existing parquet catalog data before running backtest (forces re-import of all CSV data)",
    )
    bt_parser.add_argument(
        "--skip-oi-data",
        action="store_true",
        help="Skip automatic OI and Funding Rate data retrieval",
    )
    bt_parser.add_argument(
        "--force-oi-fetch",
        action="store_true",
        help="Force re-download of all OI and Funding Rate data (ignore existing files)",
    )
    bt_parser.add_argument(
        "--oi-exchange",
        choices=["binance", "okx", "auto"],
        default="auto",
        help="Preferred exchange for OI data (auto = try all available)",
    )
    bt_parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum number of retries for failed data downloads",
    )
    bt_parser.add_argument(
        "--smart-mode",
        action="store_true",
        help="Enable smart data management with automatic optimization",
    )
    bt_parser.add_argument(
        "--auto-fix",
        action="store_true",
        help="Automatically fix data issues (requires --smart-mode)",
    )
    bt_parser.add_argument(
        "--data-quality-report",
        type=str,
        help="Generate data quality report to specified file path",
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

    # 获取当前配置
    current_config = build_backtest_config()

    # 处理 --erase 参数：清除 catalog 数据
    if args.command == "backtest" and args.erase:
        strategy_name = current_config.strategy.name
        catalog_path = BASE_DIR / "data" / "parquet" / strategy_name
        if catalog_path.exists():
            print(f"🗑️  Erasing existing catalog data: {catalog_path}")
            try:
                shutil.rmtree(catalog_path)
                print(f"✅ Catalog data erased successfully.")
            except Exception as e:
                print(f"⚠️ Failed to erase catalog: {e}")
        else:
            print(f"📂 No existing catalog found at: {catalog_path}")

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

        # 统计计数器
        data_exists_count = 0
        data_missing_count = 0
        warnings_list = []

        # 1.1 遍历 data_feeds 收集需要更新的行情数据
        if current_config.data_feeds:
            with tqdm(
                current_config.data_feeds,
                desc="🔍 Checking data_feeds",
                unit="feed",
                ncols=80,
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
            ) as pbar:
                for feed in pbar:
                    try:
                        parts = feed.csv_file_name.split("/")
                        symbol_quote = parts[0]
                        file_parts = parts[1].split("-")
                        exchange = file_parts[0]
                        timeframe = file_parts[2]

                        pbar.set_postfix_str(symbol_quote, refresh=True)

                        exists, warning = check_single_data_file_enhanced(
                            symbol_quote, get_start_date(), get_end_date(), timeframe, exchange, BASE_DIR,
                            check_parquet=True, strategy_name=current_config.strategy.name
                        )
                        if not exists:
                            key = (exchange, timeframe, get_start_date(), get_end_date())
                            tasks.setdefault(key, set()).add(symbol_quote)
                            data_missing_count += 1
                        else:
                            data_exists_count += 1
                            if warning:
                                warnings_list.append(warning)
                    except Exception as e:
                        tqdm.write(
                            f"⚠️ Failed to parse data feed config: {feed.label}, error: {e}"
                        )

        # 收集已检查的符号，避免重复检查
        checked_symbols = set()
        for feed in current_config.data_feeds:
            try:
                parts = feed.csv_file_name.split("/")
                symbol_quote = parts[0]
                checked_symbols.add(symbol_quote)
            except Exception:
                continue

        # 打印收集到的警告
        for warning in warnings_list:
            print(warning)
        warnings_list.clear()

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

            sorted_universe = sorted(list(universe_symbols))
            # 过滤掉已经检查过的符号
            universe_to_check = []
            for symbol in sorted_universe:
                symbol_str = symbol.split(":")[0]  # SOLUSDT:USDT -> SOLUSDT
                if symbol_str not in checked_symbols:
                    universe_to_check.append(symbol)
                    checked_symbols.add(symbol_str)

            if universe_to_check:
                with tqdm(
                    universe_to_check,
                    desc="🌌 Checking universe",
                    unit="symbol",
                    ncols=80,
                    bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
                ) as pbar:
                    for symbol in pbar:
                        symbol_str = symbol.split(":")[0]  # SOLUSDT:USDT -> SOLUSDT
                        pbar.set_postfix_str(symbol_str, refresh=True)

                        exists, warning = check_single_data_file_enhanced(
                            symbol_str, get_start_date(), get_end_date(), timeframe, exchange, BASE_DIR,
                            check_parquet=True, strategy_name=current_config.strategy.name
                        )
                        if not exists:
                            key = (exchange, timeframe, get_start_date(), get_end_date())
                            tasks.setdefault(key, set()).add(symbol_str)
                            data_missing_count += 1
                        else:
                            data_exists_count += 1
                            if warning:
                                warnings_list.append(warning)
            else:
                print("🌌 Universe symbols already checked in data_feeds")

            # 打印收集到的警告
            for warning in warnings_list:
                print(warning)

        # 打印数据检查摘要
        print(
            f"📊 Data check summary: {data_exists_count} exists, {data_missing_count} missing"
        )

        # 如果有 Universe，进行数据覆盖范围分析
        if universe_symbols:
            print("==========================================")
            print("📈 Analyzing Universe Data Coverage...")

            try:
                # 获取默认参数
                venue, base_currency, inst_type = get_default_venue_and_type()

                if main_feed:
                    try:
                        parts = main_feed.csv_file_name.split("/")
                        file_parts = parts[1].split("-")
                        exchange = file_parts[0]
                        timeframe = file_parts[2]
                    except Exception:
                        exchange = venue.lower()
                        timeframe = "1h"
                else:
                    exchange = venue.lower()
                    timeframe = "1h"

                # 分析CSV数据覆盖情况（基于已有的检查结果，避免重复检查）
                csv_complete = data_exists_count
                csv_missing = data_missing_count

                # 分析Parquet数据覆盖情况
                coverage_analysis = analyze_universe_data_coverage(
                    universe_symbols,
                    get_start_date(),
                    get_end_date(),
                    timeframe,
                    exchange,
                    BASE_DIR,
                    current_config.strategy.name
                )

                # 显示分析结果 - 双列格式
                print(f"📊 Universe Data Coverage Analysis:")
                print(f"   Total symbols: {coverage_analysis['total_symbols']}")
                print(f"   ┌─────────────────────────────────┬─────────────────────────────────┐")
                print(f"   │           CSV Data              │         Parquet Data            │")
                print(f"   ├─────────────────────────────────┼─────────────────────────────────┤")
                print(f"   │ Available: {csv_complete:<18} │ Complete (100%): {coverage_analysis['summary']['sufficient_count']:<14} │")
                print(f"   │ Missing: {csv_missing:<20} │ Partial (80-99%): {coverage_analysis['summary']['partial_count']:<13} │")
                print(f"   │ Coverage: {(csv_complete/coverage_analysis['total_symbols']*100):.1f}%{'':<16} │ No data (0%): {coverage_analysis['summary']['no_data_count']:<16} │")
                print(f"   │                                 │ Avg coverage: {coverage_analysis['summary']['avg_coverage_pct']:.1f}%{'':<13} │")
                print(f"   └─────────────────────────────────┴─────────────────────────────────┘")


                # 显示数据覆盖不足的标的
                if coverage_analysis['symbols_with_no_data']:
                    print(f"⚠️  Symbols with no data: {len(coverage_analysis['symbols_with_no_data'])}")
                    for symbol in coverage_analysis['symbols_with_no_data'][:5]:  # 只显示前5个
                        print(f"   • {symbol}")
                    if len(coverage_analysis['symbols_with_no_data']) > 5:
                        print(f"   ... and {len(coverage_analysis['symbols_with_no_data']) - 5} more")

                # 显示部分数据的标的
                if coverage_analysis['symbols_with_partial_data']:
                    print(f"📊 Symbols with partial data: {len(coverage_analysis['symbols_with_partial_data'])}")
                    for symbol in coverage_analysis['symbols_with_partial_data'][:3]:  # 只显示前3个
                        stats = coverage_analysis['coverage_stats'][symbol]
                        print(f"   • {symbol}: {stats['coverage_percentage']:.1f}% ({stats['actual_start']} to {stats['actual_end']})")
                    if len(coverage_analysis['symbols_with_partial_data']) > 3:
                        print(f"   ... and {len(coverage_analysis['symbols_with_partial_data']) - 3} more")

            except Exception as e:
                print(f"⚠️ Failed to analyze universe data coverage: {e}")

            print("==========================================")

        # 1.3 自动数据补全功能（先检查，后补全）
        # 记录已经存在的 csv，防止重复添加
        existing_csvs = {f.csv_file_name for f in current_config.data_feeds}

        if data_missing_count > 0:
            print(f"🔧 Auto-completing {data_missing_count} missing data files...")

            for (exchange, timeframe, start, end), symbols in tasks.items():
                if symbols:  # 如果这个任务组有缺失的标的
                    print(f"📊 Fetching {len(symbols)} symbols for {exchange} {timeframe}...")
                    new_configs = run_batch_data_retrieval(
                        sorted(list(symbols)), start, end, timeframe, exchange
                    )
                    # 将抓取成功后生成的 DataConfig 注入到全局配置中
                    for nc in new_configs:
                        if nc.csv_file_name not in existing_csvs:
                            print(f"✅ Auto-added: {nc.csv_file_name}")
                            current_config.data_feeds.append(nc)
                            existing_csvs.add(nc.csv_file_name)

            print("✅ Auto data completion finished!")
        else:
            print("✅ All required data files already exist!")

        print("==========================================\n")

    # 1.4 检查策略数据依赖（OI、Funding Rate 等）
    if args.command == "backtest" and not args.skip_data and not getattr(args, 'skip_oi_data', False):
        print("==========================================")
        print("📊 Checking Strategy Data Dependencies...")

        # 显示配置信息
        if hasattr(args, 'oi_exchange') and args.oi_exchange != "auto":
            print(f"🔧 Preferred OI exchange: {args.oi_exchange.upper()}")
        if hasattr(args, 'max_retries'):
            print(f"🔧 Max retries: {args.max_retries}")
        if hasattr(args, 'force_oi_fetch') and args.force_oi_fetch:
            print("🔧 Force re-download mode enabled")

        try:
            # 特殊处理：为 OI Divergence 策略检查 OI 数据
            strategy_name = current_config.strategy.name if hasattr(current_config.strategy, 'name') else ""
            if "OIDivergence" in strategy_name or "oi_divergence" in strategy_name.lower():
                from config.settings import get_primary_symbol

                # 获取当前配置的交易对
                primary_symbol = get_primary_symbol()
                print(f"🔍 Checking OI/Funding data for {primary_symbol}...")

                # 检查 OI 数据
                oi_exists, oi_missing = check_oi_data_exists(
                    [primary_symbol],
                    get_start_date(),
                    get_end_date(),
                    "1h",
                    "binance",
                    BASE_DIR
                )

                # 检查 Funding Rate 数据
                funding_exists, funding_missing = check_funding_data_exists(
                    [primary_symbol],
                    get_start_date(),
                    get_end_date(),
                    "binance",
                    BASE_DIR
                )

                # 如果数据缺失，自动下载
                if not oi_exists or not funding_exists:
                    missing_types = []
                    if not oi_exists:
                        missing_types.append("OI")
                    if not funding_exists:
                        missing_types.append("Funding Rate")

                    print(f"⚠️  Missing {', '.join(missing_types)} data for {primary_symbol}")
                    print(f"🚀 Auto-downloading missing data...")

                    try:
                        fetch_results = batch_fetch_oi_and_funding(
                            symbols=[primary_symbol],
                            start_date=get_start_date(),
                            end_date=get_end_date(),
                            exchange_id="binance",
                            base_dir=BASE_DIR,
                            oi_period="1h"
                        )

                        oi_count = len(fetch_results.get("oi_files", []))
                        funding_count = len(fetch_results.get("funding_files", []))

                        if oi_count > 0 or funding_count > 0:
                            print(f"✅ Successfully downloaded:")
                            if oi_count > 0:
                                print(f"   📈 {oi_count} OI data file(s)")
                            if funding_count > 0:
                                print(f"   💰 {funding_count} Funding Rate data file(s)")
                        else:
                            print(f"⚠️  No data downloaded - check exchange availability")

                    except Exception as e:
                        print(f"❌ Failed to download data: {e}")
                        print(f"   Continuing with existing data...")
                else:
                    print(f"✅ OI and Funding Rate data available for {primary_symbol}")

            # 检查策略数据依赖
            strategy_tasks = check_strategy_data_dependencies(
                current_config.strategy.params if hasattr(current_config.strategy, 'params') else current_config.strategy,
                get_start_date(),
                get_end_date(),
                BASE_DIR,
                universe_symbols
            )

            if strategy_tasks["missing_count"] > 0:
                print(f"📊 Strategy data dependencies: {strategy_tasks['missing_count']} missing data files found")

                # 显示缺失的数据类型统计
                oi_task_count = sum(len(symbols) for symbols in strategy_tasks["oi_tasks"].values())
                funding_task_count = sum(len(symbols) for symbols in strategy_tasks["funding_tasks"].values())

                if oi_task_count > 0:
                    print(f"  📈 Missing OI data for {oi_task_count} symbol-period combinations")
                if funding_task_count > 0:
                    print(f"  💰 Missing Funding Rate data for {funding_task_count} symbols")

                # 执行数据获取
                if oi_task_count > 0 or funding_task_count > 0:
                    print("🚀 Fetching missing strategy data...")
                    fetch_results = execute_oi_funding_data_fetch(
                        strategy_tasks,
                        BASE_DIR,
                        preferred_exchange=getattr(args, 'oi_exchange', 'auto'),
                        max_retries=getattr(args, 'max_retries', 3),
                        force_fetch=getattr(args, 'force_oi_fetch', False)
                    )

                    # 显示获取结果
                    total_files = fetch_results["oi_files"] + fetch_results["funding_files"]
                    if total_files > 0:
                        print(f"✅ Successfully downloaded {total_files} data files:")
                        if fetch_results["oi_files"] > 0:
                            print(f"   📈 {fetch_results['oi_files']} OI data files")
                        if fetch_results["funding_files"] > 0:
                            print(f"   💰 {fetch_results['funding_files']} Funding Rate data files")

                    # 显示重试和回退统计
                    if fetch_results.get("retries", 0) > 0:
                        print(f"🔄 Total retries performed: {fetch_results['retries']}")
                    if fetch_results.get("fallbacks", 0) > 0:
                        print(f"🔄 Fallback exchanges used: {fetch_results['fallbacks']}")

                    # 显示错误信息
                    if fetch_results["errors"]:
                        print(f"❌ {len(fetch_results['errors'])} errors encountered:")
                        for error in fetch_results["errors"]:
                            print(f"   • {error}")

            else:
                print("✅ All strategy data dependencies satisfied")

        except Exception as e:
            print(f"⚠️ Error checking strategy data dependencies: {e}")
            print("   Continuing with existing data...")

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

    # 3. File Cleanup (before backtest execution)
    if args.command == "backtest":
        try:
            deleted_count = run_file_cleanup()
            if deleted_count > 0:
                print(f"🧹 Cleaned up {deleted_count} old files from log/output directories")
        except Exception as e:
            print(f"⚠️ File cleanup warning: {e}")

    # 4. Execute Commands
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
