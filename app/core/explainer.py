# app/core/explainer.py
"""
SHAP explainability layer for the fraud detection system.

This module answers the compliance question:
"Why did the model flag this specific transaction?"

SHAP (SHapley Additive exPlanations) assigns each feature a
contribution score — how much it pushed the fraud probability
up or down from the baseline.

Regulatory context:
- GDPR Article 22: individuals have right to explanation for
  automated decisions affecting them
- US Fair Credit Reporting Act: adverse action notices required
- CBN AI Guidelines: explainability required for financial AI

This module satisfies all three requirements.
"""
import logging
from typing import Optional

import numpy as np
import shap

from app.core.feature_engineer import FEATURE_COLUMNS

logger = logging.getLogger(__name__)

# Human-readable names for each model feature.
# These appear in compliance reports and analyst dashboards.
# Written for a non-technical compliance officer, not a data scientist.
FEATURE_DESCRIPTIONS = {
    "amount":
        "Transaction amount",
    "oldbalanceOrg":
        "Sender balance before transaction",
    "newbalanceOrig":
        "Sender balance after transaction",
    "oldbalanceDest":
        "Recipient balance before transaction",
    "newbalanceDest":
        "Recipient balance after transaction",
    "hour_of_day":
        "Hour of day transaction occurred",
    "is_transfer":
        "Transaction type is TRANSFER",
    "is_cashout":
        "Transaction type is CASH_OUT",
    "balance_diff_orig":
        "Change in sender balance",
    "balance_diff_dest":
        "Change in recipient balance",
    "amount_ratio_orig":
        "Transaction as proportion of sender total balance",
    "dest_balance_zero_before":
        "Recipient account had zero balance before transaction",
    "dest_balance_zero_after":
        "Recipient account has zero balance after transaction",
    "orig_balance_zeroed":
        "Sender account completely emptied by this transaction",
}

# Singleton SHAP explainer — created once when the model loads
_explainer: Optional[shap.TreeExplainer] = None


def initialise_explainer(model) -> None:
    """
    Create the SHAP TreeExplainer from the loaded XGBoost model.

    Called once from fraud_scorer.load_model() after the model loads.
    TreeExplainer is optimised specifically for tree-based models
    like XGBoost — it uses an exact algorithm rather than sampling,
    making it both fast and accurate.

    Why not call this on every request?
    Creating a TreeExplainer involves analysing the full model tree
    structure — this takes ~1 second. We create it once and reuse it.
    """
    global _explainer
    _explainer = shap.TreeExplainer(model)
    logger.info("SHAP TreeExplainer initialised")


def explain_transaction(features: dict, top_n: int = 5) -> dict:
    """
    Generate SHAP explanation for a single transaction scoring.

    Args:
        features: Engineered features dict from feature_engineer.py
        top_n: Number of top contributing features to return

    Returns:
        Dict containing:
        - shap_values: raw SHAP values for all features
        - top_reasons: top N features driving the score, with
                       direction (increased/decreased risk) and
                       human-readable descriptions
        - baseline_probability: what the model predicts for an
                                average transaction
        - explanation_available: bool

    Example output:
        {
            "top_reasons": [
                {
                    "feature": "orig_balance_zeroed",
                    "description": "Sender account completely emptied",
                    "shap_value": 0.31,
                    "direction": "increased_risk",
                    "impact": "HIGH"
                },
                ...
            ]
        }
    """
    if _explainer is None:
        logger.warning("SHAP explainer not initialised")
        return {
            "top_reasons": [],
            "baseline_probability": None,
            "shap_values": [],
            "explanation_available": False,
        }

    # Build feature array in training order
    feature_array = np.array(
        [[features.get(col, 0.0) for col in FEATURE_COLUMNS]]
    )

    try:
        # shap_values shape: (1, n_features) for binary classification
        # These are SHAP values in log-odds space for XGBoost
        shap_values = _explainer.shap_values(feature_array)

        # For XGBoost binary classification, shap_values is a 2D array
        # We take the first row (our single transaction)
        if isinstance(shap_values, list):
            # Some versions return a list for binary classification
            values = shap_values[1][0]
        else:
            values = shap_values[0]

        # Pair each feature name with its SHAP value
        feature_shap_pairs = list(zip(FEATURE_COLUMNS, values))

        # Sort by absolute SHAP value — highest impact first
        feature_shap_pairs.sort(key=lambda x: abs(x[1]), reverse=True)

        # Build human-readable reasons for top N features
        top_reasons = []
        for feature_name, shap_value in feature_shap_pairs[:top_n]:
            direction = (
                "increased_risk"
                if shap_value > 0
                else "decreased_risk"
            )

            # Classify impact magnitude for the dashboard
            abs_value = abs(shap_value)
            if abs_value >= 0.2:
                impact = "HIGH"
            elif abs_value >= 0.1:
                impact = "MEDIUM"
            else:
                impact = "LOW"

            top_reasons.append({
                "feature": feature_name,
                "description": FEATURE_DESCRIPTIONS.get(
                    feature_name, feature_name
                ),
                "shap_value": round(float(shap_value), 6),
                "direction": direction,
                "impact": impact,
                "feature_value": round(
                    float(features.get(feature_name, 0.0)), 4
                ),
            })

        # Expected value is the baseline — what model predicts
        # for an average transaction (before considering features)
        baseline = float(_explainer.expected_value)
        if isinstance(_explainer.expected_value, np.ndarray):
            baseline = float(_explainer.expected_value[0])

        return {
            "top_reasons": top_reasons,
            "baseline_probability": round(baseline, 6),
            "shap_values": [round(float(v), 6) for v in values],
            "feature_names": FEATURE_COLUMNS,
            "explanation_available": True,
        }

    except Exception as e:
        logger.error(f"SHAP explanation failed: {e}")
        return {
            "top_reasons": [],
            "baseline_probability": None,
            "shap_values": [],
            "explanation_available": False,
        }


def format_explanation_text(explanation: dict) -> str:
    """
    Format SHAP explanation as plain English text.

    Used in compliance reports and email alerts.
    Designed for a non-technical fraud analyst reader.

    Example output:
        "This transaction was flagged for the following reasons:

        HIGH RISK: Sender account completely emptied by this
        transaction — increased fraud risk significantly.

        HIGH RISK: Recipient account had zero balance before
        transaction — typical pattern in mule accounts.

        MEDIUM RISK: Transaction as proportion of sender total
        balance is unusually high — increased fraud risk."
    """
    if not explanation.get("explanation_available"):
        return "Explanation not available."

    reasons = explanation.get("top_reasons", [])
    if not reasons:
        return "No significant feature contributions found."

    lines = ["This transaction was flagged for the following reasons:\n"]

    for reason in reasons:
        direction_text = (
            "increased fraud risk"
            if reason["direction"] == "increased_risk"
            else "reduced fraud risk"
        )
        lines.append(
            f"{reason['impact']} RISK: {reason['description']} "
            f"— {direction_text}."
        )

    return "\n".join(lines)