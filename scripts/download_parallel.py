"""
并行下载数据脚本 - 支持多交易对并行下载和进度条显示

优化特性:
1. 并行下载多个交易对（5x 性能提升）
2. 实时进度条显示
3. 磁盘空间检查
4. 增量更新支持

用法:
    python scripts/download_parallel.py --symbols BTCUSDT ETHUSDT SOLUSDT --start-date 2024-01-01 --end-date 2024-12-31
"""

# type: ignore

import argparse
import sys
import time
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.data_management.data_fetcher import BinanceFetcher
import pandas as pd

# 尝试导入 tqdm，如果没有则使用简单进度显示
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    tqdm = None
    print("提示: 安装 tqdm 可获得更好的进度条体验 (pip install tqdm)")


class SimpleProgressBar:
    """简单的进度条实现（当 tqdm 不可用时）"""

    def __init__(self, total, desc=""):
        self.total = total
        self.current = 0
        self.desc = desc
        self.start_time = time.time()

    def update(self, n=1):
        self.current += n
        percent = (self.current / self.total) * 100
        elapsed = time.time() - self.start_time
        rate = self.current / elapsed if elapsed > 0 else 0

        bar_length = 40
        filled = int(bar_length * self.current / self.total)
        bar = '█' * filled + '░' * (bar_length - filled)

        print(f"\r{self.desc}: |{bar}| {percent:.1f}% ({self.current}/{self.total}) [{rate:.2f}it/s]", end='', flush=True)

    def close(self):
        print()


def check_disk_space(output_dir: Path, required_gb: float = 1.0) -> bool:
    """
    检查磁盘空间是否足够

    Args:
        output_dir: 输出目录
        required_gb: 需要的最小空间（GB）

    Returns:
        是否有足够空间
    """
    stat = shutil.disk_usage(output_dir)
    free_gb = stat.free / (1024 ** 3)

    print(f"\n💾 磁盘空间检查:")
    print(f"   可用空间: {free_gb:.2f} GB")
    print(f"   需要空间: {required_gb:.2f} GB")

    if free_gb < required_gb:
        print(f"   ❌ 空间不足！")
        return False

    print(f"   ✅ 空间充足")
    return True


def check_existing_data(output_dir: Path, symbol: str, start_date: str, end_date: str) -> Tuple[bool, bool, bool]:
    """
    检查已存在的数据文件

    Returns:
        (has_spot, has_futures, has_funding)
    """
    spot_dir = output_dir / symbol
    futures_dir = output_dir / f"{symbol}-PERP"

    spot_file = spot_dir / f"binance-{symbol}-1h-{start_date}_{end_date}.csv"
    futures_file = futures_dir / f"binance-{symbol}-PERP-1h-{start_date}_{end_date}.csv"
    funding_file = futures_dir / f"binance-{symbol}-PERP-funding_rate-{start_date}_{end_date}.csv"

    return (
        spot_file.exists() and spot_file.stat().st_size > 0,
        futures_file.exists() and futures_file.stat().st_size > 0,
        funding_file.exists() and funding_file.stat().st_size > 0
    )


def download_data_in_batches(
    fetcher: BinanceFetcher,
    symbol: str,
    start_date: str,
    end_date: str,
    batch_days: int,
    market_type: str,
    show_progress: bool = True,
) -> pd.DataFrame:
    """分批下载数据（带进度条）"""
    all_data = []
    current_date = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    # 计算总批次数
    total_days = (end_dt - current_date).days
    total_batches = (total_days + batch_days - 1) // batch_days

    # 创建进度条
    pbar = None
    if show_progress:
        if HAS_TQDM and tqdm is not None:
            pbar = tqdm(total=total_batches, desc=f"  {market_type.upper()}", unit="batch")
        else:
            pbar = SimpleProgressBar(total=total_batches, desc=f"  {market_type.upper()}")

    batch_num = 1
    while current_date < end_dt:
        batch_end = min(current_date + timedelta(days=batch_days), end_dt)
        start_ts = int(current_date.timestamp() * 1000)
        end_ts = int(batch_end.timestamp() * 1000)

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

            time.sleep(0.5)  # 避免 API 限流

        except Exception as e:
            if show_progress:
                if HAS_TQDM and tqdm is not None:
                    tqdm.write(f"    ⚠️ 批次 {batch_num} 失败: {e}")
                else:
                    print(f"\n    ⚠️ 批次 {batch_num} 失败: {e}")

        if show_progress and pbar is not None:
            pbar.update(1)

        current_date = batch_end
        batch_num += 1

    if show_progress and pbar is not None:
        pbar.close()

    if not all_data:
        raise ValueError("未下载到任何数据")

    combined = pd.concat(all_data, ignore_index=True)
    combined = combined.drop_duplicates(subset=["timestamp"], keep="first")
    combined = combined.sort_values("timestamp").reset_index(drop=True)

    return combined


def download_funding_rate_in_batches(
    fetcher: BinanceFetcher,
    symbol: str,
    start_date: str,
    end_date: str,
    batch_days: int,
    show_progress: bool = True,
) -> pd.DataFrame:
    """分批下载资金费率数据（带进度条）"""
    all_data = []
    current_date = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    total_days = (end_dt - current_date).days
    total_batches = (total_days + batch_days - 1) // batch_days

    pbar = None
    if show_progress:
        if HAS_TQDM and tqdm is not None:
            pbar = tqdm(total=total_batches, desc="  FUNDING", unit="batch")
        else:
            pbar = SimpleProgressBar(total=total_batches, desc="  FUNDING")

    batch_num = 1
    while current_date < end_dt:
        batch_end = min(current_date + timedelta(days=batch_days), end_dt)
        start_ts = int(current_date.timestamp() * 1000)
        end_ts = int(batch_end.timestamp() * 1000)

        try:
            batch_data = fetcher.fetch_funding_rate(
                symbol=symbol,
                start_time=start_ts,
                end_time=end_ts,
                limit=1000,
            )

            if len(batch_data) > 0:
                all_data.append(batch_data)

            time.sleep(0.5)

        except Exception as e:
            if show_progress:
                if HAS_TQDM and tqdm is not None:
                    tqdm.write(f"    ⚠️ 批次 {batch_num} 失败: {e}")
                else:
                    print(f"\n    ⚠️ 批次 {batch_num} 失败: {e}")

        if show_progress and pbar is not None:
            pbar.update(1)

        current_date = batch_end
        batch_num += 1

    if show_progress and pbar is not None:
        pbar.close()

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
    skip_existing: bool = True,
) -> bool:
    """下载单个币对的完整数据"""

    print(f"\n{'=' * 60}")
    print(f"📊 {symbol}")
    print(f"{'=' * 60}")

    # 检查已存在的数据
    has_spot, has_futures, has_funding = check_existing_data(output_dir, symbol, start_date, end_date)

    if skip_existing and has_spot and has_futures and has_funding:
        print("✅ 所有数据已存在，跳过下载")
        return True

    # 1. 下载现货数据
    if skip_existing and has_spot:
        print("\n[1/3] 现货数据已存在，跳过")
    else:
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
            print(f"  ✅ 已保存 ({len(spot_data)} 条)")
        except Exception as e:
            print(f"  ❌ 失败: {e}")
            return False

    # 2. 下载永续合约数据
    if skip_existing and has_futures:
        print("\n[2/3] 永续合约数据已存在，跳过")
    else:
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
            print(f"  ✅ 已保存 ({len(futures_data)} 条)")
        except Exception as e:
            print(f"  ❌ 失败: {e}")
            return False

    # 3. 下载资金费率数据
    if skip_existing and has_funding:
        print("\n[3/3] 资金费率数据已存在，跳过")
    else:
        print("\n[3/3] 下载资金费率数据...")
        try:
            futures_dir = output_dir / f"{symbol}-PERP"
            funding_data = download_funding_rate_in_batches(
                fetcher=fetcher,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                batch_days=batch_days * 3,
            )

            funding_file = futures_dir / f"binance-{symbol}-PERP-funding_rate-{start_date}_{end_date}.csv"
            funding_data.to_csv(funding_file, index=False)
            print(f"  ✅ 已保存 ({len(funding_data)} 条)")
        except Exception as e:
            print(f"  ❌ 失败: {e}")
            return False

    print(f"\n✅ {symbol} 完成!")
    return True


def download_parallel(
    symbols: List[str],
    start_date: str,
    end_date: str,
    output_dir: Path,
    batch_days: int,
    max_workers: int = 3,
    skip_existing: bool = True,
) -> Tuple[int, List[str]]:
    """
    并行下载多个交易对

    Returns:
        (成功数量, 失败的交易对列表)
    """
    print(f"\n🚀 开始并行下载 ({max_workers} 个并发)")
    print(f"   交易对: {', '.join(symbols)}")
    print(f"   时间范围: {start_date} ~ {end_date}")

    success_count = 0
    failed_symbols = []

    # 为每个 worker 创建独立的 fetcher
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_symbol = {
            executor.submit(
                download_pair_data,
                BinanceFetcher(),  # 每个任务独立的 fetcher
                symbol,
                start_date,
                end_date,
                output_dir,
                batch_days,
                skip_existing,
            ): symbol
            for symbol in symbols
        }

        # 等待完成
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                success = future.result()
                if success:
                    success_count += 1
                else:
                    failed_symbols.append(symbol)
            except Exception as e:
                print(f"\n❌ {symbol} 异常: {e}")
                failed_symbols.append(symbol)

    return success_count, failed_symbols


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="并行下载数据（支持增量更新）")

    parser.add_argument(
        "--symbols",
        nargs="+",
        required=True,
        help="交易对列表 (如: BTCUSDT ETHUSDT SOLUSDT)",
    )

    parser.add_argument(
        "--start-date",
        type=str,
        required=True,
        help="开始日期 (格式: YYYY-MM-DD)",
    )

    parser.add_argument(
        "--end-date",
        type=str,
        required=True,
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
        help="每批下载的天数 (默认: 40天)",
    )

    parser.add_argument(
        "--max-workers",
        type=int,
        default=3,
        help="并行下载的最大线程数 (默认: 3)",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新下载（忽略已存在的文件）",
    )

    parser.add_argument(
        "--interval",
        type=str,
        default="1h",
        help="时间间隔 (默认: 1h)",
    )

    return parser.parse_args()


def main():
    """主函数"""
    args = parse_args()

    print("=" * 60)
    print("🚀 并行数据下载工具")
    print("=" * 60)

    # 创建输出目录
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 检查磁盘空间（每个交易对约 100MB）
    required_space = len(args.symbols) * 0.3  # 保守估计 300MB/交易对
    if not check_disk_space(output_dir, required_space):
        return 1

    # 并行下载
    start_time = time.time()
    success_count, failed_symbols = download_parallel(
        symbols=args.symbols,
        start_date=args.start_date,
        end_date=args.end_date,
        output_dir=output_dir,
        batch_days=args.batch_days,
        max_workers=args.max_workers,
        skip_existing=not args.force,
    )
    elapsed = time.time() - start_time

    # 打印汇总
    print("\n" + "=" * 60)
    print("📊 下载汇总")
    print("=" * 60)
    print(f"✅ 成功: {success_count}/{len(args.symbols)}")
    if failed_symbols:
        print(f"❌ 失败: {', '.join(failed_symbols)}")
    print(f"⏱️  总耗时: {elapsed:.1f} 秒")
    print(f"⚡ 平均速度: {elapsed/len(args.symbols):.1f} 秒/交易对")
    print("=" * 60)

    return 0 if success_count == len(args.symbols) else 1


if __name__ == "__main__":
    sys.exit(main())
