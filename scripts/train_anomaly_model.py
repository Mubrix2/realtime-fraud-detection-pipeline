# scripts/train_anomaly_model.py
"""
Train the Isolation Forest anomaly detection model.

Unlike XGBoost, this model is unsupervised — it learns what
"normal" looks like without ever seeing fraud labels.
It detects anything statistically unusual.

This catches novel fraud patterns that the supervised model misses.

Run after prepare_data.py:
    python scripts/train_anomaly_model.py
"""
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import classification_report, roc_auc_score

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.feature_engineer import engineer_features_batch, FEATURE_COLUMNS

PROCESSED_DIR = Path("data/processed")
MODELS_DIR = Path("app/models")


def load_legitimate_training_data():
    """
    Isolation Forest trains on LEGITIMATE transactions only.

    Why only legitimate?
    The model learns what normal looks like. If you include fraud in
    training, you teach it that fraud is normal — exactly the opposite
    of what you want.
    """
    print("Loading legitimate transactions for anomaly training...")

    # Load original raw data to filter legitimate only
    raw_path = Path("data/raw/paysim.csv")
    df = pd.read_csv(raw_path)

    # Keep only legitimate TRANSFER and CASH_OUT transactions
    df = df[
        (df["type"].isin(["TRANSFER", "CASH_OUT"])) &
        (df["isFraud"] == 0)
    ].copy()

    print(f"Legitimate transactions for training: {len(df):,}")

    X = engineer_features_batch(df)

    # Sample for speed — 200k legitimate transactions is enough
    # to learn normal patterns without taking 30 minutes to train
    if len(X) > 200000:
        X = X.sample(n=200000, random_state=42)
        print(f"Sampled to {len(X):,} for training speed")

    return X


def evaluate_anomaly_model(model, threshold):
    """
    Evaluate how well the anomaly model detects fraud
    on the held-out test set.

    Note: Isolation Forest will not match XGBoost precision
    because it has no fraud labels. We evaluate it to understand
    its false positive rate — how often it flags legitimate transactions.
    """
    print("\nEvaluating anomaly model on test set...")

    # Load test data
    X_test_raw = pd.read_csv(PROCESSED_DIR / "X_test_raw.csv")
    y_test = np.load(PROCESSED_DIR / "y_test.npy")

    # Load scaler used during data preparation
    scaler = joblib.load(MODELS_DIR / "scaler.pkl")
    X_test_scaled = scaler.transform(X_test_raw)

    # Isolation Forest returns scores (more negative = more anomalous)
    scores = model.score_samples(X_test_scaled)
    predictions = (scores < threshold).astype(int)

    print("\nAnomaly Detection Report:")
    print(classification_report(
        y_test, predictions,
        target_names=["Normal", "Anomalous"],
        digits=4,
    ))

    # False positive rate — important for business
    legitimate_flagged = predictions[y_test == 0].sum()
    total_legitimate = (y_test == 0).sum()
    fpr = legitimate_flagged / total_legitimate

    fraud_caught = predictions[y_test == 1].sum()
    total_fraud = y_test.sum()
    recall = fraud_caught / total_fraud

    print(f"Anomaly Recall:         {recall:.4f} ({recall*100:.1f}% of fraud flagged)")
    print(f"False Positive Rate:    {fpr:.4f} ({fpr*100:.2f}% of legit flagged)")
    print(
        f"\nNote: Isolation Forest catches {recall*100:.0f}% of fraud "
        f"but also flags {fpr*100:.1f}% of legitimate transactions."
    )
    print(
        "In production, BOTH models must agree (or either can flag) "
        "depending on your risk tolerance."
    )

    return {"recall": float(recall), "false_positive_rate": float(fpr)}


def train():
    X_train = load_legitimate_training_data()

    # Load scaler from Phase 2 — must use the same scaler
    scaler = joblib.load(MODELS_DIR / "scaler.pkl")
    X_train_scaled = scaler.transform(X_train)

    print("\nTraining Isolation Forest...")
    print("Parameters explained:")
    print("  n_estimators=200: number of isolation trees")
    print("  contamination=0.001: expected fraud rate (~0.1%)")
    print("  max_samples=256: samples per tree (paper recommendation)")
    print("  random_state=42: reproducibility")

    model = IsolationForest(
        n_estimators=200,
        # contamination: our estimate of what fraction of data is anomalous
        # PaySim fraud rate after filtering is ~0.3%
        # This tells Isolation Forest where to set its threshold
        contamination=0.003,
        # max_samples: number of samples drawn to train each tree
        # 256 is the recommendation from the original paper
        max_samples=256,
        random_state=42,
        n_jobs=-1,
        verbose=1,
    )

    model.fit(X_train_scaled)
    print("\nTraining complete")

    # The offset_ attribute gives the built-in threshold
    # We use this as our anomaly threshold
    threshold = model.offset_
    print(f"Anomaly threshold (model offset): {threshold:.6f}")

    # Evaluate
    metrics = evaluate_anomaly_model(model, threshold)

    # Save
    model_path = MODELS_DIR / "anomaly_model.pkl"
    joblib.dump(model, model_path)
    print(f"\nModel saved to {model_path}")

    import json
    metadata = {
        "model_type": "IsolationForest",
        "threshold": float(threshold),
        "n_estimators": 200,
        "contamination": 0.003,
        "metrics": metrics,
        "note": (
            "Trained on legitimate transactions only. "
            "Lower scores = more anomalous."
        ),
    }
    with open(MODELS_DIR / "anomaly_model_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print("✅ Isolation Forest anomaly model training complete")


if __name__ == "__main__":
    train()