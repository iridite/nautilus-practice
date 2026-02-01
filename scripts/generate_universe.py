import calendar
import json

import pandas as pd
from tqdm import tqdm

# 使用统一的工具函数
from utils import get_project_root

# 配置常量
DATA_DIR = get_project_root() / "data" / "top"
STABLECOINS = [
    "USDT",
    "USDC",
    "BUSD",
    "DAI",
    "TUSD",
    "UST",
    "EURS",
    "EUR",
    "GBP",
    "KNC",
]
MIN_COUNT_RATIO = 0.9  # 当月数据完整度阈值
TOP_Ns = [1, 5, 10, 25, 50, 100]  # 选取前 N 个币种


def is_stablecoin(symbol: str) -> bool:
    """
    判断是否为稳定币
    """
    # 币安交易对通常是 BASE + QUOTE (如 BTCUSDT)
    # 剔除以稳定币为 Base 的交易对，例如 USDCUSDT
    for stable in STABLECOINS:
        if symbol.startswith(stable):
            return True
    return False


def get_days_in_month(year: int, month: int) -> int:
    """
    获取指定月份的天数
    """
    return calendar.monthrange(year, month)[1]


def generate_universe():
    """
    从 CSV 数据中动态生成每月成交额 Top 50 交易池
    """
    if not DATA_DIR.exists():
        print(f"[!] Data directory not found: {DATA_DIR}")
        return {}

    all_files = list(DATA_DIR.glob("*_1d.csv"))
    if not all_files:
        print(f"[!] No CSV files found in {DATA_DIR}")
        return {}

    # 用于存储所有币种的月度统计信息
    # 结构: { MonthString: [(symbol, mean_turnover, count), ...] }
    monthly_stats = {}

    print(f"[*] Found {len(all_files)} files. Starting data processing...")

    for file_path in tqdm(all_files, desc="Reading CSVs"):
        symbol = file_path.name.split("_")[0]

        # 1. 剔除稳定币
        if is_stablecoin(symbol):
            continue

        try:
            # 高效读取：仅读取必要列
            df = pd.read_csv(file_path, usecols=["timestamp", "close", "volume"])
            if df.empty:
                continue

            # 转换时间
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
            # 计算每日成交额 (Turnover = Close * Volume)
            df["turnover"] = df["close"] * df["volume"]

            # 按月分组
            df.set_index("datetime", inplace=True)
            monthly_resample = df.resample("MS")

            for month_start, group in monthly_resample:
                if group.empty:
                    continue

                month_str = month_start.strftime("%Y-%m")
                days_in_month = get_days_in_month(month_start.year, month_start.month)

                # 2. 处理新币入场：检查数据行数是否达标
                if len(group) < days_in_month * MIN_COUNT_RATIO:
                    continue

                avg_turnover = group["turnover"].mean()

                if month_str not in monthly_stats:
                    monthly_stats[month_str] = []

                monthly_stats[month_str].append((symbol, avg_turnover))

        except Exception as e:
            print(f"\n[!] Error processing {symbol}: {e}")
            continue

    # 3. 排序并生成结果
    # 注意：T 月的成交量排名决定 T+1 月的 Universe

    sorted_months = sorted(monthly_stats.keys())
    universes = {n: {} for n in TOP_Ns}

    for i in range(len(sorted_months) - 1):
        current_month = sorted_months[i]
        next_month = sorted_months[i + 1]

        # 获取当前月的所有币种，按成交额降序排列
        candidates = monthly_stats[current_month]
        candidates.sort(key=lambda x: x[1], reverse=True)

        # 选取不同数量的 Top N
        for n in TOP_Ns:
            top_n_symbols = [c[0] for c in candidates[:n]]
            universes[n][next_month] = top_n_symbols

    return universes


if __name__ == "__main__":
    universes = generate_universe()

    if universes:
        for n, universe in universes.items():
            if not universe:
                continue

            print(f"\n[*] Sample Universe Top {n} (Latest Month):")
            last_month = sorted(universe.keys())[-1]
            print(f"Month: {last_month}")
            print(
                f"Symbols ({len(universe[last_month])}): {universe[last_month][:10]} ..."
            )

            # 保存为 JSON 方便查看或加载
            output_path = DATA_DIR.parent / f"universe_{n}.json"
            with open(output_path, "w") as f:
                json.dump(universe, f, indent=4)
            print(f"[√] Universe Top {n} saved to: {output_path}")
    else:
        print("[!] No universes generated. Check if data exists in data/top/")
