# tests/test_anomaly_detector.py
import numpy as np
import pytest
from unittest.mock import MagicMock
from app.core.feature_engineer import FEATURE_COLUMNS


def _base_features():
    return {col: 0.0 for col in FEATURE_COLUMNS}


def test_returns_all_expected_keys():
    from app.core.anomaly_detector import score_transaction
    result = score_transaction(_base_features())
    assert "anomaly_score" in result
    assert "is_anomalous" in result
    assert "anomaly_severity" in result
    assert "model_available" in result


def test_safe_default_when_model_not_loaded():
    import app.core.anomaly_detector as detector
    detector._model = None
    result = detector.score_transaction(_base_features())
    assert result["is_anomalous"] is False
    assert result["model_available"] is False


def test_anomalous_when_score_below_threshold():
    import app.core.anomaly_detector as detector

    mock_model = MagicMock()
    mock_model.score_samples.return_value = np.array([-0.25])
    detector._model = mock_model
    detector._scaler = None
    detector._threshold = -0.1

    result = detector.score_transaction(_base_features())
    assert result["is_anomalous"] is True
    assert result["anomaly_severity"] in ("SUSPICIOUS", "ANOMALOUS")


def test_normal_when_score_above_threshold():
    import app.core.anomaly_detector as detector

    mock_model = MagicMock()
    mock_model.score_samples.return_value = np.array([0.05])
    detector._model = mock_model
    detector._scaler = None
    detector._threshold = -0.1

    result = detector.score_transaction(_base_features())
    assert result["is_anomalous"] is False
    assert result["anomaly_severity"] == "NORMAL"


def test_anomalous_severity_for_very_low_score():
    import app.core.anomaly_detector as detector

    mock_model = MagicMock()
    # Score well below threshold — ANOMALOUS not just SUSPICIOUS
    mock_model.score_samples.return_value = np.array([-0.35])
    detector._model = mock_model
    detector._scaler = None
    detector._threshold = -0.1

    result = detector.score_transaction(_base_features())
    assert result["anomaly_severity"] == "ANOMALOUS"