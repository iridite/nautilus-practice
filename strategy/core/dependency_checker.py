"""策略数据依赖检查模块"""

import logging
from pathlib import Path

from utils.data_file_checker import check_funding_data_exists, check_oi_data_exists

logger = logging.getLogger(__name__)


def extract_strategy_symbols(strategy_config, universe_symbols: set) -> set:
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

    strategy_symbols = extract_strategy_symbols(strategy_config, universe_symbols)
    if not strategy_symbols:
        return tasks

    logger.info(f"检查 {len(strategy_symbols)} 个符号的 {len(data_types)} 种数据类型")

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
