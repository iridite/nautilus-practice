"""
实时资金费率监控模块

从 Binance API 获取实时资金费率数据,支持缓存和熔断器逻辑
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

import aiohttp


@dataclass
class FundingRateSnapshot:
    """资金费率快照"""

    symbol: str
    rate_8h: Decimal  # 8小时费率 (如 0.0001 = 0.01%)
    rate_annual: Decimal  # 年化费率 (如 10.95 = 10.95%)
    mark_price: Decimal  # 标记价格
    next_funding_time: datetime  # 下次结算时间
    timestamp: datetime  # 数据时间戳
    staleness_sec: int  # 数据新鲜度 (秒)


class FundingRateMonitor:
    """
    资金费率监控器

    功能:
    - 从 Binance API 获取实时资金费率
    - 5分钟缓存 (避免频繁 API 调用)
    - 15分钟最大延迟容忍 (数据过期则拒绝)
    - 支持批量查询
    """

    def __init__(
        self,
        api_endpoint: str = "https://fapi.binance.com/fapi/v1/premiumIndex",
        refresh_interval_sec: int = 300,  # 5分钟
        max_staleness_sec: int = 900,  # 15分钟
        timeout_sec: int = 5,
    ):
        """
        初始化资金费率监控器

        Parameters
        ----------
        api_endpoint : str
            Binance API 端点
        refresh_interval_sec : int
            缓存刷新间隔 (秒)
        max_staleness_sec : int
            最大数据延迟容忍 (秒)
        timeout_sec : int
            API 请求超时 (秒)
        """
        self.api_endpoint = api_endpoint
        self.refresh_interval_sec = refresh_interval_sec
        self.max_staleness_sec = max_staleness_sec
        self.timeout_sec = timeout_sec

        # 缓存: {symbol: FundingRateSnapshot}
        self._cache: dict[str, FundingRateSnapshot] = {}

        self.logger = logging.getLogger(__name__)

    async def get_rate(self, symbol: str) -> FundingRateSnapshot:
        """
        获取资金费率 (带缓存)

        Parameters
        ----------
        symbol : str
            交易对符号 (如 "ETHUSDT")

        Returns
        -------
        FundingRateSnapshot
            资金费率快照

        Raises
        ------
        StaleDataError
            数据过期 (超过 max_staleness_sec)
        TimeoutError
            API 请求超时
        """
        # 检查缓存
        cached = self._cache.get(symbol)
        if cached:
            age_sec = (datetime.now() - cached.timestamp).total_seconds()
            if age_sec < self.refresh_interval_sec:
                # 缓存有效,更新新鲜度
                cached.staleness_sec = int(age_sec)
                self.logger.debug(f"Using cached funding rate for {symbol} (age: {age_sec:.1f}s)")
                return cached

        # 缓存过期或不存在,从 API 获取
        snapshot = await self._fetch_from_api(symbol)

        # 检查数据新鲜度
        if snapshot.staleness_sec > self.max_staleness_sec:
            raise StaleDataError(
                f"Funding rate data too stale for {symbol}: "
                f"{snapshot.staleness_sec}s > {self.max_staleness_sec}s"
            )

        # 更新缓存
        self._cache[symbol] = snapshot
        return snapshot

    async def refresh(self, symbols: list[str]) -> dict[str, FundingRateSnapshot]:
        """
        批量刷新资金费率

        Parameters
        ----------
        symbols : list[str]
            交易对符号列表

        Returns
        -------
        dict[str, FundingRateSnapshot]
            符号 -> 快照映射
        """
        tasks = [self._fetch_from_api(symbol) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        snapshots = {}
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                self.logger.error(f"Failed to fetch funding rate for {symbol}: {result}")
            else:
                self._cache[symbol] = result
                snapshots[symbol] = result

        return snapshots

    def get_cached_rate(self, symbol: str) -> Optional[FundingRateSnapshot]:
        """
        获取缓存的资金费率 (不触发 API 调用)

        Parameters
        ----------
        symbol : str
            交易对符号

        Returns
        -------
        FundingRateSnapshot | None
            缓存的快照,如果不存在则返回 None
        """
        cached = self._cache.get(symbol)
        if cached:
            age_sec = (datetime.now() - cached.timestamp).total_seconds()
            cached.staleness_sec = int(age_sec)
        return cached

    def is_stale(self, symbol: str, max_age_sec: Optional[int] = None) -> bool:
        """
        检查数据是否过期

        Parameters
        ----------
        symbol : str
            交易对符号
        max_age_sec : int | None
            最大年龄 (秒),默认使用 max_staleness_sec

        Returns
        -------
        bool
            True 如果数据过期或不存在
        """
        max_age = max_age_sec if max_age_sec is not None else self.max_staleness_sec
        cached = self.get_cached_rate(symbol)
        if not cached:
            return True
        return cached.staleness_sec > max_age

    async def _fetch_from_api(self, symbol: str) -> FundingRateSnapshot:
        """
        从 Binance API 获取资金费率

        Parameters
        ----------
        symbol : str
            交易对符号

        Returns
        -------
        FundingRateSnapshot
            资金费率快照

        Raises
        ------
        TimeoutError
            API 请求超时
        """
        params = {"symbol": symbol}
        timeout = aiohttp.ClientTimeout(total=self.timeout_sec)

        async with aiohttp.ClientSession() as session:
            async with session.get(self.api_endpoint, params=params, timeout=timeout) as response:
                response.raise_for_status()
                data = await response.json()

        # 解析数据
        rate_8h = Decimal(str(data["lastFundingRate"]))
        rate_annual = rate_8h * Decimal("3") * Decimal("365") * Decimal("100")
        mark_price = Decimal(str(data["markPrice"]))
        next_funding_time_ms = int(data["nextFundingTime"])
        next_funding_time = datetime.fromtimestamp(next_funding_time_ms / 1000)

        timestamp = datetime.now()
        staleness_sec = 0  # 刚获取的数据

        snapshot = FundingRateSnapshot(
            symbol=symbol,
            rate_8h=rate_8h,
            rate_annual=rate_annual,
            mark_price=mark_price,
            next_funding_time=next_funding_time,
            timestamp=timestamp,
            staleness_sec=staleness_sec,
        )

        self.logger.info(
            f"Fetched funding rate for {symbol}: "
            f"8h={rate_8h:.6f}, annual={rate_annual:.2f}%, "
            f"next_funding={next_funding_time.strftime('%H:%M:%S')}"
        )

        return snapshot


class StaleDataError(Exception):
    """数据过期异常"""

    pass
