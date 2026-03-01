#!/usr/bin/env python3
"""
资金费率套利策略 - 一键分析工具

功能:
1. 自动下载指定币种的历史数据
2. 依次运行每个币种的回测
3. 生成完整的对比分析报告

用法:
    # 使用默认币种 (BTC, ETH, SOL, BNB)
    uv run python scripts/run_funding_arbitrage_analysis.py

    # 指定币种
    uv run python scripts/run_funding_arbitrage_analysis.py --symbols BTCUSDT ETHUSDT SOLUSDT

    # 跳过数据下载（假设数据已存在）
    uv run python scripts/run_funding_arbitrage_analysis.py --skip-download

    # 指定年份
    uv run python scripts/run_funding_arbitrage_analysis.py --year 2024
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="资金费率套利策略 - 一键分析工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        help="交易对列表 (默认: BTCUSDT ETHUSDT SOLUSDT BNBUSDT)",
    )

    parser.add_argument(
        "--year",
        type=int,
        default=2024,
        help="年份 (默认: 2024)",
    )

    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="跳过数据下载（假设数据已存在）",
    )

    return parser.parse_args()


def print_header(title: str):
    """打印标题"""
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}\n")


def download_data(symbol: str, year: int) -> bool:
    """下载数据"""
    print_header(f"📥 下载 {symbol} 数据")

    cmd = [
        "uv",
        "run",
        "python",
        "scripts/download_full_year_data.py",
        "--symbols",
        symbol,
        "--year",
        str(year),
    ]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 下载失败: {e}")
        print(e.stderr)
        return False


def update_config(symbol: str, year: int):
    """更新配置文件"""
    import re

    project_root = Path(__file__).parent.parent
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"

    # 更新策略配置
    strategy_config_path = project_root / "config/strategies/funding_arbitrage.yaml"
    with open(strategy_config_path, "r", encoding="utf-8") as f:
        strategy_config = f.read()

    strategy_config = re.sub(
        r"symbols:\s*\n\s*-\s*\w+USDT",
        f"symbols:\n    - {symbol}",
        strategy_config,
    )
    strategy_config = re.sub(
        r"instrument_id:\s*\w+USDT-PERP\.BINANCE",
        f"instrument_id: {symbol}-PERP.BINANCE",
        strategy_config,
    )
    strategy_config = re.sub(
        r"bar_type:\s*\w+USDT-PERP\.BINANCE-1-HOUR-LAST-EXTERNAL",
        f"bar_type: {symbol}-PERP.BINANCE-1-HOUR-LAST-EXTERNAL",
        strategy_config,
    )

    with open(strategy_config_path, "w", encoding="utf-8") as f:
        f.write(strategy_config)

    # 更新环境配置
    env_config_path = project_root / "config/environments/funding_test.yaml"
    with open(env_config_path, "r", encoding="utf-8") as f:
        env_config = f.read()

    env_config = re.sub(
        r"instrument_id:\s*\w+USDT-PERP\.BINANCE",
        f"instrument_id: {symbol}-PERP.BINANCE",
        env_config,
    )
    env_config = re.sub(
        r"instrument_id:\s*\w+USDT\.BINANCE",
        f"instrument_id: {symbol}.BINANCE",
        env_config,
    )
    env_config = re.sub(
        r"csv_file_name:\s*\w+USDT-PERP/[^\n]+",
        f"csv_file_name: {symbol}-PERP/binance-{symbol}-PERP-1h-{start_date}_{end_date}.csv",
        env_config,
    )
    env_config = re.sub(
        r"csv_file_name:\s*\w+USDT/[^\n]+",
        f"csv_file_name: {symbol}/binance-{symbol}-1h-{start_date}_{end_date}.csv",
        env_config,
    )

    with open(env_config_path, "w", encoding="utf-8") as f:
        f.write(env_config)


def run_backtest(symbol: str) -> bool:
    """运行回测"""
    print_header(f"🚀 运行 {symbol} 回测")

    cmd = [
        "uv",
        "run",
        "python",
        "main.py",
        "backtest",
        "--type",
        "low",
        "--env",
        "funding_test",
    ]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        # 只打印关键信息
        lines = result.stdout.split("\n")
        for line in lines:
            if any(
                keyword in line
                for keyword in [
                    "Real PnL",
                    "Funding Collected",
                    "Engine PnL",
                    "Initial Capital",
                    "📊 Backtest Results Summary",
                    "=" * 60,
                ]
            ):
                print(line)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 回测失败: {e}")
        return False


def generate_report():
    """生成分析报告"""
    print_header("📊 生成分析报告")

    cmd = ["uv", "run", "python", "scripts/generate_comparison.py"]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 报告生成失败: {e}")
        print(e.stderr)
        return False


def main():
    """主函数"""
    args = parse_args()

    print_header("🎯 资金费率套利策略 - 一键分析工具")
    print(f"配置信息:")
    print(f"  • 交易对: {', '.join(args.symbols)}")
    print(f"  • 年份: {args.year}")
    print(f"  • 跳过下载: {args.skip_download}")
    print()

    start_time = time.time()
    success_count = 0
    failed_symbols = []

    for i, symbol in enumerate(args.symbols, 1):
        print(f"\n{'#' * 80}")
        print(f"# [{i}/{len(args.symbols)}] 处理 {symbol}")
        print(f"{'#' * 80}")

        # 1. 下载数据
        if not args.skip_download:
            if not download_data(symbol, args.year):
                print(f"⚠️ {symbol} 数据下载失败，跳过")
                failed_symbols.append(symbol)
                continue

        # 2. 更新配置
        update_config(symbol, args.year)
        print(f"✅ 配置已更新: {symbol}")

        # 3. 运行回测
        if run_backtest(symbol):
            success_count += 1
        else:
            failed_symbols.append(symbol)

        # 短暂延迟，避免过快
        if i < len(args.symbols):
            time.sleep(1)

    # 4. 生成报告
    if success_count > 0:
        generate_report()

    # 5. 打印总结
    elapsed_time = time.time() - start_time
    print_header("✅ 分析完成")
    print(f"总耗时: {elapsed_time:.1f} 秒")
    print(f"成功: {success_count}/{len(args.symbols)}")
    if failed_symbols:
        print(f"失败: {', '.join(failed_symbols)}")
    print()

    return 0 if success_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
