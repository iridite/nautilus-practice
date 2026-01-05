#!/usr/bin/env python3
# -------------------------------------------------------------------------------------------------
#  Copyright (C) 2015-2025 Nautech Systems Pty Ltd. All rights reserved.
#  https://nautechsystems.io
#
#  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
#  You may not use this file except in compliance with the License.
#  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# -------------------------------------------------------------------------------------------------
import asyncio
import os
import sys
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv
from nautilus_trader.adapters.okx import (
    OKX,
    OKXDataClientConfig,
    OKXExecClientConfig,
    OKXLiveExecClientFactory,
)
from nautilus_trader.adapters.okx.factories import OKXLiveDataClientFactory
from nautilus_trader.config import (
    CacheConfig,
    InstrumentProviderConfig,
    LiveExecEngineConfig,
    LoggingConfig,
    TradingNodeConfig,
)
from nautilus_trader.core.nautilus_pyo3 import OKXContractType, OKXInstrumentType
from nautilus_trader.examples.strategies.volatility_market_maker import (
    VolatilityMarketMaker,
    VolatilityMarketMakerConfig,
)
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId, TraderId
from nautilus_trader.model.instruments import Instrument

trader_name = "OKX_BTCUSDT_TESTNET_001"
BASE_DIR: Path = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
from utils.instrument_loader import load_instrument

LOG_DIR = BASE_DIR / "log" / "sandbox" / trader_name

load_dotenv(BASE_DIR / "test.env")

api_key = os.getenv("OKX_API_KEY")
api_secret = os.getenv("OKX_API_SECRET")
api_passphrase: str | None = os.getenv("OKX_API_PASSPHRASE")

print(
    f"Using OKX Testnet API Key: {api_key}\n"
    f" Passphrase: {api_passphrase}\n"
    f" Secret: {api_secret}"
)


async def main():
    """
    Show how to run a strategy in a sandbox for the OKX venue.
    """
    # Configure the trading node
    config_node = TradingNodeConfig(
        trader_id=TraderId(trader_name.replace("_", "-")),
        logging=LoggingConfig(
            log_level="INFO",
            log_level_file="DEBUG",
            log_directory=str(LOG_DIR / "runtime"),
            log_colors=True,
            use_pyo3=True,
        ),
        exec_engine=LiveExecEngineConfig(
            reconciliation=True,
            # 这意味着节点启动时，会尝试将本地（Sandbox）的订单状态与交易所（或模拟交易所）的状态进行对比。
            reconciliation_lookback_mins=1440,
            filter_position_reports=True,
            # snapshot_orders=True,
            # snapshot_positions=True,
            # snapshot_positions_interval_secs=5.0,
        ),
        cache=CacheConfig(
            # database=DatabaseConfig(timeout=2),
            timestamps_as_iso8601=True,
            flush_on_start=False,
        ),
        # message_bus=MessageBusConfig(
        #     database=DatabaseConfig(timeout=2),
        #     encoding="json",
        #     timestamps_as_iso8601=True,
        #     streams_prefix="quoters",
        #     use_instance_id=False,
        #     # types_filter=[QuoteTick],
        #     autotrim_mins=30,
        #     heartbeat_interval_secs=1,
        # ),
        data_clients={
            OKX: OKXDataClientConfig(
                # base_url_http="https://www.okx.com",  # Override with custom endpoint
                base_url_ws="wss://wspap.okx.com:8443/ws/v5/public",  # Override with custom endpoint
                instrument_types=(OKXInstrumentType.SWAP,),
                instrument_provider=InstrumentProviderConfig(
                    load_all=False,  # 1. 关闭全量加载 (这一步是关键，否则会拉取所有合约)
                    load_ids=frozenset({"BTC-USDT-SWAP.OKX"}),
                ),
                contract_types=(OKXContractType.LINEAR,),
                is_demo=True,  # 现在是指明要访问 OKX 的 Testnet 也就是 Demo 环境
            ),
        },
        exec_clients={
            OKX: OKXExecClientConfig(
                # # 此处因为是 Testnet，所以账户的余额由 OKX Testnet 控制
                # # base_url_http="https://www.okx.com",  # Override with custom endpoint
                # base_url_ws="wss://wspap.okx.com:8443/ws/v5/private",  # Override with custom endpoint
                instrument_provider=InstrumentProviderConfig(
                    load_all=False,  # 1. 关闭全量加载 (这一步是关键，否则会拉取所有合约)
                    load_ids=frozenset({"BTC-USDT-SWAP.OKX"}),
                ),
                instrument_types=(OKXInstrumentType.SWAP,),
                contract_types=(OKXContractType.LINEAR,),  # 对冲或者单项持仓？
                is_demo=True,
            ),
        },
        timeout_connection=10.0,
        timeout_reconciliation=10.0,
        timeout_portfolio=10.0,
        timeout_disconnection=10.0,
        timeout_post_stop=5.0,
    )

    # Instantiate the node with a configuration
    node = TradingNode(config=config_node)

    # Configure your strategy
    strat_config = VolatilityMarketMakerConfig(
        instrument_id=InstrumentId.from_str("BTC-USDT-SWAP.OKX"),
        external_order_claims=[InstrumentId.from_str("BTC-USDT-SWAP.OKX")],
        bar_type=BarType.from_str("BTC-USDT-SWAP.OKX-1-MINUTE-LAST-EXTERNAL"),
        atr_period=20,
        atr_multiple=6.0,
        trade_size=Decimal("0.01"),  # 数量值小于 0.01 会报错，报出小数位舍弃错误
        # manage_gtd_expiry=True,
    )
    # Instantiate your strategy
    strategy = VolatilityMarketMaker(config=strat_config)

    # Add your strategies and modules
    node.trader.add_strategy(strategy)

    # Register your client factories with the node (can take user-defined factories)
    node.add_data_client_factory(OKX, OKXLiveDataClientFactory)
    node.add_exec_client_factory(OKX, OKXLiveExecClientFactory)
    node.build()

    # Load and register instrument from local file
    inst_id_str = "BTC-USDT-SWAP.OKX"
    venue_str = "OKX"
    inst_file = (
        BASE_DIR
        / "data"
        / "instruments"
        / venue_str
        / f"{inst_id_str.split('.')[0]}.json"
    )

    if inst_file.exists():
        print(f"📂 Loading instrument from {inst_file}")
        inst = load_instrument(inst_file)
        node.trader.add_instrument(inst)
    else:
        print(f"⚠️ Instrument file not found: {inst_file}")

    # 创建一个后台任务
    # monitor_task = asyncio.create_task(monitor_portfolio(node, interval_secs=20))

    try:
        await node.run_async()
    finally:
        # 退出时取消监控
        # monitor_task.cancel()

        # if node.trader:
        #     print("\n🛑 Sandbox 已停止，正在生成最终报告...")
        #     # 1. 打印账户报告 DataFrame
        #     print("📊 账户资金历史:")
        #     print(node.trader.generate_account_report(OKX_VENUE).tail())

        #     # 2. 打印成交记录
        #     print("📝 成交记录:")
        #     print(node.trader.generate_order_fills_report().tail())

        #     # 3. (可选) 导出为 CSV
        #     node.trader.generate_account_report(OKX_VENUE).to_csv(
        #         str(LOG_DIR / "account" / f"account_report_{datetime.now().isoformat()}.csv")
        #     )
        #     print("✅ 数据已保存到 sandbox_account.csv")

        await node.stop_async()
        await asyncio.sleep(1)
        node.dispose()


# Stop and dispose of the node with SIGINT/CTRL+C
if __name__ == "__main__":
    asyncio.run(main())
