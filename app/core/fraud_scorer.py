# app/core/fraud_scorer.py
"""
Production fraud scorer.

Loads the trained XGBoost model at startup (singleton pattern)
and scores individual transactions in real time.

Design principle: this module knows nothing about Kafka or FastAPI.
It takes a feature dict, returns a score dict.
Fully testable without any infrastructure.
"""
import json
import logging
from pathlib import Path

import joblib
import numpy as np

from app.config import FRAUD_MODEL_PATH, FRAUD_THRESHOLD
from app.core.feature_engineer import FEATURE_COLUMNS
from app.core.explainer import initialise_explainer

logger = logging.getLogger(__name__)

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

    # Initialise the SHAP explainer with the loaded model
    initialise_explainer(_model)

    logger.info(
        f"Fraud model loaded. Threshold: {_threshold}. "
        f"Best iteration: {getattr(_model, 'best_iteration', 'N/A')}"
        f"SHAP explainer ready."
    )
    return True


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
    is_fraud = fraud_probability >= _threshold

    # Risk levels give analysts a human-readable triage label
    # These thresholds are business decisions — adjust based on
    # how conservative your client wants to be
    if fraud_probability >= 0.9:
        risk_level = "CRITICAL"
    elif fraud_probability >= 0.7:
        risk_level = "HIGH"
    elif fraud_probability >= 0.4:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return {
        "fraud_probability": round(fraud_probability, 6),
        "is_fraud": is_fraud,
        "risk_level": risk_level,
        "threshold_used": _threshold,
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