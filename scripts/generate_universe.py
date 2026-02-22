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
import logging
import sys
from pathlib import Path
from typing import List, Optional

import pandas as pd
from tqdm import tqdm

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

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
MIN_COUNT_RATIO = 1.0  # 数据完整度阈值
TOP_Ns = [15, 100]  # 选取前 N 个币种

# 更新频率配置：支持 "ME"(月度), "W-MON"(周度), "2W-MON"(双周)
REBALANCE_FREQ = "W-MON"


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


def _validate_data_directory() -> Optional[List[Path]]:
    """验证数据目录并返回CSV文件列表"""
    if not DATA_DIR.exists():
        logger.error(f"Data directory not found: {DATA_DIR}")
        return None

    all_files = list(DATA_DIR.glob("*_1d.csv"))
    if not all_files:
        logger.error(f"No CSV files found in {DATA_DIR}")
        return None

    return all_files


def _parse_symbol_from_filename(file_path: Path) -> Optional[str]:
    """从文件名解析symbol"""
    filename = file_path.stem
    if "_" not in filename:
        return None

    symbol = filename.split("_")[0]
    if is_stablecoin(symbol):
        return None

    return symbol


def _load_and_prepare_data(file_path: Path) -> Optional[pd.DataFrame]:
    """加载并准备数据"""
    try:
        df = pd.read_csv(file_path, usecols=["timestamp", "close", "volume"])
        if df.empty:
            return None

        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
        df["turnover"] = df["close"] * df["volume"]
        df.set_index("datetime", inplace=True)

        return df
    except (FileNotFoundError, pd.errors.EmptyDataError, KeyError, ValueError) as e:
        symbol = file_path.stem.split("_")[0]
        logger.warning(f"Error processing {symbol}: {e}")
        return None
    except Exception as e:
        symbol = file_path.stem.split("_")[0]
        logger.error(f"Unexpected error processing {symbol}: {e}")
        return None


def _generate_period_string(period_start, rebalance_freq: str) -> str:
    """生成周期字符串"""
    if rebalance_freq == "ME":
        return period_start.strftime("%Y-%m")
    elif rebalance_freq == "W-MON":
        return period_start.strftime("%Y-W%W")
    elif rebalance_freq == "2W-MON":
        week_num = int(period_start.strftime("%W"))
        return f"{period_start.year}-2W{week_num//2:02d}"
    else:
        return period_start.strftime("%Y-%m-%d")


def _process_period_group(group: pd.DataFrame, period_start, symbol: str) -> Optional[tuple[str, str, float]]:
    """处理单个周期的数据组"""
    if group.empty:
        return None

    period_str = _generate_period_string(period_start, REBALANCE_FREQ)
    expected_days = get_expected_days(REBALANCE_FREQ, period_start)

    if len(group) < expected_days * MIN_COUNT_RATIO:
        return None

    avg_turnover = group["turnover"].mean()
    return (period_str, symbol, avg_turnover)


def _collect_period_stats(all_files: List[Path]) -> dict:
    """收集所有周期的统计数据"""
    period_stats = {}

    logger.info(f"Found {len(all_files)} files. Starting data processing...")
    logger.info(f"Rebalance frequency: {REBALANCE_FREQ}")

    for file_path in tqdm(all_files, desc="Reading CSVs"):
        symbol = _parse_symbol_from_filename(file_path)
        if not symbol:
            continue

        df = _load_and_prepare_data(file_path)
        if df is None:
            continue

        period_resample = df.resample(REBALANCE_FREQ)

        for period_start, group in period_resample:
            result = _process_period_group(group, period_start, symbol)
            if result:
                period_str, sym, avg_turnover = result
                if period_str not in period_stats:
                    period_stats[period_str] = []
                period_stats[period_str].append((sym, avg_turnover))

        del df

    return period_stats


def _build_universes(period_stats: dict) -> dict:
    """构建universe字典"""
    sorted_periods = sorted(period_stats.keys())
    universes = {n: {} for n in TOP_Ns}

    for i in range(len(sorted_periods) - 1):
        current_period = sorted_periods[i]
        next_period = sorted_periods[i + 1]

        candidates = period_stats[current_period]
        candidates.sort(key=lambda x: x[1], reverse=True)

        for n in TOP_Ns:
            top_n_symbols = [c[0] for c in candidates[:n]]
            universes[n][next_period] = top_n_symbols

    return universes


def generate_universe():
    """
    从 CSV 数据中动态生成交易池，支持月度/周度/双周更新
    """
    validate_config()

    all_files = _validate_data_directory()
    if not all_files:
        return {}

    period_stats = _collect_period_stats(all_files)
    return _build_universes(period_stats)



if __name__ == "__main__":
    universes = generate_universe()

    if universes:
        for n, universe in universes.items():
            if not universe:
                continue

            logger.info(f"\nSample Universe Top {n} (Latest Period):")
            last_period = sorted(universe.keys())[-1]
            logger.info(f"Period: {last_period}")
            sample_size = min(10, len(universe[last_period]))
            logger.info(
                f"Symbols ({len(universe[last_period])}): {universe[last_period][:sample_size]} ..."
            )

            # 保存为 JSON，文件名包含频率信息
            freq_suffix = REBALANCE_FREQ.replace("/", "")
            output_path = DATA_DIR.parent / "universe" / f"universe_{n}_{freq_suffix}.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(universe, f, indent=4)
            logger.info(f"Universe Top {n} saved to: {output_path}")
    else:
        logger.warning("No universes generated. Check if data exists in data/top/")
