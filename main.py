import argparse
import json
import logging
import sys
from pathlib import Path

# Add workspace root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from backtest.tui_manager import get_tui, is_tui_enabled
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)
from cli.commands import (
    check_and_fetch_strategy_data,
    run_backtest,
    run_live,
    run_sandbox,
    update_instrument_definitions,
)
from core.adapter import get_adapter
from utils.data_management import prepare_data_feeds


def override_symbol_config(adapter, symbol: str, base_dir: Path):
    """
    动态覆盖配置中的交易对

    Args:
        adapter: 配置适配器
        symbol: 交易对符号（如 BTCUSDT）
        base_dir: 项目根目录
    """
    import yaml

    # 1. 更新策略配置
    strategy_file = base_dir / "config" / "strategies" / f"{adapter.active_config.strategy}.yaml"
    with open(strategy_file, "r", encoding="utf-8") as f:
        strategy_config = yaml.safe_load(f)

    # 更新 symbols 和 instrument_id
    strategy_config["parameters"]["symbols"] = [symbol]
    strategy_config["parameters"]["instrument_id"] = f"{symbol}-PERP.BINANCE"
    strategy_config["parameters"]["bar_type"] = f"{symbol}-PERP.BINANCE-1-HOUR-LAST-EXTERNAL"

    with open(strategy_file, "w", encoding="utf-8") as f:
        yaml.dump(strategy_config, f, default_flow_style=False, allow_unicode=True)

    # 2. 更新环境配置
    env_file = base_dir / "config" / "environments" / f"{adapter.active_config.environment}.yaml"
    with open(env_file, "r", encoding="utf-8") as f:
        env_config = yaml.safe_load(f)

    # 获取时间范围
    start_date = env_config.get("backtest", {}).get("start_date", "2024-01-01")
    end_date = env_config.get("backtest", {}).get("end_date", "2024-12-31")

    # 更新数据源配置（只更新 data_feeds，保留其他配置）
    env_config["data_feeds"] = [
        {
            "instrument_id": f"{symbol}-PERP.BINANCE",
            "bar_aggregation": "HOUR",
            "bar_period": 1,
            "price_type": "LAST",
            "origination": "EXTERNAL",
            "csv_file_name": f"{symbol}-PERP/binance-{symbol}-PERP-1h-{start_date}_{end_date}.csv",
            "label": "main",
        },
        {
            "instrument_id": f"{symbol}.BINANCE",
            "bar_aggregation": "HOUR",
            "bar_period": 1,
            "price_type": "LAST",
            "origination": "EXTERNAL",
            "csv_file_name": f"{symbol}/binance-{symbol}-1h-{start_date}_{end_date}.csv",
            "label": "main",
        },
    ]

    with open(env_file, "w", encoding="utf-8") as f:
        yaml.dump(env_config, f, default_flow_style=False, allow_unicode=True)

    # 3. 更新 active.yaml 中的 overrides（移除 initial_balance 覆盖）
    active_file = base_dir / "config" / "active.yaml"
    with open(active_file, "r", encoding="utf-8") as f:
        active_data = yaml.safe_load(f)

    # 移除 overrides 中的 initial_balance，让环境配置生效
    if "overrides" in active_data and "trading" in active_data["overrides"]:
        if "initial_balance" in active_data["overrides"]["trading"]:
            del active_data["overrides"]["trading"]["initial_balance"]

    with open(active_file, "w", encoding="utf-8") as f:
        yaml.dump(active_data, f, default_flow_style=False, allow_unicode=True)

    logger.info(f"✅ 配置已更新为 {symbol}")


def load_universe_symbols(adapter, base_dir: Path) -> set:
    """加载 Universe 符号"""
    try:
        cfg = adapter.build_backtest_config()
        params = cfg.strategy.params if hasattr(cfg.strategy, "params") else {}

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
    backtest_parser.add_argument(
        "--env", type=str, default="dev", help="Environment name (default: dev)"
    )
    backtest_parser.add_argument(
        "--symbol", type=str, help="Trading symbol (e.g., BTCUSDT, SOLUSDT, BNBUSDT)"
    )
    backtest_parser.add_argument("--skip-data-check", action="store_true")
    backtest_parser.add_argument("--skip-oi-data", action="store_true")
    backtest_parser.add_argument("--force-oi-fetch", action="store_true")
    backtest_parser.add_argument(
        "--oi-exchange", choices=["binance", "okx", "auto"], default="auto"
    )
    backtest_parser.add_argument("--max-retries", type=int, default=3)

    sandbox_parser = subparsers.add_parser("sandbox", help="Run sandbox trading")
    sandbox_parser.add_argument(
        "--env", type=str, help="Environment name (default: from active.yaml)"
    )

    live_parser = subparsers.add_parser("live", help="Run live trading")
    live_parser.add_argument("--env", type=str, help="Environment name (default: from active.yaml)")

    return parser.parse_args()


def main():
    """主入口"""
    # 配置 logging（必须在任何 logger 调用之前）
    setup_logging(level=logging.INFO)

    args = parse_arguments()

    if not args.command:
        logger.info("请指定命令。使用 --help 查看可用命令。")
        sys.exit(1)

    # 根据命令选择环境
    if args.command == "backtest":
        # 回测默认使用 dev 环境（可通过 --env 覆盖）
        env_name = getattr(args, "env", "dev")
        # 临时修改 active.yaml 的环境设置
        import yaml

        active_file = BASE_DIR / "config" / "active.yaml"
        with open(active_file, "r") as f:
            active_data = yaml.safe_load(f)
        original_env = active_data.get("environment", "dev")
        active_data["environment"] = env_name
        with open(active_file, "w") as f:
            yaml.dump(active_data, f, default_flow_style=False, allow_unicode=True)

        try:
            adapter = get_adapter()
            adapter.reload()
        finally:
            # 恢复原始环境设置
            active_data["environment"] = original_env
            with open(active_file, "w") as f:
                yaml.dump(active_data, f, default_flow_style=False, allow_unicode=True)
    else:
        # sandbox 和 live 使用 active.yaml 或 --env 参数
        adapter = get_adapter()

    # 如果指定了 symbol，动态覆盖配置
    if args.command == "backtest" and hasattr(args, "symbol") and args.symbol:
        override_symbol_config(adapter, args.symbol, BASE_DIR)
        # 重新加载配置
        adapter.reload()

    universe_symbols = load_universe_symbols(adapter, BASE_DIR)

    if args.command == "backtest":
        # 启动全局 TUI（如果启用）
        tui = get_tui()
        if is_tui_enabled():
            with tui:
                tui.start_phase("Backtest Initialization")
                prepare_data_feeds(args, adapter, BASE_DIR, universe_symbols)
                check_and_fetch_strategy_data(args, adapter, BASE_DIR, universe_symbols)
                update_instrument_definitions(adapter, BASE_DIR, universe_symbols)
                run_backtest(args, adapter, BASE_DIR)
        else:
            # 传统模式（无 TUI）
            prepare_data_feeds(args, adapter, BASE_DIR, universe_symbols)
            check_and_fetch_strategy_data(args, adapter, BASE_DIR, universe_symbols)
            update_instrument_definitions(adapter, BASE_DIR, universe_symbols)
            run_backtest(args, adapter, BASE_DIR)
    elif args.command == "sandbox":
        run_sandbox(args, getattr(args, "env", None))
    elif args.command == "live":
        run_live(args, getattr(args, "env", None))


if __name__ == "__main__":
    main()
