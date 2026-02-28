"""
下载资金费率套利策略所需的数据

用法:
    uv run python scripts/download_arbitrage_data.py --symbols BTCUSDT ETHUSDT SOLUSDT DOGEUSDT
    uv run python scripts/download_arbitrage_data.py --start-date 2024-01-01 --end-date 2024-12-31
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path


# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.data_management.data_fetcher import BinanceFetcher


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="下载资金费率套利策略所需的数据")

    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT"],
        help="交易对列表 (默认: BTCUSDT ETHUSDT SOLUSDT DOGEUSDT)",
    )

    parser.add_argument(
        "--start-date",
        type=str,
        default="2024-01-01",
        help="开始日期 (格式: YYYY-MM-DD, 默认: 2024-01-01)",
    )

    parser.add_argument(
        "--end-date",
        type=str,
        default="2024-12-31",
        help="结束日期 (格式: YYYY-MM-DD, 默认: 2024-12-31)",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/raw",
        help="输出目录 (默认: data/raw)",
    )

    return parser.parse_args()


def date_to_timestamp_ms(date_str: str) -> int:
    """将日期字符串转换为毫秒时间戳"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return int(dt.timestamp() * 1000)


def download_pair_data(
    fetcher: BinanceFetcher,
    symbol: str,
    start_time: int,
    end_time: int,
    start_date: str,
    end_date: str,
    output_dir: Path,
):
    """
    下载单个币对的现货、合约和资金费率数据

    Args:
        fetcher: BinanceFetcher 实例
        symbol: 交易对 (如 BTCUSDT)
        start_time: 开始时间戳(毫秒)
        end_time: 结束时间戳(毫秒)
        start_date: 开始日期字符串 (用于文件名)
        end_date: 结束日期字符串 (用于文件名)
        output_dir: 输出目录
    """
    print(f"\n{'=' * 60}")
    print(f"📊 处理交易对: {symbol}")
    print(f"{'=' * 60}")

    # 1. 下载现货数据
    print("\n[1/3] 下载现货数据...")
    try:
        spot_data = fetcher.fetch_ohlcv(
            symbol=symbol,
            timeframe="1h",
            start_time=start_time,
            end_time=end_time,
            market_type="spot",
        )

        spot_dir = output_dir / symbol
        spot_dir.mkdir(parents=True, exist_ok=True)
        spot_file = spot_dir / f"binance-{symbol}-1h-{start_date}_{end_date}.csv"

        spot_data.to_csv(spot_file, index=False)
        print(f"✅ 现货数据已保存: {spot_file}")
        print(f"   数据行数: {len(spot_data)}")
        print(f"   时间范围: {spot_data['timestamp'].min()} ~ {spot_data['timestamp'].max()}")
    except Exception as e:
        print(f"❌ 现货数据下载失败: {e}")
        return False

    # 2. 下载永续合约数据
    print("\n[2/3] 下载永续合约数据...")
    try:
        futures_data = fetcher.fetch_ohlcv(
            symbol=symbol,
            timeframe="1h",
            start_time=start_time,
            end_time=end_time,
            market_type="futures",
        )

        futures_dir = output_dir / f"{symbol}-PERP"
        futures_dir.mkdir(parents=True, exist_ok=True)
        futures_file = futures_dir / f"binance-{symbol}-PERP-1h-{start_date}_{end_date}.csv"

        futures_data.to_csv(futures_file, index=False)
        print(f"✅ 永续合约数据已保存: {futures_file}")
        print(f"   数据行数: {len(futures_data)}")
        print(f"   时间范围: {futures_data['timestamp'].min()} ~ {futures_data['timestamp'].max()}")
    except Exception as e:
        print(f"❌ 永续合约数据下载失败: {e}")
        return False

    # 3. 下载资金费率数据
    print("\n[3/3] 下载资金费率数据...")
    try:
        funding_data = fetcher.fetch_funding_rate(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
        )

        funding_file = (
            futures_dir / f"binance-{symbol}-PERP-funding_rate-{start_date}_{end_date}.csv"
        )

        funding_data.to_csv(funding_file, index=False)
        print(f"✅ 资金费率数据已保存: {funding_file}")
        print(f"   数据行数: {len(funding_data)}")
        print(f"   时间范围: {funding_data['timestamp'].min()} ~ {funding_data['timestamp'].max()}")

        # 显示资金费率统计
        print("\n📈 资金费率统计:")
        print(f"   平均年化: {funding_data['funding_rate_annual'].mean():.2f}%")
        print(f"   最大年化: {funding_data['funding_rate_annual'].max():.2f}%")
        print(f"   最小年化: {funding_data['funding_rate_annual'].min():.2f}%")
    except Exception as e:
        print(f"❌ 资金费率数据下载失败: {e}")
        return False

    print(f"\n✅ {symbol} 所有数据下载完成!")
    return True


def main():
    """主函数"""
    args = parse_args()

    print("=" * 60)
    print("🚀 资金费率套利数据下载工具")
    print("=" * 60)
    print("\n配置信息:")
    print(f"  交易对: {', '.join(args.symbols)}")
    print(f"  时间范围: {args.start_date} ~ {args.end_date}")
    print(f"  输出目录: {args.output_dir}")

    # 转换日期为时间戳
    start_time = date_to_timestamp_ms(args.start_date)
    end_time = date_to_timestamp_ms(args.end_date)

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
            start_time=start_time,
            end_time=end_time,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=output_dir,
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

    # 返回退出码
    return 0 if success_count == len(args.symbols) else 1


if __name__ == "__main__":
    sys.exit(main())
