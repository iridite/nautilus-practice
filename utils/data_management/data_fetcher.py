"""
多数据源OHLCV数据获取器

支持：
1. Binance Public API (无需API key)
2. CoinGecko API (免费层)
3. CCXT (备用)
"""

from typing import Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def _create_retry_session(
    retries: int = 3,
    backoff_factor: float = 0.3,
    status_forcelist: tuple = (500, 502, 503, 504),
) -> requests.Session:
    """
    创建带有重试机制的 requests.Session

    Args:
        retries: 最大重试次数
        backoff_factor: 重试间隔的指数退避因子 (0.3 表示 0.3s, 0.6s, 1.2s...)
        status_forcelist: 触发重试的 HTTP 状态码

    Returns:
        配置好重试策略的 Session 对象
    """
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["GET", "POST"],  # 只对幂等方法重试
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


class BinanceFetcher:
    """Binance公开API获取器"""

    BASE_URL = "https://api.binance.com"

    INTERVAL_MAP = {
        "1m": "1m",
        "3m": "3m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "2h": "2h",
        "4h": "4h",
        "6h": "6h",
        "8h": "8h",
        "12h": "12h",
        "1d": "1d",
        "3d": "3d",
        "1w": "1w",
        "1M": "1M",
    }

    def __init__(self):
        """初始化 Fetcher，创建带重试机制的 HTTP session"""
        self.session = _create_retry_session()

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """
        获取OHLCV数据

        Args:
            symbol: 交易对 (如 BTCUSDT)
            timeframe: 时间周期
            start_time: 开始时间戳(毫秒)
            end_time: 结束时间戳(毫秒)
            limit: 最多返回条数(最大1000)

        Raises:
            ValueError: 如果时间戳超出有效范围
        """
        # 验证时间戳范围，防止整数溢出
        # 最大时间戳：8640000000000 (约公元 2243 年)
        # 最小时间戳：0 (1970-01-01)
        MAX_TIMESTAMP = 8640000000000
        MIN_TIMESTAMP = 0

        if start_time is not None:
            if not isinstance(start_time, int):
                raise ValueError(f"start_time 必须是整数，当前类型: {type(start_time)}")
            if start_time < MIN_TIMESTAMP or start_time > MAX_TIMESTAMP:
                raise ValueError(
                    f"start_time 超出有效范围: {start_time} "
                    f"(有效范围: {MIN_TIMESTAMP} - {MAX_TIMESTAMP})"
                )

        if end_time is not None:
            if not isinstance(end_time, int):
                raise ValueError(f"end_time 必须是整数，当前类型: {type(end_time)}")
            if end_time < MIN_TIMESTAMP or end_time > MAX_TIMESTAMP:
                raise ValueError(
                    f"end_time 超出有效范围: {end_time} "
                    f"(有效范围: {MIN_TIMESTAMP} - {MAX_TIMESTAMP})"
                )

        # 验证时间范围逻辑
        if start_time is not None and end_time is not None:
            if start_time >= end_time:
                raise ValueError(f"start_time ({start_time}) 必须小于 end_time ({end_time})")

        interval = self.INTERVAL_MAP.get(timeframe, "1h")

        params = {
            "symbol": symbol.replace("/", ""),
            "interval": interval,
            "limit": min(limit, 1000),
        }

        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        # 使用带重试机制的 session 发送请求
        resp = self.session.get(f"{self.BASE_URL}/api/v3/klines", params=params, timeout=10)
        resp.raise_for_status()

        data = resp.json()
        df = pd.DataFrame(
            data,
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_volume",
                "trades",
                "taker_buy_base",
                "taker_buy_quote",
                "ignore",
            ],
        )

        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        return df[["timestamp", "open", "high", "low", "close", "volume"]]


class CoinGeckoFetcher:
    """CoinGecko API获取器"""

    BASE_URL = "https://api.coingecko.com/api/v3"

    SYMBOL_MAP = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binancecoin"}

    def __init__(self):
        """初始化 Fetcher，创建带重试机制的 HTTP session"""
        self.session = _create_retry_session()

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", days: int = 30) -> pd.DataFrame:
        """
        获取OHLCV数据

        Args:
            symbol: 交易对 (如 BTC/USDT)
            timeframe: 时间周期 (仅支持1d)
            days: 历史天数
        """
        base = symbol.split("/")[0] if "/" in symbol else symbol[:3]
        coin_id = self.SYMBOL_MAP.get(base.upper())

        if not coin_id:
            raise ValueError(f"Unsupported symbol: {symbol}")

        params = {"vs_currency": "usd", "days": days}

        # 使用带重试机制的 session 发送请求
        resp = self.session.get(f"{self.BASE_URL}/coins/{coin_id}/ohlc", params=params, timeout=10)
        resp.raise_for_status()

        data = resp.json()
        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df["volume"] = 0.0

        return df


class DataFetcher:
    """统一数据获取器"""

    def __init__(self):
        self.binance = BinanceFetcher()
        self.coingecko = CoinGeckoFetcher()

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        source: str = "binance",
    ) -> pd.DataFrame:
        """
        获取OHLCV数据，支持多数据源切换

        Args:
            symbol: 交易对
            timeframe: 时间周期
            start_time: 开始时间戳(毫秒)
            end_time: 结束时间戳(毫秒)
            source: 数据源 (binance/coingecko/auto)
        """
        if source == "auto":
            try:
                return self.binance.fetch_ohlcv(symbol, timeframe, start_time, end_time)
            except Exception:
                return self.coingecko.fetch_ohlcv(symbol, timeframe)
        elif source == "binance":
            return self.binance.fetch_ohlcv(symbol, timeframe, start_time, end_time)
        elif source == "coingecko":
            return self.coingecko.fetch_ohlcv(symbol, timeframe)
        else:
            raise ValueError(f"Unknown source: {source}")
