import pandas as pd
import numpy as np
import ta
from pathlib import Path
from typing import Tuple, Optional
import sys

# Add project root to sys.path to allow importing config
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import current_config

class DataProcessor:
    """
    Handles data loading, feature engineering, and labeling for the
    MTF Trend Pullback strategy AI filter.
    """
    def __init__(self,
                 ema_period: Optional[int] = None,
                 rsi_period: Optional[int] = None,
                 rsi_oversold: Optional[int] = None,
                 rsi_overbought: Optional[int] = None,
                 stop_loss_pct: Optional[float] = None,
                 take_profit_pct: Optional[float] = None,
                 horizon_bars: Optional[int] = None
                 ):
        # Read defaults from settings.py
        ml_cfg = current_config.ml

        self.ema_period = ema_period if ema_period is not None else ml_cfg.ema_period
        self.rsi_period = rsi_period if rsi_period is not None else ml_cfg.rsi_period
        self.rsi_oversold = rsi_oversold if rsi_oversold is not None else ml_cfg.rsi_oversold
        self.rsi_overbought = rsi_overbought if rsi_overbought is not None else ml_cfg.rsi_overbought
        self.sl_pct = stop_loss_pct if stop_loss_pct is not None else ml_cfg.stop_loss_pct
        self.tp_pct = take_profit_pct if take_profit_pct is not None else ml_cfg.take_profit_pct
        self.horizon_bars = horizon_bars if horizon_bars is not None else ml_cfg.horizon_bars

    def load_data(self, file_path: str) -> pd.DataFrame:
        """
        Load CSV data fetched by utils/data_retrival.py
        """
        if not Path(file_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        df = pd.read_csv(file_path)

        # Standardize Datetime Index
        if 'datetime' in df.columns:
            df['datetime'] = pd.to_datetime(df['datetime'])
            df.set_index('datetime', inplace=True)
        elif 'timestamp' in df.columns:
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('datetime', inplace=True)

        df.sort_index(inplace=True)

        # Ensure we have OHLCV columns in lowercase
        df.columns = [c.lower() for c in df.columns]
        return df

    def add_features(self, df_trade: pd.DataFrame, df_trend: pd.DataFrame) -> pd.DataFrame:
        """
        Feature Engineering:
        1. Calculate indicators on Trend Data (1H)
        2. Calculate indicators on Trade Data (5m)
        3. Merge Trend context into Trade Data
        """

        # --- 1. Process Trend Data (High Timeframe, e.g., 1H) ---
        # Calculate EMA
        trend_ema = ta.trend.EMAIndicator(close=df_trend['close'], window=self.ema_period)
        df_trend['trend_ema'] = trend_ema.ema_indicator()

        # Trend Direction (1: Bull, -1: Bear)
        df_trend['trend_dir'] = np.where(df_trend['close'] > df_trend['trend_ema'], 1, -1)

        # Trend Strength (ADX)
        trend_adx = ta.trend.ADXIndicator(high=df_trend['high'], low=df_trend['low'], close=df_trend['close'], window=14)
        df_trend['trend_adx'] = trend_adx.adx()

        # Shift trend data by 1 to represent "closed candle" state available at the start of the next period
        # This prevents lookahead bias when merging with lower timeframe
        df_trend_shifted = df_trend.shift(1).copy()

        # Select columns to merge
        trend_cols = ['trend_dir', 'trend_adx', 'trend_ema', 'close']
        trend_feats = df_trend_shifted[trend_cols].rename(columns=lambda x: f"ctx_{x}")

        # --- 2. Process Trade Data (Low Timeframe, e.g., 5m) ---
        # RSI
        rsi_ind = ta.momentum.RSIIndicator(close=df_trade['close'], window=self.rsi_period)
        df_trade['rsi'] = rsi_ind.rsi()

        # ATR (Volatility)
        atr_ind = ta.volatility.AverageTrueRange(high=df_trade['high'], low=df_trade['low'], close=df_trade['close'], window=14)
        df_trade['atr'] = atr_ind.average_true_range()
        df_trade['atr_pct'] = df_trade['atr'] / df_trade['close'] # Normalized volatility

        # Relative Volume
        df_trade['vol_ma'] = df_trade['volume'].rolling(20).mean()
        df_trade['vol_ratio'] = df_trade['volume'] / df_trade['vol_ma']

        # Distance to Short Term EMA
        trade_ema = ta.trend.EMAIndicator(close=df_trade['close'], window=self.ema_period)
        df_trade['trade_ema'] = trade_ema.ema_indicator()
        df_trade['dist_to_ema'] = (df_trade['close'] - df_trade['trade_ema']) / df_trade['trade_ema']

        # Bollinger Bands Width (Squeeze)
        bb = ta.volatility.BollingerBands(close=df_trade['close'], window=20, window_dev=2)
        df_trade['bb_width'] = (bb.bollinger_hband() - bb.bollinger_lband()) / bb.bollinger_mavg()

        # --- 3. Merge Trend Context ---
        # Reindex the trend data to match trade data timestamps (Forward Fill)
        # This aligns the last closed 1H candle to all 5m candles within the next hour
        trend_reindexed = trend_feats.reindex(df_trade.index, method='ffill')

        df_final = pd.concat([df_trade, trend_reindexed], axis=1)

        # Drop initial NaNs
        df_final.dropna(inplace=True)

        return df_final

    def generate_labels(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate labels for the ML model.
        The model only needs to learn to filter signals generated by the base strategy.

        Label 1: Trade was profitable (hit TP before SL)
        Label 0: Trade failed (hit SL before TP, or timed out)
        """

        # 1. Identify Strategy Signals
        df['signal'] = 0

        # Long Signal: Bullish Trend + RSI Oversold
        long_cond = (df['ctx_trend_dir'] == 1) & (df['rsi'] < self.rsi_oversold)
        df.loc[long_cond, 'signal'] = 1

        # Short Signal: Bearish Trend + RSI Overbought
        short_cond = (df['ctx_trend_dir'] == -1) & (df['rsi'] > self.rsi_overbought)
        df.loc[short_cond, 'signal'] = -1

        # 2. Labeling Logic (Triple Barrier)
        df['target'] = np.nan
        df['ret_result'] = np.nan # For analysis: actual return

        # Convert to numpy for speed
        closes = df['close'].values
        highs = df['high'].values
        lows = df['low'].values
        signals = df['signal'].values

        targets = np.full(len(df), np.nan)

        # Indices where signal is present
        # We assume we enter at the CLOSE of the bar where signal is generated (simplification)
        # or OPEN of next bar. Here using CLOSE of signal bar as entry price.
        indices = np.where(signals != 0)[0]

        for i in indices:
            direction = signals[i]
            entry_price = closes[i]

            # Define Barriers
            if direction == 1: # Long
                sl_price = entry_price * (1 - self.sl_pct)
                tp_price = entry_price * (1 + self.tp_pct)
            else: # Short
                sl_price = entry_price * (1 + self.sl_pct)
                tp_price = entry_price * (1 - self.tp_pct)

            # Future Window
            end_idx = min(i + self.horizon_bars, len(df))
            if end_idx <= i + 1:
                continue

            future_highs = highs[i+1 : end_idx]
            future_lows = lows[i+1 : end_idx]

            outcome = 0 # Default fail

            if direction == 1:
                # Check when Price hits SL or TP
                # Ideally we check minute by minute, but here we check bar by bar

                # Arrays of booleans
                hit_sl = future_lows <= sl_price
                hit_tp = future_highs >= tp_price

                # Find first index
                idx_sl = np.argmax(hit_sl) if np.any(hit_sl) else 99999
                idx_tp = np.argmax(hit_tp) if np.any(hit_tp) else 99999

                if idx_tp < idx_sl:
                    outcome = 1

            else: # Short
                hit_sl = future_highs >= sl_price
                hit_tp = future_lows <= tp_price

                idx_sl = np.argmax(hit_sl) if np.any(hit_sl) else 99999
                idx_tp = np.argmax(hit_tp) if np.any(hit_tp) else 99999

                if idx_tp < idx_sl:
                    outcome = 1

            targets[i] = outcome

        df['target'] = targets
        return df

    def process(self, trade_csv: str, trend_csv: str) -> pd.DataFrame:
        """
        Execute full pipeline and return clean dataset for training
        """
        print(f"📖 Loading Trade Data: {trade_csv}")
        df_trade = self.load_data(trade_csv)

        print(f"📖 Loading Trend Data: {trend_csv}")
        df_trend = self.load_data(trend_csv)

        print("⚙️  Engineering Features...")
        df_feat = self.add_features(df_trade, df_trend)

        print("🏷️  Generating Labels...")
        df_labeled = self.generate_labels(df_feat)

        # Return only rows with signals
        df_final = df_labeled[df_labeled['signal'] != 0].copy()
        df_final.dropna(subset=['target'], inplace=True)

        print(f"✅ Processing Complete. Generated {len(df_final)} samples from signals.")
        return df_final
