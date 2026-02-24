"""
Dynamic Universe Manager

动态管理交易标的池，基于历史成交量筛选活跃币种。
"""

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path


# 全局缓存函数（避免实例方法缓存导致的内存泄漏）
@lru_cache(maxsize=10000)
def _cached_period_string(freq: str, year: int, month: int, day: int, weekday: int) -> str:
    """
    缓存的周期字符串计算函数

    Args:
        freq: 更新周期
        year: 年份
        month: 月份
        day: 日期
        weekday: 星期几

    Returns:
        周期字符串
    """
    dt = datetime(year, month, day)

    if freq == "ME":
        return dt.strftime("%Y-%m")
    elif freq == "W-MON":
        return dt.strftime("%Y-W%W")
    elif freq == "2W-MON":
        week_num = int(dt.strftime("%W"))
        biweek_num = (week_num // 2) + 1
        return f"{dt.year}-W{biweek_num:02d}"
    else:
        return dt.strftime("%Y-%m")


class DynamicUniverseManager:
    """
    动态 Universe 管理器

    功能：
    - 从 JSON 文件加载预计算的 Universe 数据
    - 根据时间戳自动切换活跃币种池
    - 判断标的是否在当前活跃池中

    Universe 更新周期：
    - ME: 月度更新
    - W-MON: 周度更新（每周一）
    - 2W-MON: 双周更新
    """

    def __init__(
        self,
        universe_file: Path | str,
        freq: str = "ME",
    ):
        """
        初始化 Universe 管理器

        Args:
            universe_file: Universe JSON 文件路径
            freq: 更新周期（ME=月度, W-MON=周度, 2W-MON=双周）
        """
        self.universe_file = Path(universe_file)
        self.freq = freq

        # Universe 数据
        self.universe_data: dict[str, list[str]] = {}  # {"2020-02": ["BTCUSDT", ...]}
        self.current_period: str | None = None
        self.active_symbols: set[str] = set()

        # 加载 Universe 数据
        self._load_universe()

    def _load_universe(self) -> None:
        """从 JSON 文件加载 Universe 数据"""
        if not self.universe_file.exists():
            raise FileNotFoundError(f"Universe 文件不存在: {self.universe_file}")

        try:
            with open(self.universe_file, "r") as f:
                raw_data = json.load(f)

            # 转换符号格式：BTCUSDT:USDT -> BTCUSDT
            for period, symbols in raw_data.items():
                self.universe_data[period] = [s.split(":")[0] if ":" in s else s for s in symbols]

        except Exception as e:
            raise RuntimeError(f"加载 Universe 文件失败: {e}")

    def _get_period_string(self, dt: datetime) -> str:
        """
        根据 freq 生成周期字符串（使用全局缓存函数）

        Args:
            dt: 日期时间

        Returns:
            周期字符串（如 "2020-02", "2020-W05"）
        """
        return _cached_period_string(self.freq, dt.year, dt.month, dt.day, dt.weekday())

    def update(self, timestamp: int) -> bool:
        """
        根据时间戳更新活跃币种池

        Args:
            timestamp: 时间戳（纳秒）

        Returns:
            True 表示周期发生变化
        """
        dt = datetime.fromtimestamp(timestamp / 1e9)
        period_str = self._get_period_string(dt)

        # 周期未变化
        if period_str == self.current_period:
            return False

        # 周期变化，更新活跃币种
        if period_str not in self.universe_data:
            # 周期不在数据中，保持当前状态
            return False

        self.current_period = period_str
        self.active_symbols = set(self.universe_data[period_str])

        return True

    def is_active(self, symbol: str) -> bool:
        """
        判断标的是否在当前活跃池中

        Args:
            symbol: 标的符号（如 "BTCUSDT"）

        Returns:
            True 表示标的在活跃池中
        """
        # 如果没有加载 Universe 数据，默认所有标的都活跃
        if not self.universe_data:
            return True

        # 标准化符号格式（去除连字符和后缀）
        base_symbol = symbol.split("-")[0].split(".")[0]
        return base_symbol in self.active_symbols

    def get_active_symbols(self) -> set[str]:
        """获取当前活跃币种集合"""
        return self.active_symbols.copy()

    def get_current_period(self) -> str | None:
        """获取当前周期字符串"""
        return self.current_period

    def get_universe_size(self) -> int:
        """获取当前 Universe 规模"""
        return len(self.active_symbols)

    def get_all_periods(self) -> list[str]:
        """获取所有可用周期"""
        return sorted(self.universe_data.keys())
