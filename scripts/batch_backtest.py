"""
批量回测工具 - 一键运行多个币种的资金费率套利回测

用法:
    uv run python scripts/batch_backtest.py --symbols BTCUSDT SOLUSDT BNBUSDT --year 2024
    uv run python scripts/batch_backtest.py --symbols ETHUSDT --start-date 2024-01-01 --end-date 2024-12-31
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="批量回测工具")

    parser.add_argument(
        "--symbols",
        nargs="+",
        required=True,
        help="交易对列表 (如: BTCUSDT ETHUSDT SOLUSDT)",
    )

    parser.add_argument(
        "--year",
        type=int,
        help="年份 (如: 2024)",
    )

    parser.add_argument(
        "--start-date",
        type=str,
        help="开始日期 (格式: YYYY-MM-DD)",
    )

    parser.add_argument(
        "--end-date",
        type=str,
        help="结束日期 (格式: YYYY-MM-DD)",
    )

    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="跳过数据下载（假设数据已存在）",
    )

    parser.add_argument(
        "--output",
        type=str,
        default="output/backtest/comparison.csv",
        help="输出对比表格路径 (默认: output/backtest/comparison.csv)",
    )

    return parser.parse_args()


def download_data(symbol: str, start_date: str, end_date: str) -> bool:
    """下载单个币对的数据"""
    print(f"\n{'=' * 60}")
    print(f"📥 下载 {symbol} 数据...")
    print(f"{'=' * 60}")

    cmd = [
        "uv",
        "run",
        "python",
        "scripts/download_full_year_data.py",
        "--symbols",
        symbol,
        "--start-date",
        start_date,
        "--end-date",
        end_date,
    ]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 下载失败: {e}")
        print(e.stderr)
        return False


def update_config_files(symbol: str):
    """更新策略和环境配置文件"""
    project_root = Path(__file__).parent.parent

    # 更新策略配置
    strategy_config_path = project_root / "config/strategies/funding_arbitrage.yaml"
    with open(strategy_config_path, "r", encoding="utf-8") as f:
        strategy_config = f.read()

    # 替换 symbols 和 instrument_id
    import re

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

    # 替换 data_feeds
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
        f"csv_file_name: {symbol}-PERP/binance-{symbol}-PERP-1h-2024-01-01_2024-12-31.csv",
        env_config,
    )
    env_config = re.sub(
        r"csv_file_name:\s*\w+USDT/[^\n]+",
        f"csv_file_name: {symbol}/binance-{symbol}-1h-2024-01-01_2024-12-31.csv",
        env_config,
    )

    with open(env_config_path, "w", encoding="utf-8") as f:
        f.write(env_config)

    print(f"✅ 配置文件已更新: {symbol}")


def run_backtest(symbol: str) -> Dict | None:
    """运行单个币对的回测"""
    print(f"\n{'=' * 60}")
    print(f"🚀 运行 {symbol} 回测...")
    print(f"{'=' * 60}")

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
        print(result.stdout)

        # 查找最新的结果文件
        project_root = Path(__file__).parent.parent
        result_dir = project_root / "output/backtest/result"
        result_files = sorted(result_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)

        if result_files:
            with open(result_files[0], "r", encoding="utf-8") as f:
                result_data = json.load(f)
                result_data["symbol"] = symbol
                return result_data

        return None

    except subprocess.CalledProcessError as e:
        print(f"❌ 回测失败: {e}")
        print(e.stderr)
        return None


def generate_comparison_table(results: List[Dict], output_path: str):
    """生成对比表格"""
    if not results:
        print("❌ 没有回测结果可供对比")
        return

    # 提取关键指标
    comparison_data = []
    for result in results:
        symbol = result.get("symbol", "Unknown")
        performance = result.get("performance", {})

        comparison_data.append(
            {
                "币种": symbol,
                "初始资金 (USDT)": 100000.0,
                "引擎 PnL (USDT)": round(performance.get("engine_pnl", 0), 2),
                "资金费率收益 (USDT)": round(performance.get("funding_collected", 0), 2),
                "真实 PnL (USDT)": round(performance.get("real_pnl", 0), 2),
                "收益率 (%)": round(performance.get("real_return_pct", 0), 2),
                "订单数": performance.get("total_orders", 0),
                "持仓数": performance.get("total_positions", 0),
            }
        )

    # 创建 DataFrame
    df = pd.DataFrame(comparison_data)

    # 按收益率排序
    df = df.sort_values("收益率 (%)", ascending=False)

    # 保存到 CSV
    project_root = Path(__file__).parent.parent
    output_file = project_root / output_path
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_file, index=False, encoding="utf-8-sig")

    # 打印表格
    print(f"\n{'=' * 80}")
    print("📊 回测结果对比")
    print(f"{'=' * 80}\n")
    print(df.to_string(index=False))
    print(f"\n{'=' * 80}")
    print(f"✅ 对比表格已保存: {output_file}")
    print(f"{'=' * 80}\n")


def main():
    """主函数"""
    args = parse_args()

    # 确定日期范围
    if args.year:
        start_date = f"{args.year}-01-01"
        end_date = f"{args.year}-12-31"
    elif args.start_date and args.end_date:
        start_date = args.start_date
        end_date = args.end_date
    else:
        print("❌ 错误: 必须指定 --year 或 (--start-date 和 --end-date)")
        return 1

    print("=" * 80)
    print("🚀 批量回测工具")
    print("=" * 80)
    print(f"\n配置信息:")
    print(f"  交易对: {', '.join(args.symbols)}")
    print(f"  时间范围: {start_date} ~ {end_date}")
    print(f"  跳过下载: {args.skip_download}")
    print(f"  输出路径: {args.output}\n")

    results = []

    for symbol in args.symbols:
        print(f"\n{'#' * 80}")
        print(f"# 处理交易对: {symbol}")
        print(f"{'#' * 80}")

        # 1. 下载数据（如果需要）
        if not args.skip_download:
            if not download_data(symbol, start_date, end_date):
                print(f"⚠️ {symbol} 数据下载失败，跳过")
                continue

        # 2. 更新配置文件
        update_config_files(symbol)

        # 3. 运行回测
        result = run_backtest(symbol)
        if result:
            results.append(result)
        else:
            print(f"⚠️ {symbol} 回测失败，跳过")

    # 4. 生成对比表格
    if results:
        generate_comparison_table(results, args.output)
    else:
        print("\n❌ 所有回测都失败了，无法生成对比表格")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
