#!/usr/bin/env python3
"""测试 BacktestEngine 是否会将 add_data 的数据路由到订阅者"""

import pandas as pd
from decimal import Decimal
from pathlib import Path

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.data import FundingRateUpdate
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.trading.strategy import Strategy
from nautilus_trader.model.data import DataType
from nautilus_trader.model.identifiers import ClientId


class TestStrategy(Strategy):
    def on_start(self):
        self.log.info("=== Strategy started ===")

        # 订阅 FundingRateUpdate
        funding_data_type = DataType(FundingRateUpdate)
        self.subscribe_data(
            funding_data_type,
            client_id=ClientId("BINANCE")
        )
        self.log.info("✅ Subscribed to FundingRateUpdate")

    def on_data(self, data):
        self.log.info(f"🔔 on_data called: {type(data).__name__}")
        if isinstance(data, FundingRateUpdate):
            self.log.info(f"💰 Received funding rate: {float(data.rate):.6f}")


def main():
    # 1. 创建引擎
    engine = BacktestEngine()

    # 2. 添加 venue
    engine.add_venue(
        venue=Venue("BINANCE"),
        oms_type="NETTING",
        account_type="MARGIN",
        base_currency=None,
        starting_balances=["1_000_000 USDT"],
    )

    # 3. 添加标的
    perp_instrument = TestInstrumentProvider.btcusdt_perp_binance()
    engine.add_instrument(perp_instrument)

    # 4. 添加策略
    strategy = TestStrategy()
    engine.add_strategy(strategy)

    # 5. 创建 FundingRateUpdate 数据
    funding_updates = []
    for i in range(5):
        funding_update = FundingRateUpdate(
            instrument_id=perp_instrument.id,
            rate=Decimal("0.0001"),
            next_funding_ns=i * 1_000_000_000,
            ts_event=i * 1_000_000_000,
            ts_init=i * 1_000_000_000,
        )
        funding_updates.append(funding_update)

    # 6. 使用 add_data 添加数据
    print("\n=== 使用 add_data 添加 5 个 FundingRateUpdate ===")
    engine.add_data(funding_updates, client_id=ClientId("BINANCE"))

    # 7. 运行回测
    print("\n=== 开始运行回测 ===")
    engine.run()

    print("\n=== 回测完成 ===")


if __name__ == "__main__":
    main()
