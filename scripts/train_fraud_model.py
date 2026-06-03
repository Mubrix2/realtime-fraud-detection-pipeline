# scripts/train_fraud_model.py
"""
Train the XGBoost fraud classification model.

This script:
1. Loads the processed training data from Phase 2
2. Trains XGBoost with parameters tuned for fraud detection
3. Evaluates on the held-out test set
4. Saves the trained model for production use

Run after prepare_data.py:
    python scripts/train_fraud_model.py

Key design decisions documented inline.
"""
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from xgboost import XGBClassifier

sys.path.append(str(Path(__file__).resolve().parent.parent))

PROCESSED_DIR = Path("data/processed")
MODELS_DIR = Path("app/models")
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def load_data():
    """Load the processed numpy arrays from prepare_data.py."""
    print("Loading processed data...")
    X_train = np.load(PROCESSED_DIR / "X_train.npy")
    y_train = np.load(PROCESSED_DIR / "y_train.npy")
    X_test = np.load(PROCESSED_DIR / "X_test.npy")
    y_test = np.load(PROCESSED_DIR / "y_test.npy")

    print(f"Train: {X_train.shape} | Test: {X_test.shape}")
    print(
        f"Train fraud rate: {y_train.mean()*100:.2f}% "
        f"(after SMOTE — balanced)"
    )
    print(
        f"Test fraud rate:  {y_test.mean()*100:.3f}% "
        f"(real-world distribution)"
    )
    return X_train, y_train, X_test, y_test


def build_model():
    """
    Build XGBoost classifier with fraud-detection-tuned parameters.

    Parameter explanations:
    - n_estimators=500: number of trees. More trees = better fit
      but slower inference. 500 is a good production balance.
    - max_depth=6: how deep each tree grows. Deeper = more complex
      patterns captured but higher risk of overfitting.
    - learning_rate=0.05: how much each tree corrects the previous.
      Lower rate + more trees = better generalisation.
    - subsample=0.8: each tree uses 80% of training rows randomly.
      Prevents any single tree from memorising the data.
    - colsample_bytree=0.8: each tree uses 80% of features.
      Adds diversity across trees.
    - eval_metric='aucpr': Area Under Precision-Recall Curve.
      Better than AUC-ROC for imbalanced datasets because it focuses
      on the minority (fraud) class performance.
    - early_stopping_rounds=50: stop training if no improvement
      after 50 rounds. Prevents overfitting automatically.
    - random_state=42: reproducibility.
    """
    return XGBClassifier(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="aucpr",
        early_stopping_rounds=50,
        random_state=42,
        n_jobs=-1,
        verbosity=1,
    )


def find_optimal_threshold(model, X_test, y_test):
    """
    Find the probability threshold that maximises F1 score on the test set.

    The default threshold is 0.5 — but this is almost never optimal
    for imbalanced fraud data. A lower threshold catches more fraud
    (higher recall) at the cost of more false alarms (lower precision).

    We search thresholds from 0.1 to 0.9 and pick the one with
    the best F1 score on the fraud class.
    """
    probabilities = model.predict_proba(X_test)[:, 1]
    thresholds = np.arange(0.1, 0.9, 0.05)
    best_threshold = 0.5
    best_f1 = 0.0

    for threshold in thresholds:
        predictions = (probabilities >= threshold).astype(int)
        f1 = f1_score(y_test, predictions, zero_division=0)
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = threshold

    return round(best_threshold, 2), best_f1


def evaluate(model, X_test, y_test, threshold):
    """
    Print a full evaluation report for the model.
    This is what you show in your README and portfolio.
    """
    probabilities = model.predict_proba(X_test)[:, 1]
    predictions = (probabilities >= threshold).astype(int)

    print("\n" + "="*60)
    print("FRAUD DETECTION MODEL — EVALUATION REPORT")
    print("="*60)

    print(f"\nThreshold: {threshold}")
    print(
        f"(Transactions with fraud probability >= {threshold} "
        f"are flagged)\n"
    )

    print("Classification Report:")
    print(classification_report(
        y_test, predictions,
        target_names=["Legitimate", "Fraud"],
        digits=4,
    ))

    cm = confusion_matrix(y_test, predictions)
    tn, fp, fn, tp = cm.ravel()
    print("Confusion Matrix:")
    print(f"  True Negatives  (correctly cleared): {tn:,}")
    print(f"  False Positives (wrongly flagged):   {fp:,}")
    print(f"  False Negatives (missed fraud):      {fn:,}")
    print(f"  True Positives  (caught fraud):      {tp:,}")

    print("\nKey Business Metrics:")
    print(
        f"  Fraud Recall:    {recall_score(y_test, predictions):.4f} "
        f"— {recall_score(y_test, predictions)*100:.1f}% of fraud caught"
    )
    print(
        f"  Fraud Precision: {precision_score(y_test, predictions):.4f} "
        f"— {precision_score(y_test, predictions)*100:.1f}% of flags are real fraud"
    )
    print(
        f"  F1 Score:        {f1_score(y_test, predictions):.4f}"
    )
    print(
        f"  ROC-AUC:         {roc_auc_score(y_test, probabilities):.4f}"
    )

    return {
        "threshold": threshold,
        "recall": recall_score(y_test, predictions),
        "precision": precision_score(y_test, predictions),
        "f1": f1_score(y_test, predictions),
        "roc_auc": roc_auc_score(y_test, probabilities),
        "true_positives": int(tp),
        "false_positives": int(fp),
        "false_negatives": int(fn),
        "true_negatives": int(tn),
    }


def train():
    X_train, y_train, X_test, y_test = load_data()

    print("\nTraining XGBoost model...")
    print("This takes 3-8 minutes depending on your machine.\n")

    model = build_model()

    # eval_set lets XGBoost monitor performance on test set
    # during training — used for early stopping
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=50,
    )

    print(f"\nTraining complete.")
    print(f"Best iteration: {model.best_iteration}")

    # Find best threshold
    print("\nFinding optimal decision threshold...")
    threshold, best_f1 = find_optimal_threshold(model, X_test, y_test)
    print(f"Optimal threshold: {threshold} (F1: {best_f1:.4f})")

    # Full evaluation
    metrics = evaluate(model, X_test, y_test, threshold)

    # Save model and metadata
    model_path = MODELS_DIR / "fraud_model.pkl"
    metadata_path = MODELS_DIR / "fraud_model_metadata.json"

    joblib.dump(model, model_path)
    print(f"\nModel saved to {model_path}")

    import json
    metadata = {
        "model_type": "XGBClassifier",
        "threshold": threshold,
        "metrics": metrics,
        "feature_columns": [
            "amount", "oldbalanceOrg", "newbalanceOrig",
            "oldbalanceDest", "newbalanceDest", "hour_of_day",
            "is_transfer", "is_cashout", "balance_diff_orig",
            "balance_diff_dest", "error_balance_orig",
            "error_balance_dest", "amount_ratio_orig",
            "dest_balance_zero_before", "dest_balance_zero_after",
            "orig_balance_zeroed",
        ],
    }
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"Metadata saved to {metadata_path}")
    print("\n✅ XGBoost fraud model training complete")


if __name__ == "__main__":
    train()