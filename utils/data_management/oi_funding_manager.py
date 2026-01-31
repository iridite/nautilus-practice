"""OI 和 Funding Rate 数据管理模块"""

from pathlib import Path

from .data_manager import fetch_data_with_retry


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
        files, retries, fallbacks, error = fetch_data_with_retry(
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
        files, retries, fallbacks, error = fetch_data_with_retry(
            "funding", symbols_list, exchange, start_date, end_date, "1h",
            base_dir, max_retries, supported_exchanges
        )

        results["funding_files"] += files
        results["retries"] += retries
        results["fallbacks"] += fallbacks
        if error:
            results["errors"].append(error)

    return results
