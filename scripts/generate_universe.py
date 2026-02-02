"""
动态交易池生成器 (Universe Generator)

功能说明:
    基于历史成交额动态生成加密货币交易池，用于量化策略的币种筛选。
    支持月度、周度、双周等多种更新频率。

核心特性:
    1. 避免未来函数: T 期数据生成 T+1 期交易池，无前视偏差
    2. 数据质量控制: 剔除稳定币，过滤数据不完整的新币
    3. 多层级配置: 同时生成 Top 1/5/10/25/50/100 等多个规模的交易池
    4. 灵活频率: 支持月度(M)、周度(W-MON)、双周(2W-MON)更新

使用方法:
    1. 配置参数: 修改 REBALANCE_FREQ、MIN_COUNT_RATIO、TOP_Ns 等常量
    2. 运行脚本: python generate_universe.py
    3. 输出文件: data/universe_{N}_{FREQ}.json

输出格式:
    {
        "2026-01": ["BTC", "ETH", "SOL", ...],
        "2026-02": ["BTC", "ETH", "BNB", ...],
        ...
    }

注意事项:
    - 确保 data/top/ 目录下有完整的日线数据 (*_1d.csv)
    - T 月数据决定 T+1 月交易池，回测时需对应使用
    - 最后一个周期不会生成交易池（无 T+1 期）
"""
import calendar
import json
import sys
from pathlib import Path

import pandas as pd
from tqdm import tqdm

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

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
    "FDUSD",
    "PYUSD",
    "USDD",
]
MIN_COUNT_RATIO = 0.9  # 数据完整度阈值
TOP_Ns = [1, 5, 10, 25, 50, 100]  # 选取前 N 个币种

# 更新频率配置：支持 "ME"(月度), "W-MON"(周度), "2W-MON"(双周)
REBALANCE_FREQ = "ME"


def validate_config():
    """
    验证配置参数的有效性
    """
    # 验证 MIN_COUNT_RATIO
    if not 0 < MIN_COUNT_RATIO <= 1:
        raise ValueError(f"MIN_COUNT_RATIO 必须在 (0, 1] 范围内，当前值: {MIN_COUNT_RATIO}")

    # 验证 TOP_Ns
    if not TOP_Ns:
        raise ValueError("TOP_Ns 不能为空")
    for n in TOP_Ns:
        if not isinstance(n, int) or n <= 0:
            raise ValueError(f"TOP_Ns 必须包含正整数，发现无效值: {n}")

    # 验证 REBALANCE_FREQ
    valid_freqs = ["ME", "W-MON", "2W-MON"]
    if REBALANCE_FREQ not in valid_freqs:
        raise ValueError(f"REBALANCE_FREQ 必须是 {valid_freqs} 之一，当前值: {REBALANCE_FREQ}")


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


def get_expected_days(freq: str, period_start: pd.Timestamp) -> int:
    """
    根据频率获取期望的数据天数
    """
    if freq == "ME":
        return get_days_in_month(period_start.year, period_start.month)
    elif freq == "W-MON":
        return 7
    elif freq == "2W-MON":
        return 14
    else:
        raise ValueError(f"不支持的频率: {freq}")


def generate_universe():
    """
    从 CSV 数据中动态生成交易池，支持月度/周度/双周更新
    """
    # 验证配置参数
    validate_config()

    if not DATA_DIR.exists():
        print(f"[!] Data directory not found: {DATA_DIR}")
        return {}

    all_files = list(DATA_DIR.glob("*_1d.csv"))
    if not all_files:
        print(f"[!] No CSV files found in {DATA_DIR}")
        return {}

    # 用于存储所有币种的周期统计信息
    # 结构: { PeriodString: [(symbol, mean_turnover), ...] }
    period_stats = {}

    print(f"[*] Found {len(all_files)} files. Starting data processing...")
    print(f"[*] Rebalance frequency: {REBALANCE_FREQ}")

    for file_path in tqdm(all_files, desc="Reading CSVs"):
        # 解析文件名：期望格式为 SYMBOL_1d.csv
        filename = file_path.stem  # 去除 .csv 后缀
        if "_" not in filename:
            continue
        symbol = filename.split("_")[0]

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

            # 按配置频率分组
            df.set_index("datetime", inplace=True)
            period_resample = df.resample(REBALANCE_FREQ)

            for period_start, group in period_resample:
                if group.empty:
                    continue

                # 根据频率生成时间字符串
                if REBALANCE_FREQ == "ME":
                    period_str = period_start.strftime("%Y-%m")
                elif REBALANCE_FREQ == "W-MON":
                    period_str = period_start.strftime("%Y-W%W")
                elif REBALANCE_FREQ == "2W-MON":
                    # 双周使用周数除以2来区分
                    week_num = int(period_start.strftime("%W"))
                    period_str = f"{period_start.year}-2W{week_num//2:02d}"
                else:
                    period_str = period_start.strftime("%Y-%m-%d")

                expected_days = get_expected_days(REBALANCE_FREQ, period_start)

                # 2. 处理新币入场：检查数据行数是否达标
                if len(group) < expected_days * MIN_COUNT_RATIO:
                    continue

                avg_turnover = group["turnover"].mean()

                if period_str not in period_stats:
                    period_stats[period_str] = []

                period_stats[period_str].append((symbol, avg_turnover))

            # 显式删除 DataFrame 释放内存
            del df

        except FileNotFoundError:
            print(f"\n[!] File not found: {symbol}")
            continue
        except pd.errors.EmptyDataError:
            print(f"\n[!] Empty or invalid CSV: {symbol}")
            continue
        except KeyError as e:
            print(f"\n[!] Missing required column in {symbol}: {e}")
            continue
        except ValueError as e:
            print(f"\n[!] Data conversion error in {symbol}: {e}")
            continue
        except Exception as e:
            print(f"\n[!] Unexpected error processing {symbol}: {e}")
            continue

    # 3. 排序并生成结果
    # 注意：T 期的成交量排名决定 T+1 期的 Universe
    # 重要：最后一个周期不会生成 universe（因为没有 T+1 期数据）
    # 实盘使用时，需要确保有上个周期的完整数据才能生成本周期的交易池

    sorted_periods = sorted(period_stats.keys())
    universes = {n: {} for n in TOP_Ns}

    for i in range(len(sorted_periods) - 1):
        current_period = sorted_periods[i]
        next_period = sorted_periods[i + 1]

        # 获取当前期的所有币种，按成交额降序排列
        candidates = period_stats[current_period]
        candidates.sort(key=lambda x: x[1], reverse=True)

        # 选取不同数量的 Top N
        for n in TOP_Ns:
            top_n_symbols = [c[0] for c in candidates[:n]]
            universes[n][next_period] = top_n_symbols

    return universes


if __name__ == "__main__":
    universes = generate_universe()

    if universes:
        for n, universe in universes.items():
            if not universe:
                continue

            print(f"\n[*] Sample Universe Top {n} (Latest Period):")
            last_period = sorted(universe.keys())[-1]
            print(f"Period: {last_period}")
            sample_size = min(10, len(universe[last_period]))
            print(
                f"Symbols ({len(universe[last_period])}): {universe[last_period][:sample_size]} ..."
            )

            # 保存为 JSON，文件名包含频率信息
            freq_suffix = REBALANCE_FREQ.replace("/", "")
            output_path = DATA_DIR.parent / f"universe_{n}_{freq_suffix}.json"
            with open(output_path, "w") as f:
                json.dump(universe, f, indent=4)
            print(f"[√] Universe Top {n} saved to: {output_path}")
    else:
        print("[!] No universes generated. Check if data exists in data/top/")
