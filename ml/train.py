import argparse
import sys
from pathlib import Path

import joblib
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import classification_report, roc_auc_score, confusion_matrix

# Add project root to sys.path to allow importing local modules
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from ml.data_processor import DataProcessor

# Configuration
DATA_DIR = BASE_DIR / "data" / "raw"
MODEL_DIR = BASE_DIR / "data" / "models"


def train_model(trade_file: str, trend_file: str):
    """
    Train a LightGBM model to filter strategy signals.
    """
    # Ensure model directory exists
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Initialize Processor
    # Configuration is loaded from config/settings.py
    processor = DataProcessor()

    print(f"🔄 Processing data...")
    print(f"   Trade Layer: {trade_file}")
    print(f"   Trend Layer: {trend_file}")

    trade_path = DATA_DIR / trade_file
    trend_path = DATA_DIR / trend_file

    # 2. Load & Process Data
    try:
        df = processor.process(str(trade_path), str(trend_path))
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        return

    if df.empty:
        print("❌ No signals generated from the data. Cannot train.")
        return

    # 3. Select Features
    # Filter out non-feature columns (prices, timestamps, labels)
    exclude_cols = [
        'open', 'high', 'low', 'close', 'volume', 'datetime', 'timestamp', # Raw OHLCV
        'signal', 'target', 'ret_result',                     # Labels
        'trade_ema', 'trend_ema', 'ctx_trend_ema',            # Raw indicators (use normalized versions instead)
        'ctx_close',                                          # Raw context price
        'vol_ma', 'atr'                                       # Absolute values (not generalizable)
    ]

    feature_cols = [c for c in df.columns if c not in exclude_cols]

    X = df[feature_cols]
    y = df['target']

    print(f"\n📊 Feature Set ({len(feature_cols)}): {feature_cols}")
    print(f"🔢 Total Signal Samples: {len(X)}")
    print(f"🎯 Class Balance (Win Rate): {y.mean():.2%}")

    # 4. Time-Series Split
    # Strict chronological split to prevent data leakage
    split_idx = int(len(X) * 0.80)

    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    print(f"✂️  Training Set: {len(X_train)} | Test Set: {len(X_test)}")

    # 5. Train LightGBM Classifier
    print("\n🚀 Training LightGBM Model...")

    # Parameters optimized for tabular data with noise
    model = lgb.LGBMClassifier(
        n_estimators=1000,
        learning_rate=0.03,
        max_depth=4,
        num_leaves=20,
        subsample=0.8,
        colsample_bytree=0.8,
        objective='binary',
        metric='auc',
        random_state=42,
        class_weight='balanced', # Important for imbalanced datasets
        verbose=-1
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        eval_metric='auc',
        callbacks=[
            lgb.early_stopping(stopping_rounds=50),
            lgb.log_evaluation(period=100)
        ]
    )

    # 6. Evaluation
    print("\n🔍 Model Evaluation (Test Set):")
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    print("\nClassification Report:")
    print(classification_report(y_test, y_pred))

    auc = roc_auc_score(y_test, y_prob)
    print(f"🏆 ROC-AUC Score: {auc:.4f}")

    # Confusion Matrix
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
    print(f"\nConfusion Matrix:")
    print(f"True Negatives (Filtered Loss): {tn}")
    print(f"False Positives (Bad Trades Taken): {fp}")
    print(f"False Negatives (Missed Wins): {fn}")
    print(f"True Positives (Winning Trades): {tp}")

    # 7. Save Model
    model_name = "lgbm_mtf_v1.joblib"
    save_path = MODEL_DIR / model_name
    joblib.dump(model, save_path)
    print(f"\n💾 Model saved to: {save_path}")

    # 8. Feature Importance
    importance = pd.DataFrame({
        'feature': feature_cols,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)

    print("\n🌟 Top 10 Important Features:")
    print(importance.head(10).to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train ML Filter for Strategy")
    parser.add_argument("--trade", type=str, required=True, help="Filename of 5m data (e.g., binance-ETHUSDT-5m.csv)")
    parser.add_argument("--trend", type=str, required=True, help="Filename of 1h data (e.g., binance-ETHUSDT-1h.csv)")

    args = parser.parse_args()

    train_model(args.trade, args.trend)
