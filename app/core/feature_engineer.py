# app/core/feature_engineer.py
"""
Feature engineering for fraud detection.

Every feature here is grounded in real banking fraud patterns
observed in the data exploration notebook.

Design principle: this module knows nothing about Kafka, FastAPI,
or any external service. It takes a dict, returns a dict.
Pure transformation logic, fully testable in isolation.
"""
import numpy as np
import pandas as pd


# These are the features the model was trained on.
# The order matters — it must match the training data exactly.
FEATURE_COLUMNS = [
    "amount",
    "oldbalanceOrg",
    "newbalanceOrig",
    "oldbalanceDest",
    "newbalanceDest",
    "hour_of_day",
    "is_transfer",
    "is_cashout",
    "balance_diff_orig",
    "balance_diff_dest",
    "error_balance_orig",
    "error_balance_dest",
    "amount_ratio_orig",
    "dest_balance_zero_before",
    "dest_balance_zero_after",
    "orig_balance_zeroed",
]


def engineer_features(transaction: dict) -> dict:
    """
    Transform a raw transaction dict into model-ready features.

    Args:
        transaction: Raw transaction with fields matching PaySim schema

    Returns:
        Dict of engineered features ready for the ML model

    Each feature is documented with the fraud insight that motivates it.
    """
    amount = float(transaction.get("amount", 0))
    old_balance_orig = float(transaction.get("oldbalanceOrg", 0))
    new_balance_orig = float(transaction.get("newbalanceOrig", 0))
    old_balance_dest = float(transaction.get("oldbalanceDest", 0))
    new_balance_dest = float(transaction.get("newbalanceDest", 0))
    transaction_type = str(transaction.get("type", "")).upper()
    step = int(transaction.get("step", 0))

    # ── Time features ─────────────────────────────────────────────────────────
    # Fraud rate varies significantly by hour.
    # Fraudsters often operate late at night when monitoring is reduced.
    hour_of_day = step % 24

    # ── Transaction type flags ────────────────────────────────────────────────
    # CRITICAL: Fraud ONLY occurs in TRANSFER and CASH_OUT transactions.
    # This is the single most important signal in the dataset.
    # A PAYMENT to a merchant is almost never fraudulent.
    is_transfer = 1 if transaction_type == "TRANSFER" else 0
    is_cashout = 1 if transaction_type == "CASH_OUT" else 0

    # ── Balance difference features ───────────────────────────────────────────
    # For a legitimate transaction:
    # new_balance_orig = old_balance_orig - amount (sender loses amount)
    # new_balance_dest = old_balance_dest + amount (recipient gains amount)
    #
    # Fraudulent transactions frequently violate these relationships
    # because the fraud system does not correctly update balances.
    balance_diff_orig = old_balance_orig - new_balance_orig
    balance_diff_dest = new_balance_dest - old_balance_dest

    # ── Balance error features ────────────────────────────────────────────────
    # The error is the discrepancy between expected and actual balance change.
    # A legitimate transaction has error ≈ 0.
    # Fraudulent transactions often have large errors — a major red flag.
    error_balance_orig = balance_diff_orig - amount
    error_balance_dest = balance_diff_dest - amount

    # ── Amount ratio ──────────────────────────────────────────────────────────
    # What proportion of the sender's total balance was transacted?
    # Fraudsters often drain accounts — high ratio signals account takeover.
    # Adding 1 to denominator prevents division by zero for empty accounts.
    amount_ratio_orig = amount / (old_balance_orig + 1)

    # ── Zero balance flags ────────────────────────────────────────────────────
    # When fraud occurs the recipient's balance is often:
    # - Zero before the transaction (a freshly created mule account)
    # - Zero after the transaction (immediately emptied)
    # Both patterns are strong fraud signals.
    dest_balance_zero_before = 1 if old_balance_dest == 0 else 0
    dest_balance_zero_after = 1 if new_balance_dest == 0 else 0

    # Account completely emptied — classic account takeover pattern
    orig_balance_zeroed = 1 if new_balance_orig == 0 else 0

    return {
        "amount": amount,
        "oldbalanceOrg": old_balance_orig,
        "newbalanceOrig": new_balance_orig,
        "oldbalanceDest": old_balance_dest,
        "newbalanceDest": new_balance_dest,
        "hour_of_day": hour_of_day,
        "is_transfer": is_transfer,
        "is_cashout": is_cashout,
        "balance_diff_orig": balance_diff_orig,
        "balance_diff_dest": balance_diff_dest,
        "error_balance_orig": error_balance_orig,
        "error_balance_dest": error_balance_dest,
        "amount_ratio_orig": amount_ratio_orig,
        "dest_balance_zero_before": dest_balance_zero_before,
        "dest_balance_zero_after": dest_balance_zero_after,
        "orig_balance_zeroed": orig_balance_zeroed,
    }


def engineer_features_batch(df: pd.DataFrame) -> pd.DataFrame:
    """
    Engineer features for a full DataFrame.
    Used by training scripts to process the entire PaySim dataset.
    Returns a DataFrame with only the model feature columns.
    """
    result = df.copy()

    result["hour_of_day"] = result["step"] % 24
    result["is_transfer"] = (result["type"] == "TRANSFER").astype(int)
    result["is_cashout"] = (result["type"] == "CASH_OUT").astype(int)
    result["balance_diff_orig"] = result["oldbalanceOrg"] - result["newbalanceOrig"]
    result["balance_diff_dest"] = result["newbalanceDest"] - result["oldbalanceDest"]
    result["error_balance_orig"] = result["balance_diff_orig"] - result["amount"]
    result["error_balance_dest"] = result["balance_diff_dest"] - result["amount"]
    result["amount_ratio_orig"] = result["amount"] / (result["oldbalanceOrg"] + 1)
    result["dest_balance_zero_before"] = (result["oldbalanceDest"] == 0).astype(int)
    result["dest_balance_zero_after"] = (result["newbalanceDest"] == 0).astype(int)
    result["orig_balance_zeroed"] = (result["newbalanceOrig"] == 0).astype(int)

    return result[FEATURE_COLUMNS]