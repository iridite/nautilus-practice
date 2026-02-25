"""CLI 命令实现"""

import asyncio
import logging
import sys
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from backtest.tui_manager import get_tui, is_tui_enabled
from scripts.fetch_instrument import update_instruments
from strategy.core.dependency_checker import check_strategy_data_dependencies
from utils.oi_funding_adapter import execute_oi_funding_data_fetch
from utils.universe import parse_universe_symbols

logger = logging.getLogger(__name__)


def check_and_fetch_strategy_data(args, adapter, base_dir: Path, universe_symbols: set):
    """检查并获取策略所需数据"""
    tui = get_tui()
    use_tui = is_tui_enabled()

    if args.skip_oi_data:
        if use_tui:
            tui.add_log("Skipping OI/Funding data check", "INFO")
        else:
            logger.info("⏩ Skipping OI/Funding data check")
        return

    if use_tui:
        tui.start_phase("Strategy Data Dependencies Check")
    else:
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
        if use_tui:
            tui.add_log(f"{strategy_tasks['missing_count']} missing data files", "INFO")
            tui.start_phase("Fetching Strategy Data")
        else:
            logger.info(f"📊 {strategy_tasks['missing_count']} missing data files")

        fetch_results = execute_oi_funding_data_fetch(
            strategy_tasks,
            base_dir,
            preferred_exchange=getattr(args, "oi_exchange", "auto"),
            max_retries=getattr(args, "max_retries", 3),
        )

        total_files = fetch_results["oi_files"] + fetch_results["funding_files"]
        if total_files > 0:
            if use_tui:
                tui.add_log(f"Downloaded {total_files} files", "INFO")
                tui.update_stat("strategy_data_files", total_files)
            else:
                logger.info(f"✅ Downloaded {total_files} files")
    else:
        if use_tui:
            tui.add_log("All strategy data satisfied", "INFO")
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
            tui = get_tui()
            use_tui = is_tui_enabled()

            if use_tui:
                tui.start_phase("Updating Instruments", total=len(instrument_ids))
                tui.add_log(f"Updating {len(instrument_ids)} instruments", "INFO")
            else:
                logger.info(f"🔄 Updating {len(instrument_ids)} instruments")

            update_instruments(list(instrument_ids), base_dir / "data" / "instrument")
    except Exception as e:
        tui = get_tui()
        if is_tui_enabled():
            tui.add_log(f"Error updating instruments: {e}", "ERROR")
        else:
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

    tui = get_tui()
    use_tui = is_tui_enabled()

    if use_tui:
        tui.start_phase("Starting Backtest")
        tui.add_log(f"Backtest Type: {args.type}", "INFO")
        strategy_name = getattr(
            cfg.strategy, "strategy_path", getattr(cfg.strategy, "class_name", "Unknown")
        )
        tui.add_log(f"Strategy: {strategy_name}", "INFO")

        # 停止 TUI 并切换到标准 logging
        time.sleep(0.5)  # 短暂延迟，让用户看到最后的状态
        stats = tui.get_stats_summary()
        tui.stop()

        # 重新配置 logging 使用标准输出
        from utils.logging_config import setup_logging
        setup_logging(level=logging.INFO, force_standard=True)

        # 输出数据处理总结
        logger.info("=" * 80)
        logger.info("✅ Data preparation complete")
        logger.info("-" * 80)

        if stats:
            fetched = stats.get("fetched", 0)
            cached = stats.get("cached", 0)
            skipped = stats.get("skipped", 0)
            if fetched or cached or skipped:
                logger.info(f"Data retrieval: {fetched} fetched, {cached} cached, {skipped} skipped")

            inst_new = stats.get("instruments_new", 0)
            inst_existed = stats.get("instruments_existed", 0)
            inst_failed = stats.get("instruments_failed", 0)
            if inst_new or inst_existed or inst_failed:
                logger.info(f"Instruments: {inst_new} new, {inst_existed} existed, {inst_failed} failed")

        logger.info("-" * 80)
        logger.info(f"🚀 Starting backtest engine ({args.type} level)...")
        logger.info("=" * 80)

        # 暂停 1.5 秒，让用户阅读数据处理总结
        time.sleep(1.5)
    else:
        logger.info(f"Starting backtest: {args.type}")
        strategy_name = getattr(
            cfg.strategy, "strategy_path", getattr(cfg.strategy, "class_name", "Unknown")
        )
        logger.info(f"Strategy: {strategy_name}")

    if args.type == "high":
        run_high_level(cfg, base_dir)
    else:
        run_low_level(cfg, base_dir)

    # Cleanup（TUI 已停止，使用普通 logging）
    logger.info("Running cleanup...")

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

    logger.info("✅ Backtest complete")
