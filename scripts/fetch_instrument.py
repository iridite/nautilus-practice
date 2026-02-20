import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import msgspec
from nautilus_trader.adapters.binance import (
    BinanceFuturesInstrumentProvider,
    BinanceSpotInstrumentProvider,
)
from nautilus_trader.adapters.binance.http.client import BinanceHttpClient
from nautilus_trader.adapters.okx import OKXInstrumentProvider

# Nautilus imports
from nautilus_trader.common.component import LiveClock
from nautilus_trader.core.nautilus_pyo3 import OKXHttpClient, OKXInstrumentType
from nautilus_trader.model.identifiers import InstrumentId
from tqdm import tqdm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("InstrumentFetcher")

# Default output path
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "data" / "instrument"


class InstrumentFetcher:
    """
    Responsible for fetching the latest Instrument definitions from exchanges
    and saving them as JSON files. Reuses clients to optimize performance.
    """

    def __init__(self, output_dir: Path = DEFAULT_OUTPUT_DIR):
        self.output_dir = output_dir
        self._ensure_dir()
        self.clock = LiveClock()

        # Reusable clients and providers
        self._clients: Dict[str, Any] = {}
        self._providers: Dict[str, Any] = {}

    def _ensure_dir(self):
        """Ensure the output directory exists"""
        if not self.output_dir.exists():
            self.output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 Created directory: {self.output_dir}")

    def _get_binance_client(self, is_futures: bool) -> BinanceHttpClient:
        key = f"BINANCE_{'FUTURES' if is_futures else 'SPOT'}"
        if key not in self._clients:
            base_url = (
                "https://fapi.binance.com" if is_futures else "https://api.binance.com"
            )
            self._clients[key] = BinanceHttpClient(
                clock=self.clock,
                api_key=None,
                api_secret=None,
                base_url=base_url,
            )
        return self._clients[key]

    def _get_binance_provider(self, is_futures: bool) -> Any:
        key = f"BINANCE_{'FUTURES' if is_futures else 'SPOT'}"
        if key not in self._providers:
            client = self._get_binance_client(is_futures)
            if is_futures:
                self._providers[key] = BinanceFuturesInstrumentProvider(
                    client=client, clock=self.clock
                )
            else:
                self._providers[key] = BinanceSpotInstrumentProvider(
                    client=client, clock=self.clock
                )
        return self._providers[key]

    def _get_okx_client(self) -> OKXHttpClient:
        key = "OKX"
        if key not in self._clients:
            self._clients[key] = OKXHttpClient(
                api_key="",
                api_secret="",
                api_passphrase="",
                base_url="https://www.okx.com",
            )
        return self._clients[key]

    def _get_okx_provider(self) -> OKXInstrumentProvider:
        key = "OKX"
        if key not in self._providers:
            client = self._get_okx_client()
            self._providers[key] = OKXInstrumentProvider(
                client=client,
                instrument_types=(
                    OKXInstrumentType.SPOT,
                    OKXInstrumentType.SWAP,
                    OKXInstrumentType.FUTURES,
                    OKXInstrumentType.OPTION,
                ),
            )
        return self._providers[key]

    def _parse_instrument_id(self, instrument_id_str: str) -> Tuple[Optional[InstrumentId], Optional[str], Optional[str], Optional[str]]:
        """
        解析 instrument ID 字符串
        
        Returns:
            Tuple of (instrument_id, venue, symbol, error_message)
        """
        try:
            instrument_id = InstrumentId.from_str(instrument_id_str)
            venue = instrument_id.venue.value
            symbol = instrument_id.symbol.value
            return instrument_id, venue, symbol, None
        except Exception as e:
            error_msg = f"❌ Invalid instrument ID string '{instrument_id_str}': {e}"
            return None, None, None, error_msg

    async def _fetch_instrument_from_provider(self, instrument_id: InstrumentId, venue: str, symbol: str):
        """从交易所提供商获取 instrument"""
        if venue == "BINANCE":
            is_futures = "-PERP" in symbol or "-DELIVERY" in symbol
            provider = self._get_binance_provider(is_futures)
            await provider.load_async(instrument_id)
            return provider.find(instrument_id)
        
        if venue == "OKX":
            provider = self._get_okx_provider()
            await provider.load_async(instrument_id)
            return provider.find(instrument_id)
        
        return None

    def _save_instrument_to_file(self, instrument, file_path: Path, venue: str, symbol: str) -> str:
        """保存 instrument 到文件"""
        file_path.parent.mkdir(parents=True, exist_ok=True)

        def enc_hook(obj):
            if hasattr(obj, "to_dict"):
                try:
                    return obj.to_dict()
                except TypeError:
                    return obj.to_dict(obj)
            return str(obj)

        with open(file_path, "wb") as f:
            f.write(msgspec.json.encode(instrument, enc_hook=enc_hook))

        return f"✅ Saved: {venue}/{symbol} (Price Step: {instrument.price_increment})"

    async def _retry_fetch_instrument(
        self, instrument_id: InstrumentId, venue: str, symbol: str, 
        instrument_id_str: str, retries: int, silent: bool
    ) -> Tuple[Optional[Any], Optional[str]]:
        """重试获取 instrument"""
        for attempt in range(1, retries + 1):
            try:
                instrument = await self._fetch_instrument_from_provider(instrument_id, venue, symbol)
                if instrument:
                    return instrument, None
                return None, f"⚠️ Instrument not found: {instrument_id_str}"
            
            except Exception as e:
                if attempt < retries:
                    sleep_time = 2.0 * attempt
                    if not silent:
                        logger.warning(
                            f"⚠️ Error fetching {instrument_id_str}: {e}. Retrying in {sleep_time}s..."
                        )
                    await asyncio.sleep(sleep_time)
                else:
                    return None, f"🔥 Final error fetching {instrument_id_str}: {e}"
        
        return None, None

    async def fetch_one(
        self, instrument_id_str: str, retries: int = 3, silent: bool = False
    ) -> Tuple[Optional[Path], bool, Optional[str]]:
        """
        Fetch a single instrument and save it.

        Returns:
            Tuple of (path, was_fetched, log_message)
            - path: Path to saved file or None if failed
            - was_fetched: True if newly fetched, False if existed or failed
            - log_message: Log message to display after progress bar completes
        """
        # 解析 instrument ID
        instrument_id, venue, symbol, error_msg = self._parse_instrument_id(instrument_id_str)
        if error_msg:
            return None, False, error_msg

        # 检查文件是否已存在
        file_path = self.output_dir / venue / f"{symbol}.json"
        if file_path.exists():
            return file_path, False, None

        # 重试获取 instrument
        instrument, error_msg = await self._retry_fetch_instrument(
            instrument_id, venue, symbol, instrument_id_str, retries, silent
        )
        
        if error_msg:
            return None, False, error_msg
        
        if not instrument:
            return None, False, None

        # 保存到文件
        log_msg = self._save_instrument_to_file(instrument, file_path, venue, symbol)
        return file_path, True, log_msg

    async def fetch_all(self, instrument_ids: List[str]):
        """Batch fetch with shared clients using tqdm progress bar"""
        skipped_count = 0
        fetched_count = 0
        failed_count = 0
        log_messages: List[str] = []

        with tqdm(
            instrument_ids,
            desc="🔄 Fetching instruments",
            unit="inst",
            ncols=80,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
        ) as pbar:
            for pid in pbar:
                # 提取 symbol 用于显示
                try:
                    symbol_display = pid.split(".")[0]
                except Exception:
                    symbol_display = pid

                pbar.set_postfix_str(symbol_display, refresh=True)

                path, was_fetched, log_msg = await self.fetch_one(pid, silent=True)

                if path is None:
                    failed_count += 1
                elif was_fetched:
                    fetched_count += 1
                    # Small delay between instruments to be polite to the API
                    await asyncio.sleep(0.2)
                else:
                    skipped_count += 1

                # 收集日志消息，进度条结束后统一打印
                if log_msg:
                    log_messages.append(log_msg)

        # 进度条结束后打印收集到的日志
        for msg in log_messages:
            print(f"  {msg}")

        # 打印汇总信息
        print(
            f"📊 Instrument fetch complete: {fetched_count} new, {skipped_count} existed, {failed_count} failed"
        )


def update_instruments(
    instrument_ids: List[str], output_dir: Path = DEFAULT_OUTPUT_DIR
):
    """
    [Synchronous Entry Point] for main.py
    """
    fetcher = InstrumentFetcher(output_dir)
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        asyncio.ensure_future(fetcher.fetch_all(instrument_ids))
    else:
        loop.run_until_complete(fetcher.fetch_all(instrument_ids))


if __name__ == "__main__":
    targets = [
        "ETHUSDT-PERP.BINANCE",
        "BTCUSDT-PERP.BINANCE",
        "BTCUSDT.BINANCE",
        "ETH-USDT-SWAP.OKX",
        "ETH-USDT.OKX",
    ]
    update_instruments(targets)
