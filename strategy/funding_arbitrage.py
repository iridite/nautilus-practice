"""
Delta 中性资金费率套利策略 (Funding Rate Arbitrage)

核心逻辑:
1. 从传入的永续合约 (PERP) 推导出现货标的 (SPOT)
2. 监控基差 (perp_price - spot_price) / spot_price
3. 基差 > entry_basis_pct 且资金费率年化 > min_funding_rate_annual 时开仓
4. 做多现货 + 做空合约，构建 Delta 中性组合
5. 持仓期间收取资金费率
6. 基差收敛 / 时间到期 / 负资金费率时平仓
"""

from dataclasses import dataclass
from decimal import Decimal

from nautilus_trader.model.data import Bar, BarType, CustomData, DataType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ClientId, InstrumentId
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


class FundingArbitrageConfig(BaseStrategyConfig):
    """资金费率套利策略配置"""

    # 核心参数
    entry_basis_pct: float = 0.005  # 开仓基差阈值 (0.5%)
    exit_basis_pct: float = 0.001  # 平仓基差阈值 (0.1%)
    min_funding_rate_annual: float = 15.0  # 最小要求年化资金费率 (%)

    # Delta 中性参数
    delta_tolerance: float = 0.005  # Delta 容忍度 (0.5%)

    # 仓位管理
    max_position_risk_pct: float = 0.4  # 最大仓位占比 (40%)
    max_positions: int = 3  # 最大同时持仓数

    # 时间参数
    min_holding_days: int = 7  # 最小持有期（天）
    max_holding_days: int = 90  # 最大持有期（天）
    negative_funding_threshold: int = 3  # 连续负资金费率次数阈值

    # 风控参数
    min_margin_ratio: float = 0.5  # 最小保证金率（50%）
    emergency_margin_ratio: float = 0.3  # 紧急保证金率（30%）

    # 订单超时
    order_timeout_seconds: float = 5.0  # 订单超时时间（秒）


class FundingArbitrageStrategy(BaseStrategy):
    """
    Delta 中性资金费率套利策略

    核心理念:
    - 从传入的永续合约 (PERP) 自动推导现货标的 (SPOT)
    - 做多现货 + 做空合约，构建 Delta 中性组合
    - 收取正资金费率收益
    - 基差收敛时平仓获利
    """

    def __init__(self, config: FundingArbitrageConfig):
        super().__init__(config)

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

        # 资金费率缓存
        self._latest_funding_rate_annual: float = 0.0

    def on_start(self) -> None:
        """策略启动时初始化 - 暗度陈仓推导现货标的"""
        super().on_start()

        # 1. 获取传入的永续合约标的
        self.perp_instrument = self.instrument
        if not self.perp_instrument:
            self.log.error("❌ CRITICAL: No instrument provided to strategy")
            return

        self.log.info(f"📊 Perp instrument loaded: {self.perp_instrument.id}")

        # 2. 暗度陈仓：从 PERP 推导 SPOT
        perp_id_str = str(self.perp_instrument.id)
        if "-PERP" not in perp_id_str:
            # 如果不是 PERP 标的,说明这是为 SPOT 标的创建的策略实例
            # 资金费率套利策略只需要一个实例(PERP),SPOT 实例应该跳过
            self.log.info(
                f"⏭️  Skipping strategy initialization for non-PERP instrument: {perp_id_str}. "
                f"This strategy only runs on PERP instruments."
            )
            return

        # 推导现货 ID: BTCUSDT-PERP.BINANCE -> BTCUSDT.BINANCE
        spot_id_str = perp_id_str.replace("-PERP", "")
        spot_instrument_id = InstrumentId.from_str(spot_id_str)

        # 3. 从缓存加载现货标的
        self.spot_instrument = self.cache.instrument(spot_instrument_id)
        if not self.spot_instrument:
            self.log.error(
                f"❌ CRITICAL: Spot instrument not found in cache: {spot_id_str}. "
                f"Please ensure spot data is loaded before starting strategy."
            )
            return

        self.log.info(f"✅ Spot instrument derived: {self.spot_instrument.id}")

        # 4. 订阅 Bar 数据
        # 从配置的 bar_type 中提取时间周期、价格类型和数据来源
        # bar_type 格式: BTCUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL
        perp_bar_type_str = self.config.bar_type
        # 提取 bar_type 的后半部分: 1-HOUR-LAST-EXTERNAL
        bar_spec = "-".join(perp_bar_type_str.split("-")[2:])  # 跳过 instrument_id 部分

        # 构造 SPOT 的 bar_type
        spot_bar_type = BarType.from_str(f"{self.spot_instrument.id}-{bar_spec}")
        perp_bar_type = BarType.from_str(perp_bar_type_str)

        # 保存 bar_type 供 on_stop() 使用
        self.spot_bar_type = spot_bar_type
        self.perp_bar_type = perp_bar_type

        self.subscribe_bars(spot_bar_type)
        self.subscribe_bars(perp_bar_type)

        self.log.info(f"📈 Subscribed to bars: spot={spot_bar_type}, perp={perp_bar_type}")

        # 5. 订阅资金费率数据
        funding_data_type = DataType(
            FundingRateData, metadata={"instrument_id": self.perp_instrument.id}
        )
        self.subscribe_data(data_type=funding_data_type, client_id=ClientId("BINANCE"))

        self.log.info(f"💰 Subscribed to funding rate: {self.perp_instrument.id}")

        # 6. 输出策略参数
        self.log.info(
            f"\n{'=' * 60}\n"
            f"FundingArbitrage Strategy Started\n"
            f"{'=' * 60}\n"
            f"Spot: {self.spot_instrument.id}\n"
            f"Perp: {self.perp_instrument.id}\n"
            f"Entry Basis: {self.config.entry_basis_pct:.2%}\n"
            f"Exit Basis: {self.config.exit_basis_pct:.2%}\n"
            f"Min Funding Rate (Annual): {self.config.min_funding_rate_annual:.2f}%\n"
            f"Max Position Risk: {self.config.max_position_risk_pct:.1%}\n"
            f"Delta Tolerance: {self.config.delta_tolerance:.2%}\n"
            f"{'=' * 60}"
        )

    def on_bar(self, bar: Bar) -> None:
        """K线更新 - 需要区分现货和合约"""
        if not self.spot_instrument or not self.perp_instrument:
            return

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
            basis_pct = basis  # basis 本身就是百分比形式
        except ValueError as e:
            self.log.error(f"Basis calculation error: {e}")
            return

        self.log.debug(
            f"Basis: {basis_pct:.4%}, Funding(Annual): {self._latest_funding_rate_annual:.2f}%, "
            f"spot={spot_price:.2f}, perp={perp_price:.2f}"
        )

        # 检查开仓条件
        if self._check_entry_signal(spot_price, perp_price, basis_pct):
            self._open_arbitrage_position(spot_price, perp_price, basis_pct)

        # 检查平仓条件
        for pair in self.pair_tracker.get_all_pairs():
            should_close, reason = self._check_exit_signal(
                pair.pair_id, spot_price, perp_price, basis_pct
            )
            if should_close:
                self._close_arbitrage_position(pair.pair_id, reason)

        # 检查订单超时
        self._check_order_timeout()

    def _check_entry_signal(self, spot_price: float, perp_price: float, basis_pct: float) -> bool:
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
        if basis_pct < self.config.entry_basis_pct:
            return False

        # 4. 检查资金费率是否满足最小要求
        if self._latest_funding_rate_annual < self.config.min_funding_rate_annual:
            self.log.debug(
                f"Funding rate too low: {self._latest_funding_rate_annual:.2f}% < "
                f"{self.config.min_funding_rate_annual:.2f}%"
            )
            return False

        self.log.info(
            f"✅ Entry signal: basis={basis_pct:.4%} > {self.config.entry_basis_pct:.4%}, "
            f"funding_annual={self._latest_funding_rate_annual:.2f}% > "
            f"{self.config.min_funding_rate_annual:.2f}%"
        )
        return True

    def _check_exit_signal(
        self, pair_id: str, spot_price: float, perp_price: float, basis_pct: float
    ) -> tuple[bool, str]:
        """检查平仓信号"""
        # 1. 基差收敛
        if basis_pct < self.config.exit_basis_pct:
            return True, f"basis_converged (basis={basis_pct:.4%})"

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
        self, spot_price: float, perp_price: float, basis_pct: float
    ) -> None:
        """开仓 (双腿同时下单) - 严格 Delta 中性"""
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
        spot_notional = equity_decimal * Decimal(str(self.config.max_position_risk_pct))
        spot_qty_raw = spot_notional / Decimal(str(spot_price))
        perp_qty_raw = spot_qty_raw * Decimal(str(hedge_ratio))

        # 3. 精度对齐 - 使用 make_qty() 确保符合交易所规则
        spot_qty = self.spot_instrument.make_qty(spot_qty_raw)
        perp_qty = self.perp_instrument.make_qty(perp_qty_raw)

        # 4. 验证 Delta 中性
        spot_notional_actual = self.delta_mgr.calculate_notional(spot_qty.as_decimal(), spot_price)
        perp_notional_actual = self.delta_mgr.calculate_notional(perp_qty.as_decimal(), perp_price)

        if not self.delta_mgr.is_delta_neutral(
            spot_notional_actual, perp_notional_actual, self.config.delta_tolerance
        ):
            delta_ratio = self.delta_mgr.calculate_delta_ratio(
                spot_notional_actual, perp_notional_actual
            )
            self.log.warning(
                f"⚠️ Delta not neutral: ratio={delta_ratio:.4%} > "
                f"tolerance={self.config.delta_tolerance:.4%}, skipping entry"
            )
            return

        # 5. 下单
        spot_order = self.order_factory.market(
            instrument_id=self.spot_instrument.id,
            order_side=OrderSide.BUY,
            quantity=spot_qty,
        )
        perp_order = self.order_factory.market(
            instrument_id=self.perp_instrument.id,
            order_side=OrderSide.SELL,
            quantity=perp_qty,
        )

        # 6. 记录待配对订单
        pair_id = f"pair_{self.clock.timestamp_ns()}"
        self._pending_pairs[pair_id] = PendingPair(
            spot_order_id=str(spot_order.client_order_id),
            perp_order_id=str(perp_order.client_order_id),
            submit_time=self.clock.timestamp_ns(),
        )

        # 7. 提交订单
        self.submit_order(spot_order)
        self.submit_order(perp_order)

        delta_ratio = self.delta_mgr.calculate_delta_ratio(
            spot_notional_actual, perp_notional_actual
        )

        self.log.info(
            f"🚀 Opening arbitrage position:\n"
            f"  Pair ID: {pair_id}\n"
            f"  Spot: BUY {spot_qty} @ {spot_price:.2f} (notional={spot_notional_actual:.2f})\n"
            f"  Perp: SELL {perp_qty} @ {perp_price:.2f} (notional={perp_notional_actual:.2f})\n"
            f"  Basis: {basis_pct:.4%}\n"
            f"  Funding (Annual): {self._latest_funding_rate_annual:.2f}%\n"
            f"  Delta Ratio: {delta_ratio:.4%}"
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
            f"📉 Closing arbitrage position:\n"
            f"  Pair ID: {pair_id}\n"
            f"  Reason: {reason}\n"
            f"  Holding Days: {holding_days:.1f}\n"
            f"  Funding Collected: {pair.funding_rate_collected:.2f} USDT"
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
        """处理单边成交失败 - 紧急平仓"""
        if pending.spot_filled and not pending.perp_filled:
            # 现货成交但合约未成交，立即平掉现货
            self.log.error(
                "⚠️ CRITICAL: Partial fill detected - spot filled, perp not filled. "
                "Emergency closing spot position to avoid directional risk."
            )
            self.close_all_positions(self.spot_instrument.id)

        elif pending.perp_filled and not pending.spot_filled:
            # 合约成交但现货未成交，立即平掉合约
            self.log.error(
                "⚠️ CRITICAL: Partial fill detected - perp filled, spot not filled. "
                "Emergency closing perp position to avoid directional risk."
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

        # 计算入场基差
        spot_price = float(self._latest_spot_bar.close)
        perp_price = float(self._latest_perp_bar.close)
        basis = self.basis_calc.calculate_basis(spot_price, perp_price)

        # 关联持仓
        self.pair_tracker.link_positions(
            spot_position_id=str(spot_position.id),
            perp_position_id=str(perp_position.id),
            entry_basis=basis,
            entry_annual_return=self._latest_funding_rate_annual,
            entry_time=self._latest_perp_bar.ts_event,
        )

        self.log.info(
            f"✅ Pair filled successfully:\n"
            f"  Pair ID: {pair_id}\n"
            f"  Spot Position: {spot_position.id}\n"
            f"  Perp Position: {perp_position.id}\n"
            f"  Entry Basis: {basis:.4%}\n"
            f"  Entry Funding (Annual): {self._latest_funding_rate_annual:.2f}%"
        )

    def on_data(self, data: CustomData) -> None:
        """处理自定义数据（如 Funding Rate）"""
        if isinstance(data, FundingRateData):
            self._handle_funding_rate(data)

    def _handle_funding_rate(self, data: FundingRateData) -> None:
        """处理资金费率结算"""
        # 更新缓存的资金费率
        self._latest_funding_rate_annual = data.funding_rate_annual

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
                f"💰 Funding rate settled:\n"
                f"  Pair: {pair.pair_id}\n"
                f"  Rate: {data.funding_rate:.4%}\n"
                f"  Annual: {data.funding_rate_annual:.2f}%\n"
                f"  PNL: {funding_pnl:.2f} USDT\n"
                f"  Total Collected: {pair.funding_rate_collected:.2f} USDT"
            )

    def on_stop(self) -> None:
        """策略停止"""
        # 输出最终统计
        total_pairs = len(self.pair_tracker.get_all_pairs())
        total_funding = sum(p.funding_rate_collected for p in self.pair_tracker.get_all_pairs())

        self.log.info(
            f"\n{'=' * 60}\n"
            f"FundingArbitrage Strategy Stopped\n"
            f"{'=' * 60}\n"
            f"Total active pairs: {total_pairs}\n"
            f"Total funding collected: {total_funding:.2f} USDT\n"
            f"{'=' * 60}"
        )

        # 取消订阅
        if self.spot_instrument and self.perp_instrument:
            # 使用保存的 bar_type
            if hasattr(self, "spot_bar_type") and hasattr(self, "perp_bar_type"):
                self.unsubscribe_bars(self.spot_bar_type)
                self.unsubscribe_bars(self.perp_bar_type)

                funding_data_type = DataType(
                    FundingRateData, metadata={"instrument_id": self.perp_instrument.id}
                )
                self.unsubscribe_data(data_type=funding_data_type, client_id=ClientId("BINANCE"))
