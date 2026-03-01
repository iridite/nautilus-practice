"""
自定义 DataClient 用于在回测中发布 FundingRateUpdate 数据
"""

from nautilus_trader.backtest.data_client import BacktestDataClient
from nautilus_trader.model.data import FundingRateUpdate


class FundingRateDataClient(BacktestDataClient):
    """
    专门用于回测中发布 FundingRateUpdate 数据的 DataClient

    BacktestDataClient 会在回测引擎运行时自动回放数据并触发订阅者的回调
    """

    def __init__(self, client_id, msgbus, cache, clock):
        super().__init__(
            client_id=client_id,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
        )

    def _handle_data(self, data):
        """
        处理数据回放 - BacktestEngine 会调用此方法
        我们需要将数据发布到 MessageBus
        """
        if isinstance(data, FundingRateUpdate):
            # 发布到 MessageBus，这样订阅者就能收到
            self._msgbus.publish(
                topic=f"data.funding_rate.{data.instrument_id}",
                msg=data,
            )
