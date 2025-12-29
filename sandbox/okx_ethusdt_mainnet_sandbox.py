from datetime import datetime
import os
from dotenv import load_dotenv
from nautilus_trader.core.nautilus_pyo3 import OKXInstrumentType
from nautilus_trader.model.identifiers import InstrumentId

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
from decimal import Decimal
from pathlib import Path

from nautilus_trader.adapters.okx import OKX
from nautilus_trader.adapters.okx import OKX_VENUE
from nautilus_trader.adapters.binance import BinanceAccountType
from nautilus_trader.adapters.okx import OKXDataClientConfig
from nautilus_trader.adapters.okx.factories import OKXLiveDataClientFactory
from nautilus_trader.adapters.sandbox.config import SandboxExecutionClientConfig
from nautilus_trader.adapters.sandbox.factory import SandboxLiveExecClientFactory
from nautilus_trader.config import CacheConfig
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.config import LiveExecEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.examples.strategies.volatility_market_maker import VolatilityMarketMaker
from nautilus_trader.examples.strategies.volatility_market_maker import VolatilityMarketMakerConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import TraderId


# *** THIS IS A TEST STRATEGY WITH NO ALPHA ADVANTAGE WHATSOEVER. ***
# *** IT IS NOT INTENDED TO BE USED TO TRADE LIVE WITH REAL MONEY. ***

trader_name = "OKX_ETHUSDT_MAINNET_001"
BASE_DIR: Path = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "log" / "sandbox" / trader_name

load_dotenv(BASE_DIR / "live.env")

# 1. 定义一个监控协程
async def monitor_portfolio(node: TradingNode, interval_secs: int = 5):
    print(f"👀 启动 PnL 监控 (每 {interval_secs} 秒刷新)...")
    
    while True:
        try:
            await asyncio.sleep(interval_secs)
            
            if not node.cache:
                continue

            accounts = node.cache.accounts()
            
            target_account = None
            for acc in accounts:
                if str(acc.id).startswith("OKX"): 
                    target_account = acc
                    break
            
            if target_account:
                # 1. 获取 Money 对象并转 float
                # balance_total() 是方法，调用后转 float
                total_val = float(target_account.balance_total())
                free_val = float(target_account.balance_free())
                
                positions = node.cache.positions()
                
                # 2. 计算总浮盈 (修正版)
                # 错误原因修正：
                # (1) start=None 改为 start=0.0 (因为我们要累加数字)
                # (2) p.unrealized_pnl 改为 p.unrealized_pnl() (它是方法，要加括号)
                # (3) 显式 float() 转换 Money 对象
                total_upnl_val = sum((float(p.unrealized_pnl()) for p in positions), start=0.0)
                
                # 打印状态
                print(f"💰 [Monitor] 权益: {total_val:,.2f} U | 浮盈: {total_upnl_val:+,.2f} U | 可用: {free_val:,.2f} | 持仓数: {len(positions)}")
                
                # 打印具体持仓
                for pos in positions:
                    # 同样，这里也要加括号并转 float
                    upnl_val = float(pos.unrealized_pnl())
                    qty = pos.quantity # quantity 通常是属性，不用括号
                    print(f"   👉 持仓: {pos.instrument_id} | 数量: {qty} | 方向: {pos.side} | 浮盈: {upnl_val:+,.2f}")
            
        except asyncio.CancelledError:
            print("👋 监控任务已停止")
            break
        except Exception as e:
            # 打印详细堆栈，防止因为属性名不对猜来猜去
            import traceback
            print(f"⚠️ 监控报错: {e}")
            # traceback.print_exc()

async def main():
    """
    Show how to run a strategy in a sandbox for the OKX venue.
    """
    # Configure the trading node
    config_node = TradingNodeConfig(
        trader_id=TraderId(""),
        logging=LoggingConfig(
            log_level="INFO",
            log_level_file="DEBUG",
            log_file_format="json",
            log_directory= str(LOG_DIR / "runtime"),
            log_colors=True,
            use_pyo3=True,
        ),
        exec_engine=LiveExecEngineConfig(
            reconciliation=False,
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
                api_key=os.getenv("OKX_API_KEY"),  # 'OKX_API_KEY' env var
                api_secret=os.getenv("OKX_API_SECRET"),  # 'OKX_API_SECRET' env var
                api_passphrase=os.getenv("OKX_API_PASSPHRASE"),  # 'OKX_API_PASSPHRASE' env var
                # base_url_http="https://www.okx.com",  # Override with custom endpoint
                # base_url_ws="wss://ws.okx.com:8443/ws/v5/public",  # Override with custom endpoint
                instrument_types=(OKXInstrumentType.SWAP,),
                instrument_provider=InstrumentProviderConfig(
                    load_all=False,  # 1. 关闭全量加载 (这一步是关键，否则会拉取所有合约)
                    load_ids=frozenset({"ETH-USDT-SWAP.OKX"})
                ),
                is_demo=False # 我们使用 live data 只是下面的 execution client 是纯 sandbox
            ),
        },
        exec_clients={ 
            OKX: SandboxExecutionClientConfig(
                venue=str(OKX_VENUE),
                starting_balances=["1_000 USDT"],
                base_currency="USDT",
            ),
        },
        timeout_connection=30.0,
        timeout_reconciliation=10.0,
        timeout_portfolio=10.0,
        timeout_disconnection=10.0,
        timeout_post_stop=5.0,
    )

    # Instantiate the node with a configuration
    node = TradingNode(config=config_node)

    # Configure your strategy
    strat_config = VolatilityMarketMakerConfig(
        instrument_id=InstrumentId.from_str("ETH-USDT-SWAP.OKX"),
        external_order_claims=[InstrumentId.from_str("ETH-USDT-SWAP.OKX")],
        bar_type=BarType.from_str("ETH-USDT-SWAP.OKX-1-MINUTE-LAST-EXTERNAL"),
        atr_period=20,
        atr_multiple=6.0,
        trade_size=Decimal("0.010"),
        # manage_gtd_expiry=True,
    )
    # Instantiate your strategy
    strategy = VolatilityMarketMaker(config=strat_config)

    # Add your strategies and modules
    node.trader.add_strategy(strategy)

    # Register your client factories with the node (can take user-defined factories)
    node.add_data_client_factory(OKX, OKXLiveDataClientFactory)
    node.add_exec_client_factory(OKX, SandboxLiveExecClientFactory)
    node.build()

    # 创建一个后台任务
    monitor_task = asyncio.create_task(monitor_portfolio(node, interval_secs=20))

    try:
        await node.run_async()
    finally:
        # 退出时取消监控
        monitor_task.cancel() 

        if node.trader:
            print("\n🛑 Sandbox 已停止，正在生成最终报告...")
            # 1. 打印账户报告 DataFrame
            print("📊 账户资金历史:")
            print(node.trader.generate_account_report(OKX_VENUE).tail())
            
            # 2. 打印成交记录
            print("📝 成交记录:")
            print(node.trader.generate_order_fills_report().tail())

            # 3. (可选) 导出为 CSV
            node.trader.generate_account_report(OKX_VENUE).to_csv(
                str(LOG_DIR / "account" / f"account_report_{datetime.now().isoformat()}.csv")
            )
            print("✅ 数据已保存到 sandbox_account.csv")
        
        await node.stop_async()
        await asyncio.sleep(1)
        node.dispose()


# Stop and dispose of the node with SIGINT/CTRL+C
if __name__ == "__main__":
    asyncio.run(main())