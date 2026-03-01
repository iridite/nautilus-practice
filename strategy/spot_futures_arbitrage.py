"""
Delta 中性期现套利策略

核心逻辑:
1. 监控现货和合约价格基差
2. 基差年化 > 15% 时开仓 (做多现货 + 做空合约)
3. 确保 Delta 中性 (|spot_notional - perp_notional| / spot_notional < 0.5%)
4. 持仓期间收取资金费率
5. 基差收敛 / 时间到期 / 负资金费率时平仓
"""

from dataclasses import dataclass
from decimal import Decimal

from nautilus_trader.model.data import Bar, BarType, CustomData, DataType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument

from strategy.common.arbitrage import (
    ArbitragePairTracker,
    BasisCalculator,
    DeltaManager,
)
from strategy.core.base import BaseStrategy, BaseStrategyConfig
from utils.custom_data import FundingRateData


@dataclass
class PendingPair:
    """待配对订单数据结构"""

    spot_order_id: str
    perp_order_id: str
    submit_time: int
    spot_filled: bool = False
    perp_filled: bool = False


class SpotFuturesArbitrageConfig(BaseStrategyConfig):
    """期现套利策略配置"""

    # 标的配置
    venue: str = "BINANCE"
    spot_symbol: str = "BTCUSDT"
    perp_symbol: str = "BTCUSDT-PERP"
    timeframe: str = "1h"

    # 自动生成字段（由 Adapter 填充）
    instrument_id: str = ""  # 主标的（用于兼容 BaseStrategy）
    bar_type: str = ""

    # 开平仓阈值
    entry_basis_annual: float = 15.0
    exit_basis_annual: float = 5.0

    # Delta 中性参数
    delta_tolerance: float = 0.005

    # 仓位管理
    position_size_pct: float = 0.2
    max_positions: int = 3

    # 时间参数
    min_holding_days: int = 7
    max_holding_days: int = 90
    negative_funding_threshold: int = 3

    # 风控参数
    min_margin_ratio: float = 0.5
    emergency_margin_ratio: float = 0.3

    # 订单超时
    order_timeout_seconds: float = 5.0


class SpotFuturesArbitrageStrategy(BaseStrategy):
    """
    Delta 中性期现套利策略

    核心理念:
    - 做多现货 + 做空合约，构建 Delta 中性组合
    - 收取正资金费率收益
    - 基差收敛时平仓获利
    """

    def __init__(self, config: SpotFuturesArbitrageConfig):
        super().__init__(config)
        self.config = config

        # 初始化组件
        self.basis_calc = BasisCalculator()
        self.delta_mgr = DeltaManager()
        self.pair_tracker = ArbitragePairTracker(max_pairs=config.max_positions)

        # 标的
        self.spot_instrument: Instrument | None = None
        self.perp_instrument: Instrument | None = None

        # Bar 缓存
        self._latest_spot_bar: Bar | None = None
        self._latest_perp_bar: Bar | None = None
        self._bar_sync_tolerance_ns = 60_000_000_000  # 1 分钟容忍度

        # 订单跟踪
        self._pending_pairs: dict[str, PendingPair] = {}
        self._order_timeout_ns = int(config.order_timeout_seconds * 1_000_000_000)

    def on_start(self) -> None:
        """策略启动时初始化"""
        super().on_start()

        self.log.info(
            f"SpotFuturesArbitrage 启动: "
            f"spot={self.config.spot_symbol}, perp={self.config.perp_symbol}, "
            f"entry_threshold={self.config.entry_basis_annual}%, "
            f"exit_threshold={self.config.exit_basis_annual}%"
        )

        # 1. 构建标的 ID
        spot_instrument_id = InstrumentId.from_str(f"{self.config.spot_symbol}.{self.config.venue}")
        perp_instrument_id = InstrumentId.from_str(f"{self.config.perp_symbol}.{self.config.venue}")

        # 2. 从缓存加载标的
        self.spot_instrument = self.cache.instrument(spot_instrument_id)
        self.perp_instrument = self.cache.instrument(perp_instrument_id)

        if not self.spot_instrument or not self.perp_instrument:
            raise ValueError(f"Instruments not found: {spot_instrument_id}, {perp_instrument_id}")

        self.log.info(
            f"Instruments loaded: spot={self.spot_instrument.id}, perp={self.perp_instrument.id}"
        )

        # 3. 订阅 Bar 数据
        spot_bar_type = BarType.from_str(
            f"{spot_instrument_id}-{self.config.timeframe}-{self.config.price_type}-{self.config.origination}"
        )
        perp_bar_type = BarType.from_str(
            f"{perp_instrument_id}-{self.config.timeframe}-{self.config.price_type}-{self.config.origination}"
        )

        self.subscribe_bars(spot_bar_type)
        self.subscribe_bars(perp_bar_type)

        self.log.info(f"Subscribed to bars: spot={spot_bar_type}, perp={perp_bar_type}")

        # 4. 订阅资金费率数据
        funding_data_type = DataType(
            FundingRateData, metadata={"instrument_id": perp_instrument_id}
        )
        self.subscribe_data(funding_data_type)

        self.log.info(f"Subscribed to funding rate: {perp_instrument_id}")

    def on_bar(self, bar: Bar) -> None:
        """K线更新 - 需要区分现货和合约"""
        # 1. 识别 Bar 来源
        if bar.bar_type.instrument_id == self.spot_instrument.id:
            self._latest_spot_bar = bar
            self.log.debug(f"Spot bar updated: close={bar.close}")
        elif bar.bar_type.instrument_id == self.perp_instrument.id:
            self._latest_perp_bar = bar
            self.log.debug(f"Perp bar updated: close={bar.close}")
        else:
            return  # 忽略其他标的

        # 2. 检查是否两边都有数据
        if not self._latest_spot_bar or not self._latest_perp_bar:
            return

        # 3. 检查时间戳同步（容忍 1 分钟误差）
        time_diff = abs(self._latest_spot_bar.ts_event - self._latest_perp_bar.ts_event)
        if time_diff > self._bar_sync_tolerance_ns:
            self.log.warning(f"Bar timestamps not synced: diff={time_diff / 1e9:.1f}s")
            return

        # 4. 执行套利逻辑
        self._process_arbitrage_logic()

    def _process_arbitrage_logic(self) -> None:
        """处理套利逻辑（两边数据都就绪）"""
        spot_price = float(self._latest_spot_bar.close)
        perp_price = float(self._latest_perp_bar.close)

        # 计算基差
        try:
            basis = self.basis_calc.calculate_basis(spot_price, perp_price)
            annual_return = self.basis_calc.calculate_annual_return(
                basis, holding_days=self.config.min_holding_days
            )
        except ValueError as e:
            self.log.error(f"Basis calculation error: {e}")
            return

        self.log.debug(
            f"Basis: {basis:.4%}, Annual: {annual_return:.2f}%, "
            f"spot={spot_price:.2f}, perp={perp_price:.2f}"
        )

        # 检查开仓条件
        if self._check_entry_signal(spot_price, perp_price, annual_return):
            self._open_arbitrage_position(spot_price, perp_price, basis, annual_return)

        # 检查平仓条件
        for pair in self.pair_tracker.get_all_pairs():
            should_close, reason = self._check_exit_signal(
                pair.pair_id, spot_price, perp_price, annual_return
            )
            if should_close:
                self._close_arbitrage_position(pair.pair_id, reason)

        # 检查订单超时
        self._check_order_timeout()

    def _check_entry_signal(
        self, spot_price: float, perp_price: float, annual_return: float
    ) -> bool:
        """检查开仓信号"""
        # 1. 检查是否可以开新仓
        if not self.pair_tracker.can_open_new_pair():
            self.log.debug(f"Max positions reached: {self.config.max_positions}")
            return False

        # 2. 检查是否有待配对订单
        if self._pending_pairs:
            self.log.debug("Pending pairs exist, skipping entry")
            return False

        # 3. 检查基差是否满足开仓条件
        if not self.basis_calc.should_open_position(
            annual_return, threshold=self.config.entry_basis_annual
        ):
            return False

        self.log.info(
            f"✅ Entry signal: annual_return={annual_return:.2f}% > "
            f"threshold={self.config.entry_basis_annual}%"
        )
        return True

    def _check_exit_signal(
        self, pair_id: str, spot_price: float, perp_price: float, annual_return: float
    ) -> tuple[bool, str]:
        """检查平仓信号"""
        # 1. 基差收敛
        if self.basis_calc.should_close_position(
            annual_return, threshold=self.config.exit_basis_annual
        ):
            return True, f"basis_converged (annual={annual_return:.2f}%)"

        # 2. 时间触发
        should_close_time, time_reason = self.pair_tracker.should_close_by_time(
            pair_id,
            current_time=self._latest_perp_bar.ts_event,
            min_days=self.config.min_holding_days,
            max_days=self.config.max_holding_days,
        )
        if should_close_time:
            return True, time_reason

        # 3. 负资金费率
        if self.pair_tracker.should_close_by_funding(
            pair_id, threshold=self.config.negative_funding_threshold
        ):
            return (
                True,
                f"negative_funding_rate (count >= {self.config.negative_funding_threshold})",
            )

        return False, ""

    def _open_arbitrage_position(
        self, spot_price: float, perp_price: float, basis: float, annual_return: float
    ) -> None:
        """开仓 (双腿同时下单)"""
        # 1. 计算对冲比例
        hedge_ratio = self.delta_mgr.calculate_hedge_ratio(spot_price, perp_price)

        # 2. 计算数量
        account = self.portfolio.account(self.spot_instrument.id.venue)
        if not account:
            self.log.error("Account not found")
            return

        equity = account.balance_total(self.spot_instrument.quote_currency)
        if not equity or equity.as_decimal() <= 0:
            self.log.error("Equity not available")
            return

        equity_decimal = equity.as_decimal()
        spot_notional = equity_decimal * Decimal(str(self.config.position_size_pct))
        spot_qty = spot_notional / Decimal(str(spot_price))
        perp_qty = spot_qty * Decimal(str(hedge_ratio))

        # 3. 验证 Delta 中性
        spot_notional_actual = self.delta_mgr.calculate_notional(spot_qty, spot_price)
        perp_notional_actual = self.delta_mgr.calculate_notional(perp_qty, perp_price)

        if not self.delta_mgr.is_delta_neutral(
            spot_notional_actual, perp_notional_actual, self.config.delta_tolerance
        ):
            delta_ratio = self.delta_mgr.calculate_delta_ratio(
                spot_notional_actual, perp_notional_actual
            )
            self.log.warning(
                f"Delta not neutral: ratio={delta_ratio:.4%} > "
                f"tolerance={self.config.delta_tolerance:.4%}, skipping entry"
            )
            return

        # 4. 下单
        spot_order = self.order_factory.market(
            instrument_id=self.spot_instrument.id,
            order_side=OrderSide.BUY,
            quantity=self.spot_instrument.make_qty(spot_qty),
        )
        perp_order = self.order_factory.market(
            instrument_id=self.perp_instrument.id,
            order_side=OrderSide.SELL,
            quantity=self.perp_instrument.make_qty(perp_qty),
        )

        # 5. 记录待配对订单
        pair_id = f"pair_{self.clock.timestamp_ns()}"
        self._pending_pairs[pair_id] = PendingPair(
            spot_order_id=str(spot_order.client_order_id),
            perp_order_id=str(perp_order.client_order_id),
            submit_time=self.clock.timestamp_ns(),
        )

        # 6. 提交订单
        self.submit_order(spot_order)
        self.submit_order(perp_order)

        self.log.info(
            f"🚀 Opening arbitrage position: pair_id={pair_id}, "
            f"spot_qty={spot_qty:.4f}, perp_qty={perp_qty:.4f}, "
            f"basis={basis:.4%}, annual={annual_return:.2f}%, "
            f"delta_ratio={self.delta_mgr.calculate_delta_ratio(spot_notional_actual, perp_notional_actual):.4%}"
        )

    def _close_arbitrage_position(self, pair_id: str, reason: str) -> None:
        """平仓 (双腿同时下单)"""
        pair = self.pair_tracker.get_pair(pair_id)
        if not pair:
            self.log.error(f"Pair not found: {pair_id}")
            return

        # 1. 获取持仓
        spot_positions = [
            p
            for p in self.cache.positions_open(instrument_id=self.spot_instrument.id)
            if str(p.id) == pair.spot_position_id
        ]
        perp_positions = [
            p
            for p in self.cache.positions_open(instrument_id=self.perp_instrument.id)
            if str(p.id) == pair.perp_position_id
        ]

        if not spot_positions or not perp_positions:
            self.log.error(f"Positions not found for pair: {pair_id}")
            return

        spot_position = spot_positions[0]
        perp_position = perp_positions[0]

        # 2. 下单平仓
        spot_close_order = self.order_factory.market(
            instrument_id=self.spot_instrument.id,
            order_side=OrderSide.SELL,
            quantity=spot_position.quantity,
        )
        perp_close_order = self.order_factory.market(
            instrument_id=self.perp_instrument.id,
            order_side=OrderSide.BUY,
            quantity=perp_position.quantity,
        )

        self.submit_order(spot_close_order)
        self.submit_order(perp_close_order)

        # 3. 移除配对
        self.pair_tracker.unlink_pair(pair_id)

        holding_days = self.pair_tracker.get_holding_days(pair_id, self._latest_perp_bar.ts_event)

        self.log.info(
            f"📉 Closing arbitrage position: pair_id={pair_id}, "
            f"reason={reason}, holding_days={holding_days:.1f}, "
            f"funding_collected={pair.funding_rate_collected:.2f}"
        )

    def _check_order_timeout(self) -> None:
        """检查订单超时"""
        current_time = self.clock.timestamp_ns()
        timeout_pairs = []

        for pair_id, pending in self._pending_pairs.items():
            elapsed = current_time - pending.submit_time
            if elapsed > self._order_timeout_ns:
                timeout_pairs.append(pair_id)

        for pair_id in timeout_pairs:
            pending = self._pending_pairs.pop(pair_id)
            self._handle_partial_fill(pending)

    def _handle_partial_fill(self, pending: PendingPair) -> None:
        """处理单边成交失败"""
        if pending.spot_filled and not pending.perp_filled:
            # 现货成交但合约未成交，立即平掉现货
            self.log.error(
                "⚠️ Partial fill detected: spot filled, perp not filled. "
                "Emergency closing spot position."
            )
            self.close_all_positions(self.spot_instrument.id)

        elif pending.perp_filled and not pending.spot_filled:
            # 合约成交但现货未成交，立即平掉合约
            self.log.error(
                "⚠️ Partial fill detected: perp filled, spot not filled. "
                "Emergency closing perp position."
            )
            self.close_all_positions(self.perp_instrument.id)

        elif not pending.spot_filled and not pending.perp_filled:
            # 双边都未成交，超时
            self.log.warning(
                f"Order timeout: both sides not filled within {self.config.order_timeout_seconds}s"
            )

    def on_order_filled(self, event) -> None:
        """订单成交回调"""
        super().on_order_filled(event)

        # 查找对应的配对
        for pair_id, pending in list(self._pending_pairs.items()):
            if str(event.client_order_id) == pending.spot_order_id:
                pending.spot_filled = True
                self.log.debug(f"Spot order filled: {event.client_order_id}")
            elif str(event.client_order_id) == pending.perp_order_id:
                pending.perp_filled = True
                self.log.debug(f"Perp order filled: {event.client_order_id}")

            # 检查是否双边成交
            if pending.spot_filled and pending.perp_filled:
                self._on_pair_filled(pair_id, pending)
                del self._pending_pairs[pair_id]
                return

    def _on_pair_filled(self, pair_id: str, pending: PendingPair) -> None:
        """双边订单都成交"""
        # 查找新创建的持仓
        spot_positions = self.cache.positions_open(instrument_id=self.spot_instrument.id)
        perp_positions = self.cache.positions_open(instrument_id=self.perp_instrument.id)

        if not spot_positions or not perp_positions:
            self.log.error("Positions not found after order filled")
            return

        # 获取最新的持仓（假设是刚创建的）
        spot_position = spot_positions[-1]
        perp_position = perp_positions[-1]

        # 计算入场基差和年化收益率
        spot_price = float(self._latest_spot_bar.close)
        perp_price = float(self._latest_perp_bar.close)
        basis = self.basis_calc.calculate_basis(spot_price, perp_price)
        annual_return = self.basis_calc.calculate_annual_return(
            basis, holding_days=self.config.min_holding_days
        )

        # 关联持仓
        self.pair_tracker.link_positions(
            spot_position_id=str(spot_position.id),
            perp_position_id=str(perp_position.id),
            entry_basis=basis,
            entry_annual_return=annual_return,
            entry_time=self._latest_perp_bar.ts_event,
        )

        self.log.info(
            f"✅ Pair filled: pair_id={pair_id}, "
            f"spot_position={spot_position.id}, perp_position={perp_position.id}"
        )

    def on_data(self, data: CustomData) -> None:
        """处理自定义数据（如 Funding Rate）"""
        if isinstance(data, FundingRateData):
            self._handle_funding_rate(data)

    def _handle_funding_rate(self, data: FundingRateData) -> None:
        """处理资金费率结算"""
        for pair in self.pair_tracker.get_all_pairs():
            # 获取合约持仓
            perp_positions = [
                p
                for p in self.cache.positions_open(instrument_id=self.perp_instrument.id)
                if str(p.id) == pair.perp_position_id
            ]

            if not perp_positions:
                continue

            perp_position = perp_positions[0]

            # 计算资金费率收益（做空合约收取正资金费率）
            # 注意：做空时 quantity 为负，所以需要取绝对值
            funding_pnl = abs(perp_position.quantity.as_decimal()) * data.funding_rate

            # 更新持仓
            self.pair_tracker.update_funding_rate(pair.pair_id, funding_pnl)

            # 检查负资金费率
            if data.funding_rate < 0:
                self.pair_tracker.increment_negative_funding(pair.pair_id)
            else:
                self.pair_tracker.reset_negative_funding(pair.pair_id)

            self.log.info(
                f"💰 Funding rate settled: pair={pair.pair_id}, "
                f"rate={data.funding_rate:.4%}, annual={data.funding_rate_annual:.2f}%, "
                f"pnl={funding_pnl:.2f}, total_collected={pair.funding_rate_collected:.2f}"
            )

    def on_stop(self) -> None:
        """策略停止"""
        # 输出最终统计
        total_pairs = len(self.pair_tracker.get_all_pairs())
        total_funding = sum(p.funding_rate_collected for p in self.pair_tracker.get_all_pairs())

        self.log.info(
            f"\n{'=' * 60}\n"
            f"SpotFuturesArbitrage Strategy Stopped\n"
            f"{'=' * 60}\n"
            f"Total active pairs: {total_pairs}\n"
            f"Total funding collected: {total_funding:.2f} USDT\n"
            f"{'=' * 60}"
        )

        # 取消订阅
        if self.spot_instrument and self.perp_instrument:
            spot_bar_type = BarType.from_str(
                f"{self.spot_instrument.id}-{self.config.timeframe}-{self.config.price_type}-{self.config.origination}"
            )
            perp_bar_type = BarType.from_str(
                f"{self.perp_instrument.id}-{self.config.timeframe}-{self.config.price_type}-{self.config.origination}"
            )

            self.unsubscribe_bars(spot_bar_type)
            self.unsubscribe_bars(perp_bar_type)

            funding_data_type = DataType(
                FundingRateData, metadata={"instrument_id": self.perp_instrument.id}
            )
            self.unsubscribe_data(funding_data_type)
