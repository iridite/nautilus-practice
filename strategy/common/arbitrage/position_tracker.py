"""Position tracker for arbitrage pairs."""

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class ArbitragePair:
    """套利配对数据结构（不是持仓）"""

    pair_id: str
    spot_position_id: str  # 引用 NautilusTrader 的 Position ID
    perp_position_id: str  # 引用 NautilusTrader 的 Position ID
    entry_time: int  # 纳秒时间戳
    entry_basis: float
    entry_annual_return: float
    funding_rate_collected: Decimal = field(default_factory=lambda: Decimal("0"))
    negative_funding_count: int = 0


class ArbitragePairTracker:
    """
    套利配对跟踪器（不是持仓跟踪器）

    职责:
    - 记录现货持仓和合约持仓的配对关系
    - 记录套利特有的元数据（entry_basis, funding_rate_collected）
    - 不重复存储 quantity/price（从 NautilusTrader cache 读取）
    """

    def __init__(self, max_pairs: int = 3):
        self._pairs: dict[str, ArbitragePair] = {}
        self._max_pairs = max_pairs

    def link_positions(
        self,
        spot_position_id: str,
        perp_position_id: str,
        entry_basis: float,
        entry_annual_return: float,
        entry_time: int,
    ) -> str:
        """关联现货和合约持仓，返回 pair_id"""
        pair_id = f"{spot_position_id}_{perp_position_id}"

        pair = ArbitragePair(
            pair_id=pair_id,
            spot_position_id=spot_position_id,
            perp_position_id=perp_position_id,
            entry_time=entry_time,
            entry_basis=entry_basis,
            entry_annual_return=entry_annual_return,
        )

        self._pairs[pair_id] = pair
        return pair_id

    def unlink_pair(self, pair_id: str) -> ArbitragePair | None:
        """移除配对"""
        return self._pairs.pop(pair_id, None)

    def get_pair(self, pair_id: str) -> ArbitragePair | None:
        """获取配对"""
        return self._pairs.get(pair_id)

    def get_pair_by_position_id(self, position_id: str) -> ArbitragePair | None:
        """通过任一持仓 ID 查找配对"""
        for pair in self._pairs.values():
            if pair.spot_position_id == position_id or pair.perp_position_id == position_id:
                return pair
        return None

    def update_funding_rate(self, pair_id: str, funding_pnl: Decimal) -> None:
        """更新资金费率收益"""
        pair = self._pairs.get(pair_id)
        if pair:
            pair.funding_rate_collected += funding_pnl

    def increment_negative_funding(self, pair_id: str) -> None:
        """增加负资金费率计数"""
        pair = self._pairs.get(pair_id)
        if pair:
            pair.negative_funding_count += 1

    def reset_negative_funding(self, pair_id: str) -> None:
        """重置负资金费率计数"""
        pair = self._pairs.get(pair_id)
        if pair:
            pair.negative_funding_count = 0

    def get_holding_days(self, pair_id: str, current_time: int) -> float:
        """获取持仓天数"""
        pair = self._pairs.get(pair_id)
        if not pair:
            return 0.0

        holding_ns = current_time - pair.entry_time
        # 纳秒转天数: 1 天 = 24 * 60 * 60 * 1e9 纳秒
        holding_days = holding_ns / (24 * 60 * 60 * 1e9)
        return holding_days

    def should_close_by_time(
        self, pair_id: str, current_time: int, min_days: int = 7, max_days: int = 90
    ) -> tuple[bool, str]:
        """判断是否因时间触发平仓"""
        holding_days = self.get_holding_days(pair_id, current_time)

        if holding_days < min_days:
            return False, ""

        if holding_days >= max_days:
            return True, f"max_holding_days_reached ({holding_days:.1f} >= {max_days})"

        return False, ""

    def should_close_by_funding(self, pair_id: str, threshold: int = 3) -> bool:
        """判断是否因负资金费率触发平仓"""
        pair = self._pairs.get(pair_id)
        if not pair:
            return False

        return pair.negative_funding_count >= threshold

    def can_open_new_pair(self) -> bool:
        """判断是否可以开新仓"""
        return len(self._pairs) < self._max_pairs

    def get_all_pairs(self) -> list[ArbitragePair]:
        """获取所有配对"""
        return list(self._pairs.values())
