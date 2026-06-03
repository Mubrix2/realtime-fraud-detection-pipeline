# scripts/evaluate_models.py
"""
Combined evaluation of fraud classifier + anomaly detector.

Shows three scenarios:
1. XGBoost only
2. Isolation Forest only
3. Combined (flag if EITHER model flags) — maximum recall
4. Combined (flag if BOTH models flag) — maximum precision

Run after training both models:
    python scripts/evaluate_models.py
"""
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, f1_score

sys.path.append(str(Path(__file__).resolve().parent.parent))

PROCESSED_DIR = Path("data/processed")
MODELS_DIR = Path("app/models")


def evaluate():
    import json

    # Load models
    fraud_model = joblib.load(MODELS_DIR / "fraud_model.pkl")
    anomaly_model = joblib.load(MODELS_DIR / "anomaly_model.pkl")
    scaler = joblib.load(MODELS_DIR / "scaler.pkl")

    # Load metadata for thresholds
    with open(MODELS_DIR / "fraud_model_metadata.json") as f:
        fraud_meta = json.load(f)
    with open(MODELS_DIR / "anomaly_model_metadata.json") as f:
        anomaly_meta = json.load(f)

    fraud_threshold = fraud_meta["threshold"]
    anomaly_threshold = anomaly_meta["threshold"]

    # Load test data
    X_test_scaled = np.load(PROCESSED_DIR / "X_test.npy")
    y_test = np.load(PROCESSED_DIR / "y_test.npy")
    X_test_raw = pd.read_csv(PROCESSED_DIR / "X_test_raw.csv")
    X_test_anomaly = scaler.transform(X_test_raw)

    # Predictions from each model
    fraud_probs = fraud_model.predict_proba(X_test_scaled)[:, 1]
    fraud_preds = (fraud_probs >= fraud_threshold).astype(int)

    anomaly_scores = anomaly_model.score_samples(X_test_anomaly)
    anomaly_preds = (anomaly_scores < anomaly_threshold).astype(int)

    # Combined strategies
    either_flags = np.logical_or(fraud_preds, anomaly_preds).astype(int)
    both_flag = np.logical_and(fraud_preds, anomaly_preds).astype(int)

    scenarios = {
        "XGBoost Only": fraud_preds,
        "Isolation Forest Only": anomaly_preds,
        "Either Flags (Max Recall)": either_flags,
        "Both Flag (Max Precision)": both_flag,
    }

    print("="*65)
    print("COMBINED MODEL EVALUATION REPORT")
    print("="*65)

    for name, preds in scenarios.items():
        print(f"\n{'─'*65}")
        print(f"Strategy: {name}")
        print(classification_report(
            y_test, preds,
            target_names=["Legitimate", "Fraud"],
            digits=4,
        ))

    print("\n" + "="*65)
    print("RECOMMENDATION FOR PRODUCTION")
    print("="*65)
    print(
        "\nUse 'Either Flags' for maximum fraud protection "
        "(higher false positive rate)"
    )
    print(
        "Use 'XGBoost Only' for customer experience priority "
        "(fewer false alarms)"
    )
    print(
        "Use 'Both Flag' for manual review queue "
        "(highest confidence fraud only)"
    )


if __name__ == "__main__":
    evaluate()