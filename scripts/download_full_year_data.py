"""
下载完整年度数据（自动分批处理）

用法:
    uv run python scripts/download_full_year_data.py --symbols SOLUSDT --year 2024
    uv run python scripts/download_full_year_data.py --symbols BTCUSDT ETHUSDT --start-date 2024-01-01 --end-date 2024-12-31
"""

import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.data_management.data_fetcher import BinanceFetcher
import pandas as pd


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="下载完整年度数据（自动分批处理）")

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
        "--output-dir",
        type=str,
        default="data/raw",
        help="输出目录 (默认: data/raw)",
    )

    parser.add_argument(
        "--batch-days",
        type=int,
        default=40,
        help="每批下载的天数 (默认: 40天，约960条1h数据)",
    )

    return parser.parse_args()


def date_to_timestamp_ms(date_str: str) -> int:
    """将日期字符串转换��毫秒时间戳"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return int(dt.timestamp() * 1000)


def download_data_in_batches(
    fetcher: BinanceFetcher,
    symbol: str,
    start_date: str,
    end_date: str,
    batch_days: int,
    market_type: str,
) -> pd.DataFrame:
    """
    分批下载数据（处理 Binance API 1000 条限制）

    Args:
        fetcher: BinanceFetcher 实例
        symbol: 交易对
        start_date: 开始日期
        end_date: 结束日期
        batch_days: 每批天数
        market_type: 市场类型 (spot/futures)

    Returns:
        合并后的完整数据
    """
    all_data = []
    current_date = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    batch_num = 1
    while current_date < end_dt:
        # 计算当前批次的结束时间
        batch_end = min(current_date + timedelta(days=batch_days), end_dt)

        start_ts = int(current_date.timestamp() * 1000)
        end_ts = int(batch_end.timestamp() * 1000)

        print(f"  批次 {batch_num}: {current_date.date()} ~ {batch_end.date()}", end=" ")

        try:
            batch_data = fetcher.fetch_ohlcv(
                symbol=symbol,
                timeframe="1h",
                start_time=start_ts,
                end_time=end_ts,
                limit=1000,
                market_type=market_type,
            )

            if len(batch_data) > 0:
                all_data.append(batch_data)
                print(f"✅ ({len(batch_data)} 条)")
            else:
                print("⚠️ (无数据)")

            # 避免触发 API 限流
            time.sleep(0.5)

        except Exception as e:
            print(f"❌ 失败: {e}")

        current_date = batch_end
        batch_num += 1

    if not all_data:
        raise ValueError("未下载到任何数据")

    # 合并所有批次数据
    combined = pd.concat(all_data, ignore_index=True)

    # 去重（可能有重叠）
    combined = combined.drop_duplicates(subset=["timestamp"], keep="first")

    # 按时间排序
    combined = combined.sort_values("timestamp").reset_index(drop=True)

    return combined


def download_funding_rate_in_batches(
    fetcher: BinanceFetcher,
    symbol: str,
    start_date: str,
    end_date: str,
    batch_days: int,
) -> pd.DataFrame:
    """
    分批下载资金费率数据

    Args:
        fetcher: BinanceFetcher 实例
        symbol: 交易对
        start_date: 开始日期
        end_date: 结束日期
        batch_days: 每批天数

    Returns:
        合并后的完整数据
    """
    all_data = []
    current_date = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    batch_num = 1
    while current_date < end_dt:
        batch_end = min(current_date + timedelta(days=batch_days), end_dt)

        start_ts = int(current_date.timestamp() * 1000)
        end_ts = int(batch_end.timestamp() * 1000)

        print(f"  批次 {batch_num}: {current_date.date()} ~ {batch_end.date()}", end=" ")

        try:
            batch_data = fetcher.fetch_funding_rate(
                symbol=symbol,
                start_time=start_ts,
                end_time=end_ts,
                limit=1000,
            )

            if len(batch_data) > 0:
                all_data.append(batch_data)
                print(f"✅ ({len(batch_data)} 条)")
            else:
                print("⚠️ (无数据)")

            time.sleep(0.5)

        except Exception as e:
            print(f"❌ 失败: {e}")

        current_date = batch_end
        batch_num += 1

    if not all_data:
        raise ValueError("未下载到任何资金费率数据")

    combined = pd.concat(all_data, ignore_index=True)
    combined = combined.drop_duplicates(subset=["timestamp"], keep="first")
    combined = combined.sort_values("timestamp").reset_index(drop=True)

    return combined


def download_pair_data(
    fetcher: BinanceFetcher,
    symbol: str,
    start_date: str,
    end_date: str,
    output_dir: Path,
    batch_days: int,
):
    """
    下载单个币对的完整数据

    Args:
        fetcher: BinanceFetcher 实例
        symbol: 交易对
        start_date: 开始日期
        end_date: 结束日期
        output_dir: 输出目录
        batch_days: 每批天数
    """
    print(f"\n{'=' * 60}")
    print(f"📊 处理交易对: {symbol}")
    print(f"{'=' * 60}")

    # 1. 下载现货数据
    print("\n[1/3] 下载现货数据...")
    try:
        spot_data = download_data_in_batches(
            fetcher=fetcher,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            batch_days=batch_days,
            market_type="spot",
        )

        spot_dir = output_dir / symbol
        spot_dir.mkdir(parents=True, exist_ok=True)
        spot_file = spot_dir / f"binance-{symbol}-1h-{start_date}_{end_date}.csv"

        spot_data.to_csv(spot_file, index=False)
        print(f"\n✅ 现货数据已保存: {spot_file}")
        print(f"   总数据行数: {len(spot_data)}")
        print(f"   时间范围: {spot_data['timestamp'].min()} ~ {spot_data['timestamp'].max()}")
    except Exception as e:
        print(f"\n❌ 现货数据下载失败: {e}")
        return False

    # 2. 下载永续合约数据
    print("\n[2/3] 下载永续合约数据...")
    try:
        futures_data = download_data_in_batches(
            fetcher=fetcher,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            batch_days=batch_days,
            market_type="futures",
        )

        futures_dir = output_dir / f"{symbol}-PERP"
        futures_dir.mkdir(parents=True, exist_ok=True)
        futures_file = futures_dir / f"binance-{symbol}-PERP-1h-{start_date}_{end_date}.csv"

        futures_data.to_csv(futures_file, index=False)
        print(f"\n✅ 永续合约数据已保存: {futures_file}")
        print(f"   总数据行数: {len(futures_data)}")
        print(f"   时间范围: {futures_data['timestamp'].min()} ~ {futures_data['timestamp'].max()}")
    except Exception as e:
        print(f"\n❌ 永续合约数据下载失败: {e}")
        return False

    # 3. 下载资金费率数据
    print("\n[3/3] 下载资金费率数据...")
    try:
        funding_data = download_funding_rate_in_batches(
            fetcher=fetcher,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            batch_days=batch_days * 3,  # 资金费率数据更稀疏，可以用更大的批次
        )

        funding_file = futures_dir / f"binance-{symbol}-PERP-funding_rate-{start_date}_{end_date}.csv"

        funding_data.to_csv(funding_file, index=False)
        print(f"\n✅ 资金费率数据已保存: {funding_file}")
        print(f"   总数据行数: {len(funding_data)}")
        print(f"   时间范围: {funding_data['timestamp'].min()} ~ {funding_data['timestamp'].max()}")

        # 显示资金费率统计
        print("\n📈 资金费率统计:")
        print(f"   平均年化: {funding_data['funding_rate_annual'].mean():.2f}%")
        print(f"   最大年化: {funding_data['funding_rate_annual'].max():.2f}%")
        print(f"   最小年化: {funding_data['funding_rate_annual'].min():.2f}%")
    except Exception as e:
        print(f"\n❌ 资金费率数据下载失败: {e}")
        return False

    print(f"\n✅ {symbol} 所有数据下载完成!")
    return True


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

    print("=" * 60)
    print("🚀 完整年度数据下载工具（分批处理）")
    print("=" * 60)
    print("\n配置信息:")
    print(f"  交易对: {', '.join(args.symbols)}")
    print(f"  时间范围: {start_date} ~ {end_date}")
    print(f"  输出目录: {args.output_dir}")
    print(f"  批次大小: {args.batch_days} 天")

    # 创建输出目录
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 创建 fetcher
    fetcher = BinanceFetcher()

    # 下载每个交易对的数据
    success_count = 0
    failed_symbols = []

    for symbol in args.symbols:
        success = download_pair_data(
            fetcher=fetcher,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            output_dir=output_dir,
            batch_days=args.batch_days,
        )

        if success:
            success_count += 1
        else:
            failed_symbols.append(symbol)

    # 打印汇总信息
    print("\n" + "=" * 60)
    print("📊 下载汇总")
    print("=" * 60)
    print(f"✅ 成功: {success_count}/{len(args.symbols)}")
    if failed_symbols:
        print(f"❌ 失败: {', '.join(failed_symbols)}")
    print("=" * 60)

    return 0 if success_count == len(args.symbols) else 1


if __name__ == "__main__":
    sys.exit(main())
