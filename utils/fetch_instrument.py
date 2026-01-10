import asyncio
import logging
from pathlib import Path
from typing import List, Optional

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
    and saving them as JSON files.
    """

    def __init__(self, output_dir: Path = DEFAULT_OUTPUT_DIR):
        self.output_dir = output_dir
        self._ensure_dir()
        self.clock = LiveClock()

    def _ensure_dir(self):
        """Ensure the output directory exists"""
        if not self.output_dir.exists():
            self.output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 Created directory: {self.output_dir}")

    async def fetch_one(self, instrument_id_str: str, retries: int = 3) -> Optional[Path]:
        """
        Fetch a single instrument and save it.
        """
        for attempt in range(1, retries + 1):
            try:
                # 因为使用了 NT inst ID 进行分割，所以这里的 inst ID 名称必须准确
                instrument_id = InstrumentId.from_str(instrument_id_str)
                venue: str = instrument_id.venue.value
                symbol: str = instrument_id.symbol.value

                logger.info(f"⏳ Fetching {symbol} from {venue} (Attempt {attempt}/{retries})...")

                instrument = None
                if venue == "BINANCE":
                    # Determine if it's Futures or Spot based on the symbol suffix
                    is_futures = "-PERP" in symbol or "-DELIVERY" in symbol
                    base_url = (
                        "https://fapi.binance.com"
                        if is_futures
                        else "https://api.binance.com"
                    )

                    client = BinanceHttpClient(
                        clock=self.clock,
                        api_key=None,
                        api_secret=None,
                        base_url=base_url,
                    )

                    if is_futures:
                        provider = BinanceFuturesInstrumentProvider(
                            client=client, clock=self.clock
                        )
                    else:
                        provider = BinanceSpotInstrumentProvider(
                            client=client, clock=self.clock
                        )

                    await provider.load_async(instrument_id)
                    instrument = provider.find(instrument_id)

                elif venue == "OKX":
                    client = OKXHttpClient(
                        api_key="",
                        api_secret="",
                        api_passphrase="",
                        base_url="https://www.okx.com",
                    )
                    # OKX provider needs to know which types to look for
                    provider = OKXInstrumentProvider(
                        client=client,
                        instrument_types=(
                            OKXInstrumentType.SPOT,
                            OKXInstrumentType.SWAP,
                            OKXInstrumentType.FUTURES,
                            OKXInstrumentType.OPTION,
                        ),
                    )
                    await provider.load_async(instrument_id)
                    instrument = provider.find(instrument_id)

                if instrument:
                    # Generate save path: data/instrument/BINANCE/ETHUSDT-PERP.json
                    venue_dir = self.output_dir / venue
                    venue_dir.mkdir(exist_ok=True)
                    file_path = venue_dir / f"{symbol}.json"

                    # Serialization helper for Nautilus objects
                    def enc_hook(obj):
                        if hasattr(obj, "to_dict"):
                            try:
                                return obj.to_dict()
                            except TypeError:
                                # Some Cython versions might require passing self explicitly
                                return obj.to_dict(obj)
                        return str(obj)

                    # Save as JSON
                    with open(file_path, "wb") as f:
                        f.write(msgspec.json.encode(instrument, enc_hook=enc_hook))

                    logger.info(
                        f"✅ Saved: {file_path} (Price Step: {instrument.price_increment})"
                    )
                    return file_path
                else:
                    logger.warning(
                        f"⚠️ Instrument not found on exchange: {instrument_id_str}"
                    )
                    # No retry if not found
                    return None

            except Exception as e:
                if attempt < retries:
                    logger.warning(f"⚠️ Error fetching {instrument_id_str}: {e}. Retrying in 2s...")
                    await asyncio.sleep(2.0)
                else:
                    logger.error(f"🔥 Final error fetching {instrument_id_str}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    return None

    async def fetch_all(self, instrument_ids: List[str]):
        """Batch fetch"""
        for pid in instrument_ids:
            await self.fetch_one(pid)


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
        # If already in an async environment, we need to schedule it
        asyncio.ensure_future(fetcher.fetch_all(instrument_ids))
    else:
        loop.run_until_complete(fetcher.fetch_all(instrument_ids))


if __name__ == "__main__":
    # Test list
    targets = [
        "ETHUSDT-PERP.BINANCE",
        "BTCUSDT-PERP.BINANCE",
        "BTCUSDT.BINANCE",
        "ETH-USDT-SWAP.OKX",
        "ETH-USDT-PERP.OKX",  # Do not exist
        "ETH-USDT.OKX",
    ]

    print("🚀 Starting manual instrument update...")
    update_instruments(targets)
    print("✨ Done.")
