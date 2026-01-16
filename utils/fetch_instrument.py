import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

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

    async def fetch_one(
        self, instrument_id_str: str, retries: int = 3
    ) -> Optional[Path]:
        """
        Fetch a single instrument and save it.
        """
        for attempt in range(1, retries + 1):
            try:
                instrument_id = InstrumentId.from_str(instrument_id_str)
                venue: str = instrument_id.venue.value
                symbol: str = instrument_id.symbol.value

                instrument = None
                if venue == "BINANCE":
                    is_futures = "-PERP" in symbol or "-DELIVERY" in symbol
                    provider = self._get_binance_provider(is_futures)
                    await provider.load_async(instrument_id)
                    instrument = provider.find(instrument_id)

                elif venue == "OKX":
                    provider = self._get_okx_provider()
                    await provider.load_async(instrument_id)
                    instrument = provider.find(instrument_id)

                if instrument:
                    venue_dir = self.output_dir / venue
                    venue_dir.mkdir(exist_ok=True)
                    file_path = venue_dir / f"{symbol}.json"

                    def enc_hook(obj):
                        if hasattr(obj, "to_dict"):
                            try:
                                return obj.to_dict()
                            except TypeError:
                                return obj.to_dict(obj)
                        return str(obj)

                    with open(file_path, "wb") as f:
                        f.write(msgspec.json.encode(instrument, enc_hook=enc_hook))

                    logger.info(
                        f"✅ Saved: {venue}/{symbol} (Price Step: {instrument.price_increment})"
                    )
                    return file_path
                else:
                    logger.warning(f"⚠️ Instrument not found: {instrument_id_str}")
                    return None

            except Exception as e:
                if attempt < retries:
                    # Longer sleep if we hit rate limits (implied by errors)
                    sleep_time = 2.0 * attempt
                    logger.warning(
                        f"⚠️ Error fetching {instrument_id_str}: {e}. Retrying in {sleep_time}s..."
                    )
                    await asyncio.sleep(sleep_time)
                else:
                    logger.error(f"🔥 Final error fetching {instrument_id_str}: {e}")
                    return None

    async def fetch_all(self, instrument_ids: List[str]):
        """Batch fetch with shared clients"""
        logger.info(f"🚀 Starting batch fetch for {len(instrument_ids)} instruments")
        for pid in instrument_ids:
            await self.fetch_one(pid)
            # Small delay between instruments to be polite to the API
            await asyncio.sleep(0.2)


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
