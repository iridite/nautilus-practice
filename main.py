import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Add workspace root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from cli.commands import (
    check_and_fetch_strategy_data,
    run_backtest,
    run_live,
    run_sandbox,
    update_instrument_definitions,
)
from core.adapter import get_adapter
from utils.data_management import prepare_data_feeds


def load_universe_symbols(adapter, base_dir: Path) -> set:
    """加载 Universe 符号"""
    try:
        cfg = adapter.build_backtest_config()
        params = cfg.strategy.params if hasattr(cfg.strategy, 'params') else {}

        universe_file = params.get("universe_filename") or params.get("universe_filepath")
        if not universe_file:
            return set()

        u_path = Path(universe_file)
        if not u_path.is_absolute():
            u_path = base_dir / "data" / u_path.name

        if not u_path.exists():
            return set()

        with open(u_path, "r") as f:
            u_data = json.load(f)
            symbols = set()
            for month_list in u_data.values():
                symbols.update(month_list)
            return symbols
    except Exception:
        return set()


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="Nautilus Practice Trading CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    backtest_parser = subparsers.add_parser("backtest", help="Run backtest")
    backtest_parser.add_argument("--type", choices=["high", "low"], default="low")
    backtest_parser.add_argument("--skip-data-check", action="store_true")
    backtest_parser.add_argument("--skip-oi-data", action="store_true")
    backtest_parser.add_argument("--force-oi-fetch", action="store_true")
    backtest_parser.add_argument("--oi-exchange", choices=["binance", "okx", "auto"], default="auto")
    backtest_parser.add_argument("--max-retries", type=int, default=3)

    sandbox_parser = subparsers.add_parser("sandbox", help="Run sandbox trading")
    sandbox_parser.add_argument("--env", type=str, help="Environment name (default: from active.yaml)")

    live_parser = subparsers.add_parser("live", help="Run live trading")
    live_parser.add_argument("--env", type=str, help="Environment name (default: from active.yaml)")

    return parser.parse_args()


def main():
    """主入口"""
    args = parse_arguments()

    if not args.command:
        logger.info("请指定命令。使用 --help 查看可用命令。")
        sys.exit(1)

    adapter = get_adapter()
    universe_symbols = load_universe_symbols(adapter, BASE_DIR)

    if args.command == "backtest":
        prepare_data_feeds(args, adapter, BASE_DIR, universe_symbols)
        check_and_fetch_strategy_data(args, adapter, BASE_DIR, universe_symbols)
        update_instrument_definitions(adapter, BASE_DIR, universe_symbols)
        run_backtest(args, adapter, BASE_DIR)
    elif args.command == "sandbox":
        run_sandbox(args, getattr(args, 'env', None))
    elif args.command == "live":
        run_live(args, getattr(args, 'env', None))


if __name__ == "__main__":
    main()
