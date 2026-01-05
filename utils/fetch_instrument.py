import asyncio
import logging
from pathlib import Path
from typing import List, Optional

# Nautilus 依赖
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.adapters.binance.http.client import BinanceHttpClient
from nautilus_trader.adapters.okx.http.client import OkxHttpClient

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("InstrumentFetcher")

# 定义默认输出路径 (相对于当前脚本位置)
# 假设脚本在 workspace/utils/ 下，输出到 workspace/data/instruments/
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "data" / "instruments"

class InstrumentFetcher:
    """
    负责从各大交易所获取最新的 Instrument 定义并保存为 JSON 文件。
    """

    def __init__(self, output_dir: Path = DEFAULT_OUTPUT_DIR):
        self.output_dir = output_dir
        self._ensure_dir()

    def _ensure_dir(self):
        """确保输出目录存在"""
        if not self.output_dir.exists():
            self.output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 Created directory: {self.output_dir}")

    async def fetch_one(self, instrument_id_str: str, use_testnet: bool = False) -> Optional[Path]:
        """
        获取单个 instrument 并保存
        :param instrument_id_str: Nautilus 格式 ID (e.g., 'ETHUSDT-PERP.BINANCE')
        :param use_testnet: 是否使用测试网获取数据 (通常建议用主网，数据更准确)
        """
        try:
            instrument_id = InstrumentId.from_str(instrument_id_str)
            venue = instrument_id.venue.value
            
            client = self._get_client(venue, use_testnet)
            if not client:
                logger.error(f"❌ Unsupported venue: {venue}")
                return None

            logger.info(f"⏳ Fetching {instrument_id_str} from {venue}...")
            
            # 调用 API 获取定义
            instrument = await client.get_instrument(instrument_id)
            
            # 关闭客户端连接
            await client.close()

            if instrument:
                # 生成保存路径: data/instruments/BINANCE/ETHUSDT-PERP.json
                venue_dir = self.output_dir / venue
                venue_dir.mkdir(exist_ok=True)
                
                file_path = venue_dir / f"{instrument_id.symbol.value}.json"
                
                # 保存为二进制 JSON (Nautilus 标准序列化)
                with open(file_path, "wb") as f:
                    f.write(instrument.to_json())
                
                logger.info(f"✅ Saved: {file_path} (Price Step: {instrument.price_increment})")
                return file_path
            else:
                logger.warning(f"⚠️ Instrument not found on exchange: {instrument_id_str}")
                return None

        except Exception as e:
            logger.error(f"🔥 Error fetching {instrument_id_str}: {e}")
            return None

    def _get_client(self, venue: str, testnet: bool):
        """工厂方法：根据 Venue 返回对应的 Client"""
        if venue == "BINANCE":
            return BinanceHttpClient(testnet=testnet)
        elif venue == "OKX":
            return OkxHttpClient(testnet=testnet)
        # 可以在这里扩展其他交易所
        return None

    async def fetch_all(self, instrument_ids: List[str]):
        """批量获取"""
        tasks = [self.fetch_one(pid) for pid in instrument_ids]
        await asyncio.gather(*tasks)

# --- 供外部调用的同步封装函数 ---

def update_instruments(instrument_ids: List[str], output_dir: Path = DEFAULT_OUTPUT_DIR):
    """
    [同步入口] 供 main.py 直接调用
    """
    fetcher = InstrumentFetcher(output_dir)
    try:
        # 处理 asyncio 事件循环，防止在已有 loop 中调用冲突
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # 如果已经在 async 环境中 (很少见，除非你的 main 也是 async)
            logger.warning("Running in existing loop, ensure this is intended.")
            loop.create_task(fetcher.fetch_all(instrument_ids))
        else:
            asyncio.run(fetcher.fetch_all(instrument_ids))
            
    except Exception as e:
        logger.error(f"Failed to update instruments: {e}")

# --- 脚本入口 (用于测试) ---
if __name__ == "__main__":
    # 测试列表
    targets = [
        "ETHUSDT-PERP.BINANCE",
        "BTCUSDT-PERP.BINANCE",
        "ETH-USDT-SWAP.OKX" # OKX 命名方式不太一样
    ]
    
    print("🚀 Starting manual instrument update...")
    update_instruments(targets)
    print("✨ Done.")