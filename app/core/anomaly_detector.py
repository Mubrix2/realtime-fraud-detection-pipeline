# app/core/anomaly_detector.py
"""
Production anomaly detector using Isolation Forest.

Complements the XGBoost fraud classifier:
- XGBoost catches KNOWN fraud patterns
- Isolation Forest catches NOVEL/UNUSUAL patterns

Both scores are returned to the detection service which
combines them into a final verdict.
"""
import json
import logging
from pathlib import Path

import joblib
import numpy as np

from app.config import ANOMALY_MODEL_PATH, ANOMALY_THRESHOLD
from app.core.feature_engineer import FEATURE_COLUMNS

logger = logging.getLogger(__name__)

_model = None
_scaler = None
_threshold = ANOMALY_THRESHOLD
_metadata = {}


def load_model():
    """
    Load Isolation Forest model and scaler from disk.
    Called once at application startup.
    """
    global _model, _scaler, _threshold, _metadata

    if not ANOMALY_MODEL_PATH.exists():
        logger.warning(
            f"Anomaly model not found at {ANOMALY_MODEL_PATH}. "
            "Run: python scripts/train_anomaly_model.py"
        )
        return False

    _model = joblib.load(ANOMALY_MODEL_PATH)

    # Load the same scaler used during training
    scaler_path = ANOMALY_MODEL_PATH.parent / "scaler.pkl"
    if scaler_path.exists():
        _scaler = joblib.load(scaler_path)

    metadata_path = ANOMALY_MODEL_PATH.parent / "anomaly_model_metadata.json"
    if metadata_path.exists():
        with open(metadata_path) as f:
            _metadata = json.load(f)
        _threshold = _metadata.get("threshold", ANOMALY_THRESHOLD)

    logger.info(
        f"Anomaly model loaded. "
        f"Threshold: {_threshold:.6f}"
    )
    return True


def score_transaction(features: dict) -> dict:
    """
    Score a single transaction for anomalous behaviour.

    The anomaly score is the raw Isolation Forest score_samples output.
    - Score close to 0: normal transaction
    - Score below threshold: anomalous transaction

    Args:
        features: Engineered features dict from feature_engineer.py

    Returns:
        Dict with:
        - anomaly_score: float (lower = more anomalous)
        - is_anomalous: bool
        - anomaly_severity: "NORMAL" | "SUSPICIOUS" | "ANOMALOUS"
        - model_available: bool
    """
    if _model is None:
        logger.warning("Anomaly model not loaded — returning safe default")
        return {
            "anomaly_score": 0.0,
            "is_anomalous": False,
            "anomaly_severity": "UNKNOWN",
            "model_available": False,
        }

    feature_array = np.array(
        [[features.get(col, 0.0) for col in FEATURE_COLUMNS]]
    )

    # Scale features using the same scaler from training
    if _scaler is not None:
        feature_array = _scaler.transform(feature_array)

    # score_samples returns negative values
    # More negative = more isolated = more anomalous
    anomaly_score = float(_model.score_samples(feature_array)[0])
    is_anomalous = anomaly_score < _threshold

    # Severity levels based on how far below threshold the score is
    if anomaly_score < _threshold - 0.1:
        severity = "ANOMALOUS"
    elif anomaly_score < _threshold:
        severity = "SUSPICIOUS"
    else:
        severity = "NORMAL"

    return {
        "anomaly_score": round(anomaly_score, 6),
        "is_anomalous": is_anomalous,
        "anomaly_severity": severity,
        "threshold_used": _threshold,
        "model_available": True,
    }


def get_model_info() -> dict:
    """Return model info for health check endpoint."""
    return {
        "model_loaded": _model is not None,
        "threshold": _threshold,
        "metrics": _metadata.get("metrics", {}),
    }