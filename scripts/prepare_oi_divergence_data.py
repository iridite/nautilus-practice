"""
OI Divergence 策略数据准备脚本

自动化下载和准备 OI Divergence 策略所需的所有数据：
1. OHLCV 数据（1H 和 4H）
2. Open Interest 数据
3. Funding Rate 数据

Usage:
    uv run python scripts/prepare_oi_divergence_data.py

    # 自定义参数：
    uv run python scripts/prepare_oi_divergence_data.py --symbols BTCUSDT ETHUSDT --start 2024-01-01 --end 2024-12-31
"""

import argparse
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.data_retrival import batch_fetch_ohlcv
from utils.oi_funding_fetcher import batch_fetch_oi_and_funding


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="准备 OI Divergence 策略所需的数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用默认参数下载 BTC 数据
  uv run python scripts/prepare_oi_divergence_data.py

  # 下载多个币种数据
  uv run python scripts/prepare_oi_divergence_data.py --symbols BTCUSDT ETHUSDT SOLUSDT

  # 指定日期范围
  uv run python scripts/prepare_oi_divergence_data.py --start 2024-01-01 --end 2024-06-30

  # 使用 OKX 交易所
  uv run python scripts/prepare_oi_divergence_data.py --exchange okx
        """,
    )

    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["BTCUSDT"],
        help="交易对列表 (默认: BTCUSDT)",
    )

    parser.add_argument(
        "--start",
        type=str,
        default="2024-01-01",
        help="开始日期 YYYY-MM-DD (默认: 2024-01-01)",
    )

    parser.add_argument(
        "--end",
        type=str,
        default="2024-12-31",
        help="结束日期 YYYY-MM-DD (默认: 2024-12-31)",
    )

    parser.add_argument(
        "--exchange",
        type=str,
        choices=["binance", "okx"],
        default="binance",
        help="交易所 (默认: binance)",
    )

    parser.add_argument(
        "--timeframes",
        nargs="+",
        default=["1h", "4h"],
        help="时间周期列表 (默认: 1h 4h)",
    )

    parser.add_argument(
        "--oi-period",
        type=str,
        default="1h",
        help="OI 数据周期 (默认: 1h)",
    )

    parser.add_argument(
        "--skip-ohlcv",
        action="store_true",
        help="跳过 OHLCV 数据下载",
    )

    parser.add_argument(
        "--skip-oi",
        action="store_true",
        help="跳过 OI 和 Funding Rate 数据下载",
    )

    return parser.parse_args()


def validate_dates(start_date: str, end_date: str) -> bool:
    """验证日期格式和合理性"""
    from datetime import datetime

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        if start >= end:
            print("❌ 错误：开始日期必须早于结束日期")
            return False

        if end > datetime.now():
            print("⚠️  警告：结束日期晚于当前日期，将使用当前日期")

        return True
    except ValueError as e:
        print(f"❌ 日期格式错误：{e}")
        print("   请使用 YYYY-MM-DD 格式")
        return False


def print_header():
    """打印脚本头部信息"""
    print("\n" + "=" * 80)
    print("🚀 OI Divergence 策略数据准备工具")
    print("=" * 80)
    print("\n此脚本将自动下载以下数据：")
    print("  1. OHLCV K线数据（多时间周期）")
    print("  2. Open Interest 持仓量数据")
    print("  3. Funding Rate 资金费率数据")
    print("\n" + "=" * 80 + "\n")


def print_summary(args, total_files: int):
    """打印下载摘要"""
    print("\n" + "=" * 80)
    print("✅ 数据准备完成！")
    print("=" * 80)
    print(f"\n📊 下载摘要:")
    print(f"  交易对数量: {len(args.symbols)}")
    print(f"  日期范围: {args.start} 至 {args.end}")
    print(f"  交易所: {args.exchange.upper()}")
    print(f"  总文件数: {total_files}")
    print(f"\n💾 数据保存位置: {PROJECT_ROOT / 'data' / 'raw'}")
    print("\n📝 下一步:")
    print("  运行回测: uv run python backtest/backtest_oi_divergence.py")
    print("\n" + "=" * 80 + "\n")


def main():
    """主函数"""
    args = parse_args()

    # 打印头部信息
    print_header()

    # 验证日期
    if not validate_dates(args.start, args.end):
        sys.exit(1)

    # 打印配置
    print("⚙️  配置参数:")
    print(f"  交易对: {', '.join(args.symbols)}")
    print(f"  日期范围: {args.start} 至 {args.end}")
    print(f"  交易所: {args.exchange.upper()}")
    print(f"  时间周期: {', '.join(args.timeframes)}")
    print(f"  OI 周期: {args.oi_period}")

    if args.skip_ohlcv:
        print("  ⏭️  跳过 OHLCV 数据下载")
    if args.skip_oi:
        print("  ⏭️  跳过 OI/Funding 数据下载")

    print()

    total_files = 0

    # === 步骤 1: 下载 OHLCV 数据 ===
    if not args.skip_ohlcv:
        print("\n" + "-" * 80)
        print("📥 步骤 1/2: 下载 OHLCV K线数据")
        print("-" * 80)

        for timeframe in args.timeframes:
            print(f"\n⏱️  正在下载 {timeframe.upper()} 周期数据...")

            try:
                configs = batch_fetch_ohlcv(
                    symbols=args.symbols,
                    start_date=args.start,
                    end_date=args.end,
                    timeframe=timeframe,
                    exchange_id=args.exchange,
                    base_dir=PROJECT_ROOT,
                )
                total_files += len(configs)
                print(f"   ✅ {timeframe.upper()} 数据下载完成 ({len(configs)} 文件)")

            except Exception as e:
                print(f"   ❌ {timeframe.upper()} 数据下载失败: {e}")
                import traceback

                traceback.print_exc()
    else:
        print("\n⏭️  跳过 OHLCV 数据下载")

    # === 步骤 2: 下载 OI 和 Funding Rate 数据 ===
    if not args.skip_oi:
        print("\n" + "-" * 80)
        print("📊 步骤 2/2: 下载 Open Interest 和 Funding Rate 数据")
        print("-" * 80)

        try:
            results = batch_fetch_oi_and_funding(
                symbols=args.symbols,
                start_date=args.start,
                end_date=args.end,
                exchange_id=args.exchange,
                base_dir=PROJECT_ROOT,
                oi_period=args.oi_period,
            )

            oi_count = len(results["oi_files"])
            funding_count = len(results["funding_files"])
            total_files += oi_count + funding_count

            print(f"\n   ✅ OI 数据: {oi_count} 文件")
            print(f"   ✅ Funding Rate 数据: {funding_count} 文件")

        except Exception as e:
            print(f"   ❌ OI/Funding 数据下载失败: {e}")
            import traceback

            traceback.print_exc()
    else:
        print("\n⏭️  跳过 OI/Funding 数据下载")

    # === 步骤 3: 验证数据完整性 ===
    print("\n" + "-" * 80)
    print("🔍 验证数据完整性")
    print("-" * 80)

    data_dir = PROJECT_ROOT / "data" / "raw"
    validation_passed = True

    for symbol in args.symbols:
        safe_symbol = symbol.replace("/", "")
        symbol_dir = data_dir / safe_symbol

        print(f"\n检查 {symbol}:")

        # 检查 OHLCV 文件
        if not args.skip_ohlcv:
            for timeframe in args.timeframes:
                ohlcv_file = (
                    symbol_dir
                    / f"{args.exchange}-{safe_symbol}-{timeframe}-{args.start}_{args.end}.csv"
                )
                if ohlcv_file.exists() and ohlcv_file.stat().st_size > 10 * 1024:
                    print(f"  ✅ OHLCV {timeframe.upper()}: {ohlcv_file.name}")
                else:
                    print(f"  ❌ OHLCV {timeframe.upper()}: 文件缺失或过小")
                    validation_passed = False

        # 检查 OI 文件
        if not args.skip_oi:
            oi_file = (
                symbol_dir
                / f"{args.exchange}-{safe_symbol}-oi-{args.oi_period}-{args.start}_{args.end}.csv"
            )
            if oi_file.exists() and oi_file.stat().st_size > 1024:
                print(f"  ✅ OI Data: {oi_file.name}")
            else:
                print(f"  ⚠️  OI Data: 文件缺失或过小 (策略可能无法正常运行)")

            # 检查 Funding Rate 文件
            funding_file = (
                symbol_dir
                / f"{args.exchange}-{safe_symbol}-funding-{args.start}_{args.end}.csv"
            )
            if funding_file.exists() and funding_file.stat().st_size > 1024:
                print(f"  ✅ Funding Rate: {funding_file.name}")
            else:
                print(f"  ⚠️  Funding Rate: 文件缺失或过小 (策略可能无法正常运行)")

    # 打印最终摘要
    print_summary(args, total_files)

    if not validation_passed:
        print("⚠️  警告：部分数据文件验证失败，请检查上述输出")
        return 1

    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断操作")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 脚本执行失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
