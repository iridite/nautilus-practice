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
        """
        interval = self.INTERVAL_MAP.get(timeframe, "1h")

        params = {
            "symbol": symbol.replace("/", ""),
            "interval": interval,
            "limit": min(limit, 1000),
        }

        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        resp = requests.get(f"{self.BASE_URL}/api/v3/klines", params=params, timeout=10)
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

        resp = requests.get(f"{self.BASE_URL}/coins/{coin_id}/ohlc", params=params, timeout=10)
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
