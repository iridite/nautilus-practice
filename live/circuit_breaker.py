"""
资金费率熔断器和现货替代管理器

在入场前检查资金费率,根据阈值决定:
- REJECT: 拒绝信号 (资金费率 > 100% 年化)
- SPOT: 切换到现货 (资金费率 50% - 100% 年化)
- PERP: 正常执行永续合约 (资金费率 < 50% 年化)
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from live.funding_rate_monitor import FundingRateMonitor, FundingRateSnapshot


class InstrumentType(Enum):
    """标的类型"""

    PERP = "PERP"  # 永续合约
    SPOT = "SPOT"  # 现货
    REJECT = "REJECT"  # 拒绝


@dataclass
class ExecutionDecision:
    """执行决策"""

    decision: InstrumentType  # 决策类型
    instrument_id: str  # 标的 ID (如 "ETHUSDT.BINANCE" 或 "ETHUSDT-PERP.BINANCE")
    reason: str  # 决策原因
    funding_rate_annual: Optional[float]  # 年化资金费率


class CircuitBreakerManager:
    """
    资金费率熔断器管理器

    功能:
    - 在入场前检查资金费率
    - 根据阈值决定执行策略 (REJECT/SPOT/PERP)
    - 记录熔断和切换事件
    """

    def __init__(
        self,
        funding_monitor: FundingRateMonitor,
        fallback_threshold_annual: float = 50.0,  # 50% 年化触发现货回退
        circuit_breaker_annual: float = 100.0,  # 100% 年化拒绝信号
        venue: str = "BINANCE",
    ):
        """
        初始化熔断器管理器

        Parameters
        ----------
        funding_monitor : FundingRateMonitor
            资金费率监控器
        fallback_threshold_annual : float
            现货回退阈值 (年化百分比)
        circuit_breaker_annual : float
            熔断器阈值 (年化百分比)
        venue : str
            交易所名称
        """
        self.funding_monitor = funding_monitor
        self.fallback_threshold_annual = fallback_threshold_annual
        self.circuit_breaker_annual = circuit_breaker_annual
        self.venue = venue

        # 永续合约到现货的映射
        self.perp_to_spot_map = {
            f"ETHUSDT-PERP.{venue}": f"ETHUSDT.{venue}",
            f"BTCUSDT-PERP.{venue}": f"BTCUSDT.{venue}",
            f"SOLUSDT-PERP.{venue}": f"SOLUSDT.{venue}",
            f"BNBUSDT-PERP.{venue}": f"BNBUSDT.{venue}",
            f"ADAUSDT-PERP.{venue}": f"ADAUSDT.{venue}",
            f"DOGEUSDT-PERP.{venue}": f"DOGEUSDT.{venue}",
            f"XRPUSDT-PERP.{venue}": f"XRPUSDT.{venue}",
            f"DOTUSDT-PERP.{venue}": f"DOTUSDT.{venue}",
            f"MATICUSDT-PERP.{venue}": f"MATICUSDT.{venue}",
            f"AVAXUSDT-PERP.{venue}": f"AVAXUSDT.{venue}",
        }

        # 统计计数器
        self.stats = {
            "total_signals": 0,
            "rejected_by_circuit_breaker": 0,
            "switched_to_spot": 0,
            "normal_perp_execution": 0,
        }

        self.logger = logging.getLogger(__name__)

    async def evaluate_signal(self, symbol: str, instrument_id: str) -> ExecutionDecision:
        """
        评估信号并决定执行策略

        Parameters
        ----------
        symbol : str
            交易对符号 (如 "ETHUSDT")
        instrument_id : str
            原始标的 ID (如 "ETHUSDT-PERP.BINANCE")

        Returns
        -------
        ExecutionDecision
            执行决策

        Raises
        ------
        Exception
            资金费率获取失败
        """
        self.stats["total_signals"] += 1

        try:
            # 获取资金费率
            snapshot = await self.funding_monitor.get_rate(symbol)
            funding_rate_annual = float(snapshot.rate_annual)

            # 决策逻辑
            if funding_rate_annual > self.circuit_breaker_annual:
                # 熔断器触发: 拒绝信号
                self.stats["rejected_by_circuit_breaker"] += 1
                decision = ExecutionDecision(
                    decision=InstrumentType.REJECT,
                    instrument_id="",
                    reason=f"Circuit breaker: {funding_rate_annual:.2f}% > {self.circuit_breaker_annual}%",
                    funding_rate_annual=funding_rate_annual,
                )
                self.logger.warning(
                    f"🚫 Circuit breaker triggered for {symbol}: "
                    f"{funding_rate_annual:.2f}% > {self.circuit_breaker_annual}%"
                )

            elif funding_rate_annual > self.fallback_threshold_annual:
                # 现货回退: 切换到现货
                self.stats["switched_to_spot"] += 1
                spot_instrument = self._map_to_spot(instrument_id)
                decision = ExecutionDecision(
                    decision=InstrumentType.SPOT,
                    instrument_id=spot_instrument,
                    reason=f"Spot fallback: {funding_rate_annual:.2f}% > {self.fallback_threshold_annual}%",
                    funding_rate_annual=funding_rate_annual,
                )
                self.logger.info(
                    f"💱 Spot fallback for {symbol}: "
                    f"{funding_rate_annual:.2f}% > {self.fallback_threshold_annual}%, "
                    f"switching to {spot_instrument}"
                )

            else:
                # 正常执行: 使用永续合约
                self.stats["normal_perp_execution"] += 1
                decision = ExecutionDecision(
                    decision=InstrumentType.PERP,
                    instrument_id=instrument_id,
                    reason=f"Normal execution: {funding_rate_annual:.2f}% < {self.fallback_threshold_annual}%",
                    funding_rate_annual=funding_rate_annual,
                )
                self.logger.debug(
                    f"✅ Normal perp execution for {symbol}: {funding_rate_annual:.2f}%"
                )

            return decision

        except Exception as e:
            self.logger.error(f"Failed to evaluate signal for {symbol}: {e}")
            # 降级策略: 发生错误时拒绝信号 (保守模式)
            return ExecutionDecision(
                decision=InstrumentType.REJECT,
                instrument_id="",
                reason=f"Error: {str(e)}",
                funding_rate_annual=None,
            )

    def _map_to_spot(self, perp_instrument_id: str) -> str:
        """
        将永续合约标的映射到现货标的

        Parameters
        ----------
        perp_instrument_id : str
            永续合约标的 ID

        Returns
        -------
        str
            现货标的 ID
        """
        spot_instrument = self.perp_to_spot_map.get(perp_instrument_id)
        if not spot_instrument:
            # 如果映射不存在,尝试自动生成
            # 例如: "ETHUSDT-PERP.BINANCE" -> "ETHUSDT.BINANCE"
            spot_instrument = perp_instrument_id.replace("-PERP", "")
            self.logger.warning(
                f"No explicit mapping for {perp_instrument_id}, "
                f"using auto-generated: {spot_instrument}"
            )
        return spot_instrument

    def get_statistics(self) -> dict:
        """
        获取统计信息

        Returns
        -------
        dict
            统计数据
        """
        total = self.stats["total_signals"]
        if total == 0:
            return self.stats

        return {
            **self.stats,
            "rejection_rate": self.stats["rejected_by_circuit_breaker"] / total,
            "spot_fallback_rate": self.stats["switched_to_spot"] / total,
            "normal_execution_rate": self.stats["normal_perp_execution"] / total,
        }

    def reset_statistics(self):
        """重置统计计数器"""
        for key in self.stats:
            self.stats[key] = 0
