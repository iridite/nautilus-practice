from decimal import Decimal
from pathlib import Path
from typing import Optional, Dict, Any
import csv

import joblib
import pandas as pd
import numpy as np
import ta

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

    # AI Filtering
    use_ai_filter: bool = False
    model_path: str = ""
    min_prob_threshold: float = 0.60

    # Data Recording (for Training/Debugging/Skew Analysis)
    record_features: bool = False
    record_path: str = "data/features_log.csv"

class MtfTrendPullbackStrategy(Strategy):
    def __init__(self, config: MtfTrendPullbackConfig):
        super().__init__(config)

        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        self.trend_bar_type = BarType.from_str(config.trend_bar_type)
        self.trade_bar_type = BarType.from_str(config.trade_bar_type)

        # Buffers for Feature Engineering
        self.lookback = 150
        self.trade_bars = []
        self.trend_bars = []

        # AI Model
        self.model = None
        if config.use_ai_filter and config.model_path:
            self.load_model(config.model_path)

        self.current_trend: int = 0

    def load_model(self, path: str):
        p = Path(path)
        if p.exists():
            try:
                self.model = joblib.load(p)
                self.log.info(f"🤖 AI Model loaded from {path}")
            except Exception as e:
                self.log.error(f"Failed to load AI model: {e}")
        else:
            self.log.warning(f"AI Model path not found: {path}")

    def on_start(self):
        self.subscribe_bars(self.trend_bar_type)
        self.subscribe_bars(self.trade_bar_type)
        self.log.info(f"Strategy Started on {self.instrument_id}")

    def on_bar(self, bar: Bar):
        # 1. Update Buffers with Dicts (faster than DF append every tick)
        row = {
            'datetime': pd.to_datetime(bar.ts_event, unit='ns'),
            'open': float(bar.open),
            'high': float(bar.high),
            'low': float(bar.low),
            'close': float(bar.close),
            'volume': float(bar.volume)
        }

        if bar.bar_type == self.trend_bar_type:
            self.trend_bars.append(row)
            if len(self.trend_bars) > self.lookback: self.trend_bars.pop(0)
            self._update_trend_state()

        elif bar.bar_type == self.trade_bar_type:
            self.trade_bars.append(row)
            if len(self.trade_bars) > self.lookback: self.trade_bars.pop(0)
            self._check_signal(bar)

    def _update_trend_state(self):
        if len(self.trend_bars) < self.config.ema_period:
            return

        # Optimization: Don't create full DF just for EMA if we can avoid it?
        # For simplicity and correctness with TA lib, we create DF.
        df = pd.DataFrame(self.trend_bars)
        ema = ta.trend.EMAIndicator(close=df['close'], window=self.config.ema_period).ema_indicator().iloc[-1]
        close = df['close'].iloc[-1]

        if close > ema:
            self.current_trend = 1
        elif close < ema:
            self.current_trend = -1
        else:
            self.current_trend = 0

    def _check_signal(self, bar: Bar):
        if len(self.trade_bars) < 50:
            return

        positions = self.cache.positions(instrument_id=self.instrument_id)
        current_pos = positions[0] if positions else None

        if current_pos and current_pos.quantity != 0:
            self._check_exit(bar, current_pos)
            return

        # Calculate RSI (Trade Trigger)
        df_trade = pd.DataFrame(self.trade_bars)
        rsi_val = ta.momentum.RSIIndicator(close=df_trade['close'], window=self.config.rsi_period).rsi().iloc[-1]

        signal = 0
        if self.current_trend == 1 and rsi_val < self.config.rsi_oversold:
            signal = 1
        elif self.current_trend == -1 and rsi_val > self.config.rsi_overbought:
            signal = -1

        if signal != 0:
            should_trade = True

            # AI Filter
            if self.config.use_ai_filter and self.model:
                should_trade = self._ask_ai_filter(signal)

            if should_trade:
                self._execute_trade(signal, bar.close)

    def _ask_ai_filter(self, signal: int) -> bool:
        try:
            df_trade = pd.DataFrame(self.trade_bars)
            df_trend = pd.DataFrame(self.trend_bars)

            if len(df_trend) < self.config.ema_period:
                return False

            # --- Feature Engineering (Must match DataProcessor exactly) ---
            # 1. Trend Features
            trend_ema = ta.trend.EMAIndicator(close=df_trend['close'], window=self.config.ema_period).ema_indicator()
            df_trend['trend_dir'] = np.where(df_trend['close'] > trend_ema, 1, -1)

            trend_adx = ta.trend.ADXIndicator(high=df_trend['high'], low=df_trend['low'], close=df_trend['close'], window=14).adx()

            # Context: Last CLOSED trend bar
            ctx_row = df_trend.iloc[-1]

            # 2. Trade Features
            rsi = ta.momentum.RSIIndicator(close=df_trade['close'], window=self.config.rsi_period).rsi()
            atr = ta.volatility.AverageTrueRange(high=df_trade['high'], low=df_trade['low'], close=df_trade['close'], window=14).average_true_range()
            vol_ma = df_trade['volume'].rolling(20).mean()
            trade_ema = ta.trend.EMAIndicator(close=df_trade['close'], window=self.config.ema_period).ema_indicator()
            bb = ta.volatility.BollingerBands(close=df_trade['close'], window=20, window_dev=2)

            curr = df_trade.iloc[-1]

            features = {
                'rsi': rsi.iloc[-1],
                'atr': atr.iloc[-1],
                'atr_pct': atr.iloc[-1] / curr['close'],
                'vol_ratio': curr['volume'] / vol_ma.iloc[-1] if (not pd.isna(vol_ma.iloc[-1]) and vol_ma.iloc[-1] != 0) else 1.0,
                'dist_to_ema': (curr['close'] - trade_ema.iloc[-1]) / trade_ema.iloc[-1] if (not pd.isna(trade_ema.iloc[-1]) and trade_ema.iloc[-1] != 0) else 0,
                'bb_width': (bb.bollinger_hband().iloc[-1] - bb.bollinger_lband().iloc[-1]) / bb.bollinger_mavg().iloc[-1] if (not pd.isna(bb.bollinger_mavg().iloc[-1]) and bb.bollinger_mavg().iloc[-1] != 0) else 0,

                'ctx_trend_dir': ctx_row['trend_dir'],
                'ctx_trend_adx': trend_adx.iloc[-1]
            }

            # Align cols with training
            model_cols = ['rsi', 'atr_pct', 'vol_ratio', 'dist_to_ema', 'bb_width', 'ctx_trend_dir', 'ctx_trend_adx']
            X_input = pd.DataFrame([features])[model_cols]

            # Handling NaNs
            X_input.fillna(0, inplace=True)

            prob = self.model.predict_proba(X_input)[0][1]

            is_pass = prob >= self.config.min_prob_threshold

            # Logging / Recording
            self.log.info(f"🤖 AI Prob: {prob:.4f} | Pass: {is_pass} | Sig: {signal}")

            if self.config.record_features:
                self._record_features(features, prob, signal, is_pass)

            return is_pass

        except Exception as e:
            self.log.error(f"AI Filter Error: {e}")
            return True

    def _record_features(self, features: Dict, prob: float, signal: int, accepted: bool):
        path = Path(self.config.record_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        row = features.copy()
        row['prob'] = prob
        row['signal'] = signal
        row['accepted'] = accepted
        row['timestamp'] = pd.Timestamp.now().isoformat()

        file_exists = path.exists()

        with open(path, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=row.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

    def _check_exit(self, bar: Bar, position: Position):
        entry_price = position.avg_px_open
        if position.side == OrderSide.BUY:
            pnl_pct = (bar.close - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - bar.close) / entry_price

        if pnl_pct < -self.config.stop_loss_pct:
            self.log.info(f"🛑 Stop Loss: {pnl_pct:.2%}")
            self.close_position(position)

    def _execute_trade(self, direction: int, price: Price):
        qty = self.calc_order_qty(price)
        if qty <= 0: return

        side = OrderSide.BUY if direction == 1 else OrderSide.SELL
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=side,
            quantity=qty,
            time_in_force=TimeInForce.IOC,
        )
        self.submit_order(order)
        self.log.info(f"🚀 SUBMIT {'BUY' if side == OrderSide.BUY else 'SELL'} {qty} @ {price}")

    def calc_order_qty(self, price: Price) -> Quantity:
        accounts = self.cache.accounts()
        if not accounts: return Quantity.from_int(0)
        account = accounts[0]
        instrument = self.cache.instrument(self.instrument_id)
        if not instrument: return Quantity.from_int(0)

        balance = account.balance(instrument.quote_currency)
        if not balance: return Quantity.from_int(0)

        equity = balance.total
        target_notional = equity * self.config.qty_percent

        if price == 0: return Quantity.from_int(0)
        raw_qty = target_notional / price

        try:
            return instrument.make_qty(raw_qty)
        except:
            return Quantity.from_int(0)
