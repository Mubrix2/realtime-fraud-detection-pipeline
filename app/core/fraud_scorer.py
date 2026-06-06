# app/core/fraud_scorer.py
"""
Production fraud scorer.

Loads the trained XGBoost model at startup (singleton pattern)
and scores individual transactions in real time.

Design principle: this module knows nothing about Kafka or FastAPI.
It takes a feature dict, returns a score dict.
Fully testable without any infrastructure.
"""
import sys
from pathlib import Path
import json
import logging
from pathlib import Path

import joblib
import numpy as np

from app.config import FRAUD_MODEL_PATH, FRAUD_THRESHOLD
from app.core.feature_engineer import FEATURE_COLUMNS
from app.core.explainer import initialise_explainer

logger = logging.getLogger(__name__)

# Allow imports from project root
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Singleton — model loaded once, reused for every transaction
_model = None
_threshold = FRAUD_THRESHOLD
_metadata = {}


def load_model():
    """
    Load the trained model from disk.
    Called once at application startup via lifespan event.
    Loading takes ~1 second — we do it at startup, not per-request.
    """
    global _model, _threshold, _metadata

    if not FRAUD_MODEL_PATH.exists():
        logger.warning(
            f"Fraud model not found at {FRAUD_MODEL_PATH}. "
            "Run: python scripts/train_fraud_model.py"
        )
        return False

    _model = joblib.load(FRAUD_MODEL_PATH)

    # Load metadata for threshold and feature info
    metadata_path = FRAUD_MODEL_PATH.parent / "fraud_model_metadata.json"
    if metadata_path.exists():
        with open(metadata_path) as f:
            _metadata = json.load(f)
        _threshold = _metadata.get("threshold", FRAUD_THRESHOLD)

    from app.core.explainer import initialise_explainer
    initialise_explainer(_model)

    logger.info(
        f"Fraud model loaded. Threshold: {_threshold}. "
        f"Best iteration: {getattr(_model, 'best_iteration', 'N/A')}"
        f"SHAP explainer ready."
    )
    return True


def _get_tiered_action(probability: float) -> dict:
    """
    Tiered threshold system.

    Instead of a single binary cut-off, we define four zones
    that trigger different customer-facing actions.

    Thresholds are configurable via environment variables —
    different businesses have different risk tolerances.
    A lending company may set CHALLENGE lower than a payment processor.

    APPROVE   — low risk, no friction
    FLAG      — moderate risk, approve but alert analyst
    CHALLENGE — high risk, require step-up authentication (OTP/biometric)
    BLOCK     — critical risk, decline and require manual review
    """
    if probability >= 0.80:
        return {
            "action": "BLOCK",
            "risk_level": "CRITICAL",
            "is_fraud": True,
            "customer_message": (
                "This transaction has been declined for security reasons. "
                "Please contact your bank."
            ),
            "analyst_action": "Manual review required immediately",
        }
    elif probability >= 0.60:
        return {
            "action": "CHALLENGE",
            "risk_level": "HIGH",
            "is_fraud": False,
            "customer_message": (
                "Please verify this transaction with the OTP "
                "sent to your registered phone number."
            ),
            "analyst_action": "Flag for review if challenge fails",
        }
    elif probability >= 0.30:
        return {
            "action": "FLAG",
            "risk_level": "MEDIUM",
            "is_fraud": False,
            "customer_message": "Transaction approved.",
            "analyst_action": "Review within 24 hours",
        }
    else:
        return {
            "action": "APPROVE",
            "risk_level": "LOW",
            "is_fraud": False,
            "customer_message": "Transaction approved.",
            "analyst_action": "No action required",
        }



def score_transaction(features: dict) -> dict:
    """
    Score a single transaction for fraud probability.

    Args:
        features: Dict of engineered features from feature_engineer.py
                  Must contain all columns in FEATURE_COLUMNS

    Returns:
        Dict with:
        - fraud_probability: float 0.0–1.0
        - is_fraud: bool (probability >= threshold)
        - risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
        - threshold_used: float
        - model_available: bool

    If model is not loaded, returns a safe default (not_fraud)
    so the system degrades gracefully rather than crashing.
    """
    if _model is None:
        logger.warning("Model not loaded — returning safe default")
        return {
            "fraud_probability": 0.0,
            "is_fraud": False,
            "risk_level": "UNKNOWN",
            "threshold_used": _threshold,
            "model_available": False,
        }

    # Build feature array in the exact order the model was trained on
    feature_values = np.array(
        [[features.get(col, 0.0) for col in FEATURE_COLUMNS]]
    )

    # predict_proba returns [[prob_legitimate, prob_fraud]]
    # We want the fraud probability — index 1
    fraud_probability = float(_model.predict_proba(feature_values)[0][1])
    

    # Risk levels give analysts a human-readable triage label
    # These thresholds are business decisions — adjust based on
    # how conservative your client wants to be
    tiered = _get_tiered_action(fraud_probability)


    return {
        "fraud_probability": round(fraud_probability, 6),
        "action": tiered["action"],
        "is_fraud": tiered["is_fraud"],
        "risk_level": tiered["risk_level"],
        "customer_message": tiered["customer_message"],
        "analyst_action": tiered["analyst_action"],
        "threshold_used": "tiered",
        "model_available": True,
    }


def get_model_info() -> dict:
    """Return model metadata for the health check endpoint."""
    return {
        "model_loaded": _model is not None,
        "threshold": _threshold,
        "metrics": _metadata.get("metrics", {}),
        "feature_count": len(FEATURE_COLUMNS),
    }