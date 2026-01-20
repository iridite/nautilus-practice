"""
自定义数据类型：Open Interest 和 Funding Rate
用于 NautilusTrader 策略中处理交易所衍生品数据
"""

from decimal import Decimal
from typing import Any

from nautilus_trader.core.data import Data
from nautilus_trader.model.identifiers import InstrumentId


class OpenInterestData(Data):
    """
    持仓量（Open Interest）数据

    表示某一时刻某个合约的未平仓合约数量或价值。
    """

    def __init__(
        self,
        instrument_id: InstrumentId,
        open_interest: Decimal,
        ts_event: int,
        ts_init: int,
    ):
        """
        初始化 OpenInterestData

        Parameters
        ----------
        instrument_id : InstrumentId
            合约标识符
        open_interest : Decimal
            持仓量数值（通常为合约张数或 USD 计价）
        ts_event : int
            事件发生时间戳（纳秒）
        ts_init : int
            数据初始化时间戳（纳秒）
        """
        super().__init__()
        self.instrument_id = instrument_id
        self.open_interest = open_interest
        self._ts_event = ts_event
        self._ts_init = ts_init

    @property
    def ts_event(self) -> int:
        """事件时间戳（纳秒）"""
        return self._ts_event

    @property
    def ts_init(self) -> int:
        """初始化时间戳（纳秒）"""
        return self._ts_init

    def __repr__(self) -> str:
        return (
            f"OpenInterestData("
            f"instrument_id={self.instrument_id}, "
            f"open_interest={self.open_interest}, "
            f"ts_event={self._ts_event})"
        )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, OpenInterestData):
            return False
        return (
            self.instrument_id == other.instrument_id
            and self.open_interest == other.open_interest
            and self._ts_event == other._ts_event
        )

    def __hash__(self) -> int:
        return hash((self.instrument_id, self.open_interest, self._ts_event))


class FundingRateData(Data):
    """
    资金费率（Funding Rate）数据

    表示永续合约的资金费率，通常每 8 小时结算一次。
    正值表示多头支付空头，负值表示空头支付多头。
    """

    def __init__(
        self,
        instrument_id: InstrumentId,
        funding_rate: Decimal,
        next_funding_time: int | None,
        ts_event: int,
        ts_init: int,
    ):
        """
        初始化 FundingRateData

        Parameters
        ----------
        instrument_id : InstrumentId
            合约标识符
        funding_rate : Decimal
            当前资金费率（小数形式，如 0.0001 表示 0.01%）
        next_funding_time : int | None
            下次资金费率结算时间戳（纳秒），可选
        ts_event : int
            事件发生时间戳（纳秒）
        ts_init : int
            数据初始化时间戳（纳秒）
        """
        super().__init__()
        self.instrument_id = instrument_id
        self.funding_rate = funding_rate
        self.next_funding_time = next_funding_time
        self._ts_event = ts_event
        self._ts_init = ts_init

    @property
    def ts_event(self) -> int:
        """事件时间戳（纳秒）"""
        return self._ts_event

    @property
    def ts_init(self) -> int:
        """初始化时间戳（纳秒）"""
        return self._ts_init

    @property
    def funding_rate_annual(self) -> Decimal:
        """
        年化资金费率（假设每 8 小时结算一次）

        Returns
        -------
        Decimal
            年化后的资金费率（百分比形式）
        """
        # 每天 3 次，每年 365 天
        return self.funding_rate * Decimal("3") * Decimal("365") * Decimal("100")

    def __repr__(self) -> str:
        return (
            f"FundingRateData("
            f"instrument_id={self.instrument_id}, "
            f"funding_rate={self.funding_rate}, "
            f"annual={self.funding_rate_annual:.2f}%, "
            f"ts_event={self._ts_event})"
        )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, FundingRateData):
            return False
        return (
            self.instrument_id == other.instrument_id
            and self.funding_rate == other.funding_rate
            and self._ts_event == other._ts_event
        )

    def __hash__(self) -> int:
        return hash((self.instrument_id, self.funding_rate, self._ts_event))
