"""CLI 命令实现"""

from pathlib import Path

from scripts.fetch_instrument import update_instruments
from strategy.core.dependency_checker import check_strategy_data_dependencies
from utils.data_management import execute_oi_funding_data_fetch
from utils.universe import parse_universe_symbols


def check_and_fetch_strategy_data(args, adapter, base_dir: Path, universe_symbols: set):
    """检查并获取策略所需数据"""
    if args.skip_oi_data:
        print("⏩ Skipping OI/Funding data check")
        return

    print("="*70)
    print("📊 Strategy Data Dependencies Check")
    print("="*70)

    current_config = adapter.build_backtest_config()
    strategy_tasks = check_strategy_data_dependencies(
        current_config.strategy.params if hasattr(current_config.strategy, 'params') else current_config.strategy,
        adapter.get_start_date(),
        adapter.get_end_date(),
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
        current_config = adapter.build_backtest_config()

        if current_config.instrument:
            instrument_ids.add(current_config.instrument.instrument_id)

        for feed in current_config.data_feeds:
            if feed.instrument_id:
                instrument_ids.add(feed.instrument_id)

        if universe_symbols:
            from core.schemas import InstrumentType
            venue = adapter.get_venue()
            inst_type = InstrumentType(adapter.env_config.trading.instrument_type)
            universe_inst_ids = parse_universe_symbols(universe_symbols, venue, "USDT", inst_type)
            instrument_ids.update(universe_inst_ids)

        if instrument_ids:
            print(f"🔄 Updating {len(instrument_ids)} instruments")
            update_instruments(list(instrument_ids), base_dir / "data" / "instrument")
    except Exception as e:
        print(f"⚠️ Error updating instruments: {e}")


def run_backtest(args, adapter, base_dir: Path):
    """执行回测"""
    from backtest.engine_high import run_high_level
    from backtest.engine_low import run_low_level
    from utils.file_cleanup import auto_cleanup

    cfg = adapter.build_backtest_config()

    if args.type == "high":
        run_high_level(cfg, base_dir)
    else:
        run_low_level(cfg, base_dir)

    fc = adapter.env_config.file_cleanup
    auto_cleanup(
        base_dir,
        max_files_per_dir=fc.max_files_per_dir,
        enabled=fc.enabled,
        target_dirs=fc.target_dirs,
    )
