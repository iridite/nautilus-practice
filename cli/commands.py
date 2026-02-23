"""CLI 命令实现"""

import asyncio
import logging
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scripts.fetch_instrument import update_instruments
from strategy.core.dependency_checker import check_strategy_data_dependencies
from utils.oi_funding_adapter import execute_oi_funding_data_fetch
from utils.universe import parse_universe_symbols

logger = logging.getLogger(__name__)


def check_and_fetch_strategy_data(args, adapter, base_dir: Path, universe_symbols: set):
    """检查并获取策略所需数据"""
    if args.skip_oi_data:
        logger.info("⏩ Skipping OI/Funding data check")
        return

    logger.info("📊 Strategy Data Dependencies Check")

    current_config = adapter.build_backtest_config()
    strategy_tasks = check_strategy_data_dependencies(
        current_config.strategy.params
        if hasattr(current_config.strategy, "params")
        else current_config.strategy,
        adapter.get_start_date(),
        adapter.get_end_date(),
        base_dir,
        universe_symbols,
    )

    if strategy_tasks["missing_count"] > 0:
        logger.info(f"📊 {strategy_tasks['missing_count']} missing data files")

        fetch_results = execute_oi_funding_data_fetch(
            strategy_tasks,
            base_dir,
            preferred_exchange=getattr(args, "oi_exchange", "auto"),
            max_retries=getattr(args, "max_retries", 3),
        )

        total_files = fetch_results["oi_files"] + fetch_results["funding_files"]
        if total_files > 0:
            logger.info(f"✅ Downloaded {total_files} files")
    else:
        logger.info("✅ All strategy data satisfied\n")


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
            logger.info(f"🔄 Updating {len(instrument_ids)} instruments")
            update_instruments(list(instrument_ids), base_dir / "data" / "instrument")
    except Exception as e:
        logger.error(f"⚠️ Error updating instruments: {e}")


def run_live(args, env_name=None):
    """执行实盘交易"""
    from live.engine import run_live

    logger.info("🚀 Starting live trading...")
    asyncio.run(run_live(env_name))


def run_sandbox(args, env_name=None):
    """执行沙盒交易"""
    from sandbox.engine import run_sandbox

    logger.info("🧪 Starting sandbox trading...")
    asyncio.run(run_sandbox(env_name))


def run_backtest(args, adapter, base_dir: Path):
    """执行回测"""
    from backtest.engine_high import run_high_level
    from backtest.engine_low import run_low_level

    from .file_cleanup import auto_cleanup, auto_cleanup_by_age

    cfg = adapter.build_backtest_config()

    if args.type == "high":
        run_high_level(cfg, base_dir)
    else:
        run_low_level(cfg, base_dir)

    fc = adapter.env_config.file_cleanup
    if fc.use_time_rotation:
        auto_cleanup_by_age(
            base_dir,
            keep_days=fc.keep_days,
            delete_days=fc.delete_days,
            enabled=fc.enabled,
            target_dirs=fc.target_dirs,
        )
    else:
        auto_cleanup(
            base_dir,
            max_files_per_dir=fc.max_files_per_dir,
            enabled=fc.enabled,
            target_dirs=fc.target_dirs,
        )
