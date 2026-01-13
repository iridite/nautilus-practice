import csv
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

# Third-party imports
import joblib
import numpy as np
import pandas as pd
import ta

# Nautilus imports
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.position import Position
from nautilus_trader.trading.strategy import Strategy


class MtfTrendPullbackConfig(StrategyConfig):
    instrument_id: str
    trend_bar_type: str
    trade_bar_type: str

    # Strategy Params
    ema_period: int = 50
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70

    # Risk Management
    qty_percent: Decimal = Decimal("0.1")
    stop_loss_pct: Decimal = Decimal("0.02")
    leverage: Optional[int] = None

    # AI Filtering
    use_ai_filter: bool = False
    model_path: str = ""
    min_prob_threshold: float = 0.60

    # Data Recording
    record_features: bool = False
    record_path: str = "data/record/features_log.csv"


class MtfTrendPullbackStrategy(Strategy):
    def __init__(self, config: MtfTrendPullbackConfig):
        super().__init__(config)

        # Handle both str (high-level/config) and Object (low-level direct) types
        # TODO: improved and unify this multi-typed obj in further
        if isinstance(config.instrument_id, InstrumentId):
            self.instrument_id = config.instrument_id
        else:
            self.instrument_id = InstrumentId.from_str(config.instrument_id)

        if isinstance(config.trend_bar_type, BarType):
            self.trend_bar_type = config.trend_bar_type
        else:
            self.trend_bar_type = BarType.from_str(config.trend_bar_type)

        if isinstance(config.trade_bar_type, BarType):
            self.trade_bar_type = config.trade_bar_type
        else:
            self.trade_bar_type = BarType.from_str(config.trade_bar_type)

        # Buffers: Keep enough history for indicators to stabilize
        # EMA 50 needs decent history. 150 is 3x period, usually safe.
        self.lookback = 150
        self.trade_bars: List[Dict] = []
        self.trend_bars: List[Dict] = []

        # State
        self.model = None
        self.current_trend: int = 0  # 0: Neutral, 1: Bull, -1: Bear

        if config.use_ai_filter and config.model_path:
            self._load_model(config.model_path)

    def _load_model(self, path: str):
        p = Path(path)
        if p.exists():
            try:
                self.model = joblib.load(p)
                self.log.info(f"🤖 AI Model successfully loaded from {path}")
            except Exception as e:
                self.log.error(f"❌ Failed to load AI model from {path}: {e}")
                # Fallback: Disable AI filter if load fails to prevent crash during trading?
                # Or keep it enabled but fail open/closed?
                # Here we'll just log error, and _ask_ai_filter will check if self.model is None.
        else:
            self.log.warning(
                f"⚠️ AI Model path not found: {path}. Strategy will run without AI filter (or fail if logic depends on it)."
            )

    def on_start(self):
        """
        Subscribe to data feeds.
        """
        self.subscribe_bars(self.trend_bar_type)
        self.subscribe_bars(self.trade_bar_type)
        self.log.info(f"🟢 Strategy Started on {self.instrument_id}")
        self.log.info(f"   Trend Layer: {self.trend_bar_type}")
        self.log.info(f"   Trade Layer: {self.trade_bar_type}")

    def on_stop(self):
        self.log.info(f"🔴 Strategy Stopped on {self.instrument_id}")
        self.close_all_positions(self.instrument_id)

    def on_bar(self, bar: Bar):
        """
        Handle incoming bars.
        """
        try:
            # 1. Convert Bar to Dict for DataFrame construction
            # Using dicts is slightly faster for appending than creating single-row DFs repeatedly
            row = {
                "datetime": pd.to_datetime(bar.ts_event, unit="ns"),
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": float(bar.volume),
            }

            # 2. Route based on BarType
            # Processing method is the same, this strategy keep's two private bars list for further analysising
            if bar.bar_type == self.trend_bar_type:
                self.trend_bars.append(row)
                if len(self.trend_bars) > self.lookback:
                    self.trend_bars.pop(0)

                self._update_trend_state()

            elif bar.bar_type == self.trade_bar_type:
                self.trade_bars.append(row)
                if len(self.trade_bars) > self.lookback:
                    self.trade_bars.pop(0)

                self._check_signal_logic(bar)  # only trade on trade bars

        except Exception as e:
            self.log.error(f"🔥 Error in on_bar processing: {e}", exc_info=True)

    def _update_trend_state(self):
        """
        Calculate trend direction based on Higher Timeframe EMA.
        """
        if len(self.trend_bars) < self.config.ema_period:
            return

        try:
            df = pd.DataFrame(self.trend_bars)
            # EMA Calculation
            ema_series = ta.trend.EMAIndicator(
                close=df["close"], window=self.config.ema_period
            ).ema_indicator()

            # Check if we have valid EMA value
            current_ema = ema_series.iloc[-1]
            current_close = df["close"].iloc[-1]

            if pd.isna(current_ema):
                return

            if current_close > current_ema:
                self.current_trend = 1
            elif current_close < current_ema:
                self.current_trend = -1
            else:
                self.current_trend = 0

        except Exception as e:
            self.log.error(f"Error calculating trend state: {e}")

    def _check_signal_logic(self, bar: Bar):
        """
        Main trading logic on 5m bars.
        """
        # 1. Warmup Check
        if len(self.trade_bars) < 50 or len(self.trend_bars) < self.config.ema_period:
            return

        # 2. Position Management
        positions = self.cache.positions(instrument_id=self.instrument_id)
        current_pos = positions[0] if positions else None

        if current_pos and current_pos.quantity != 0:
            self._check_exit_logic(bar, current_pos)
            return

        # 3. Entry Logic
        try:
            df_trade = pd.DataFrame(self.trade_bars)
            rsi_series = ta.momentum.RSIIndicator(
                close=df_trade["close"], window=self.config.rsi_period
            ).rsi()
            rsi_val = rsi_series.iloc[-1]

            if pd.isna(rsi_val):
                return

            signal = 0
            # Long Setup: Uptrend + RSI Oversold
            if self.current_trend == 1 and rsi_val < self.config.rsi_oversold:
                signal = 1
            # Short Setup: Downtrend + RSI Overbought
            elif self.current_trend == -1 and rsi_val > self.config.rsi_overbought:
                signal = -1

            if signal != 0:
                self.log.info(
                    f"💡 CTA Signal Generated: {'LONG' if signal == 1 else 'SHORT'} (RSI: {rsi_val:.2f})"
                )

                # 4. AI Filter
                should_trade = True
                if self.config.use_ai_filter:
                    if self.model:
                        should_trade = self._ask_ai_filter(signal)
                    else:
                        self.log.warning(
                            "AI Filter enabled but model not loaded. Skipping trade for safety."
                        )
                        should_trade = False

                if should_trade:
                    self._execute_trade(signal, bar.close)
                else:
                    self.log.info("✋ Trade Filtered by AI")

        except Exception as e:
            self.log.error(f"Error checking signals: {e}")

    def _ask_ai_filter(self, signal: int) -> bool:
        """
        Run inference using the loaded LightGBM model.
        """
        try:
            df_trade = pd.DataFrame(self.trade_bars)
            df_trend = pd.DataFrame(self.trend_bars)

            # --- Feature Engineering (Must match train.py exactly) ---

            # Trend Context
            trend_ema = ta.trend.EMAIndicator(
                close=df_trend["close"], window=self.config.ema_period
            ).ema_indicator()
            df_trend["trend_dir"] = np.where(df_trend["close"] > trend_ema, 1, -1)
            trend_adx = ta.trend.ADXIndicator(
                high=df_trend["high"],
                low=df_trend["low"],
                close=df_trend["close"],
                window=14,
            ).adx()

            # Trade Indicators
            rsi = ta.momentum.RSIIndicator(
                close=df_trade["close"], window=self.config.rsi_period
            ).rsi()
            atr = ta.volatility.AverageTrueRange(
                high=df_trade["high"],
                low=df_trade["low"],
                close=df_trade["close"],
                window=14,
            ).average_true_range()
            vol_ma = df_trade["volume"].rolling(20).mean()
            trade_ema = ta.trend.EMAIndicator(
                close=df_trade["close"], window=self.config.ema_period
            ).ema_indicator()
            bb = ta.volatility.BollingerBands(
                close=df_trade["close"], window=20, window_dev=2
            )

            # Get latest values
            curr_trade = df_trade.iloc[-1]
            ctx_trend = df_trend.iloc[-1]  # Last available trend bar

            # Handle division by zero or NaNs safely
            def safe_div(a, b, default=0.0):
                if pd.isna(b) or b == 0:
                    return default
                return a / b

            # Feature Vector construction
            features = {
                "rsi": rsi.iloc[-1],
                "atr_pct": safe_div(atr.iloc[-1], curr_trade["close"]),
                "vol_ratio": safe_div(curr_trade["volume"], vol_ma.iloc[-1], 1.0),
                "dist_to_ema": safe_div(
                    (curr_trade["close"] - trade_ema.iloc[-1]), trade_ema.iloc[-1]
                ),
                "bb_width": safe_div(
                    (bb.bollinger_hband().iloc[-1] - bb.bollinger_lband().iloc[-1]),
                    bb.bollinger_mavg().iloc[-1],
                ),
                "ctx_trend_dir": ctx_trend["trend_dir"],
                "ctx_trend_adx": trend_adx.iloc[-1],
            }

            # Prepare Input DataFrame
            # IMPORTANT: Column order must match training
            model_cols = [
                "rsi",
                "atr_pct",
                "vol_ratio",
                "dist_to_ema",
                "bb_width",
                "ctx_trend_dir",
                "ctx_trend_adx",
            ]
            X_input = pd.DataFrame([features])[model_cols]

            # Fill NaNs (LightGBM handles them, but clean input is better)
            X_input.fillna(0, inplace=True)

            # Inference
            prob = self.model.predict_proba(X_input)[0][1]
            is_pass = prob >= self.config.min_prob_threshold

            self.log.info(
                f"🤖 AI Inference | Prob: {prob:.4f} | Threshold: {self.config.min_prob_threshold} | Accepted: {is_pass}"
            )

            if self.config.record_features:
                self._record_features(features, prob, signal, is_pass)

            return is_pass

        except Exception as e:
            self.log.error(f"❌ AI Filter Inference Error: {e}", exc_info=True)
            # Fail closed (don't trade if AI breaks) or fail open?
            # Usually fail closed is safer for "High Win Rate" strategy.
            return False

    def _record_features(
        self, features: Dict, prob: float, signal: int, accepted: bool
    ):
        try:
            path = Path(self.config.record_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            row = features.copy()
            row["prob"] = prob
            row["signal"] = signal
            row["accepted"] = accepted
            row["timestamp"] = pd.Timestamp.now().isoformat()

            file_exists = path.exists()

            with open(path, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=row.keys())
                if not file_exists:
                    writer.writeheader()
                writer.writerow(row)
        except Exception as e:
            self.log.error(f"Failed to record features: {e}")

    def _check_exit_logic(self, bar: Bar, position: Position):
        """
        Stop Loss and Take Profit monitoring (if not handled by OMS orders).
        Note: Ideally use Bracket Orders or StopMarket orders, but manual monitoring works for basic logic.
        """
        try:
            entry_price = position.avg_px_open
            current_price = bar.close

            pnl_pct = 0
            if position.side == OrderSide.BUY:
                pnl_pct = (current_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - current_price) / entry_price

            # Stop Loss
            if pnl_pct < -self.config.stop_loss_pct:
                self.log.info(f"🛑 Stop Loss Triggered: PnL {pnl_pct:.2%}")
                self.close_position(position)

            # Optional: We could also implement simple Take Profit here if needed
            # e.g., if pnl_pct > 0.05: close

        except Exception as e:
            self.log.error(f"Error in exit logic: {e}")

    def _execute_trade(self, direction: int, price: Price):
        """
        Execute Market Order.
        """
        try:
            qty = self.calc_order_qty(price)
            if qty <= 0:
                return

            side = OrderSide.BUY if direction == 1 else OrderSide.SELL

            order = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=side,
                quantity=qty,
                time_in_force=TimeInForce.IOC,
            )

            self.submit_order(order)
            self.log.info(f"🚀 SUBMIT ORDER: {side} {qty} @ {price}")

        except Exception as e:
            self.log.error(f"Error executing trade: {e}")

    def recommend_leverage(self) -> Optional[int]:
        """
        策略可以重写此方法以提供推荐的杠杆倍数。
        优先级：recommend_leverage() > config.leverage
        """
        return None

    def calc_order_qty(self, price: Price) -> Quantity:
        """
        Calculate Position Size based on Equity Percentage and Leverage.
        """
        try:
            accounts = self.cache.accounts()
            if not accounts:
                self.log.error("No accounts found in cache")
                return Quantity.from_int(0)

            account = accounts[0]
            instrument = self.cache.instrument(self.instrument_id)
            if not instrument:
                self.log.error("Instrument not found in cache")
                return Quantity.from_int(0)

            balance = account.balance(instrument.quote_currency)
            if not balance:
                self.log.error(f"No balance found for {instrument.quote_currency}")
                return Quantity.from_int(0)

            # 1. Bankruptcy Check (Total Equity)
            if balance.total <= 0:
                self.log.warning(f"🛑 Account Bankrupt! Equity: {balance.total}")
                return Quantity.from_int(0)

            # 2. Margin Check (Free Balance)
            if balance.free <= 0:
                self.log.warning(
                    f"🛑 Insufficient Margin! Free Balance: {balance.free}"
                )
                return Quantity.from_int(0)

            # 3. Determine Leverage
            # Priority: Strategy Recommended > Config Set > Default(1)
            rec_leverage = self.recommend_leverage()
            leverage = (
                rec_leverage if rec_leverage is not None else self.config.leverage
            )
            leverage = leverage if leverage is not None else 1

            # 4. Cap by Instrument Maximum Leverage (if available from exchange data)
            if hasattr(instrument, "max_leverage") and instrument.max_leverage:
                if leverage > instrument.max_leverage:
                    self.log.warning(
                        f"⚠️ Requested leverage {leverage} exceeds instrument max "
                        f"{instrument.max_leverage}. Capping to limit."
                    )
                    leverage = instrument.max_leverage

            equity = balance.total
            # Target Notional = Equity * Percentage * Leverage
            target_notional = equity * self.config.qty_percent * leverage

            if price == 0:
                return Quantity.from_int(0)

            raw_qty = target_notional / price

            try:
                return instrument.make_qty(raw_qty)
            except AttributeError:
                # Fallback if method missing (unlikely in newer versions)
                return Quantity.from_int(0)

        except Exception as e:
            self.log.error(f"Error calculating quantity: {e}")
            return Quantity.from_int(0)
