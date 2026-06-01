# scripts/prepare_data.py
"""
Prepare the PaySim dataset for model training.

Steps:
1. Load raw data
2. Filter to fraud-relevant transaction types (TRANSFER and CASH_OUT)
3. Engineer features
4. Handle class imbalance with SMOTE
5. Save train/test splits

Run once before training:
    python scripts/prepare_data.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import joblib

# Allow imports from project root
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.feature_engineer import engineer_features_batch, FEATURE_COLUMNS

RAW_DATA_PATH = Path("data/raw/paysim.csv")
PROCESSED_DIR = Path("data/processed")
MODELS_DIR = Path("app/models")

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def prepare():
    print("Loading raw data...")
    df = pd.read_csv(RAW_DATA_PATH)
    print(f"Loaded {len(df):,} transactions")
    print(f"Fraud rate: {df['isFraud'].mean()*100:.3f}%")

    # ── Step 1: Filter to fraud-relevant types ─────────────────────────────
    # Fraud ONLY occurs in TRANSFER and CASH_OUT.
    # Including other types (PAYMENT, CASH_IN, DEBIT) adds noise
    # and makes the model learn irrelevant patterns.
    print("\nFiltering to TRANSFER and CASH_OUT transactions...")
    df = df[df["type"].isin(["TRANSFER", "CASH_OUT"])].copy()
    print(f"After filter: {len(df):,} transactions")
    print(f"Fraud rate after filter: {df['isFraud'].mean()*100:.3f}%")

    # ── Step 2: Engineer features ──────────────────────────────────────────
    print("\nEngineering features...")
    X = engineer_features_batch(df)
    y = df["isFraud"].values
    print(f"Feature matrix shape: {X.shape}")
    print(f"Features: {list(X.columns)}")

    # ── Step 3: Train/test split ───────────────────────────────────────────
    # stratify=y ensures both splits have the same fraud rate.
    # Without stratify, random chance could put all fraud in train
    # and leave test with no fraud examples.
    print("\nSplitting data...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )
    print(f"Train: {len(X_train):,} | Test: {len(X_test):,}")
    print(f"Train fraud rate: {y_train.mean()*100:.3f}%")

    # ── Step 4: Scale features ─────────────────────────────────────────────
    # XGBoost does not strictly require scaling (it uses tree splits).
    # But the Isolation Forest anomaly detector benefits from scaling
    # because it uses distance-based calculations.
    # We scale once and save the scaler for use in production.
    print("\nScaling features...")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Save the scaler — production must use the SAME scaler as training
    scaler_path = MODELS_DIR / "scaler.pkl"
    joblib.dump(scaler, scaler_path)
    print(f"Scaler saved to {scaler_path}")

    # ── Step 5: Handle class imbalance with SMOTE ──────────────────────────
    # SMOTE (Synthetic Minority Over-sampling TEchnique) creates new
    # synthetic fraud examples by interpolating between existing ones.
    # This is better than simple duplication because it adds variety.
    #
    # We apply SMOTE only to training data — NEVER to test data.
    # Test data must reflect real-world distribution to give honest metrics.
    print("\nApplying SMOTE to training data...")
    print(f"Before SMOTE — fraud: {y_train.sum():,}, legit: {(y_train==0).sum():,}")

    smote = SMOTE(random_state=42, k_neighbors=5)
    X_train_resampled, y_train_resampled = smote.fit_resample(
        X_train_scaled, y_train
    )

    print(
        f"After SMOTE  — fraud: {y_train_resampled.sum():,}, "
        f"legit: {(y_train_resampled==0).sum():,}"
    )

    # ── Step 6: Save processed data ───────────────────────────────────────
    print("\nSaving processed data...")

    np.save(PROCESSED_DIR / "X_train.npy", X_train_resampled)
    np.save(PROCESSED_DIR / "y_train.npy", y_train_resampled)
    np.save(PROCESSED_DIR / "X_test.npy", X_test_scaled)
    np.save(PROCESSED_DIR / "y_test.npy", y_test)

    # Also save unscaled test data for the anomaly detector
    X_test.to_csv(PROCESSED_DIR / "X_test_raw.csv", index=False)

    print("✅ Data preparation complete")
    print(f"Files saved to {PROCESSED_DIR}/")


if __name__ == "__main__":
    prepare()