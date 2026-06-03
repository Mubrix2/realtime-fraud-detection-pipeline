# tests/test_fraud_scorer.py
"""
Tests for the fraud scorer.
All tests use mocking — no real model file required.
"""
import pytest
from unittest.mock import MagicMock, patch
import numpy as np


def test_score_returns_all_expected_keys():
    """Score result must always have these keys regardless of model state."""
    from app.core.fraud_scorer import score_transaction

    features = {col: 0.0 for col in [
        "amount", "oldbalanceOrg", "newbalanceOrig",
        "oldbalanceDest", "newbalanceDest", "hour_of_day",
        "is_transfer", "is_cashout", "balance_diff_orig",
        "balance_diff_dest", "error_balance_orig",
        "error_balance_dest", "amount_ratio_orig",
        "dest_balance_zero_before", "dest_balance_zero_after",
        "orig_balance_zeroed",
    ]}

    result = score_transaction(features)
    assert "fraud_probability" in result
    assert "is_fraud" in result
    assert "risk_level" in result
    assert "threshold_used" in result
    assert "model_available" in result


def test_score_returns_safe_default_when_model_not_loaded():
    """When model is not loaded, return not_fraud rather than crashing."""
    import app.core.fraud_scorer as scorer
    scorer._model = None

    features = {"amount": 100.0}
    result = scorer.score_transaction(features)

    assert result["is_fraud"] is False
    assert result["model_available"] is False
    assert result["fraud_probability"] == 0.0


def test_risk_level_critical_for_high_probability():
    """Probability >= 0.9 should give CRITICAL risk level."""
    import app.core.fraud_scorer as scorer

    mock_model = MagicMock()
    mock_model.predict_proba.return_value = np.array([[0.05, 0.95]])
    scorer._model = mock_model
    scorer._threshold = 0.7

    features = {col: 0.0 for col in scorer.FEATURE_COLUMNS
                if hasattr(scorer, 'FEATURE_COLUMNS')}

    from app.core.feature_engineer import FEATURE_COLUMNS
    features = {col: 0.0 for col in FEATURE_COLUMNS}

    result = scorer.score_transaction(features)
    assert result["risk_level"] == "CRITICAL"
    assert result["is_fraud"] is True


def test_risk_level_low_for_low_probability():
    """Probability < 0.4 should give LOW risk level."""
    import app.core.fraud_scorer as scorer
    from app.core.feature_engineer import FEATURE_COLUMNS

    mock_model = MagicMock()
    mock_model.predict_proba.return_value = np.array([[0.85, 0.15]])
    scorer._model = mock_model

    features = {col: 0.0 for col in FEATURE_COLUMNS}
    result = scorer.score_transaction(features)
    assert result["risk_level"] == "LOW"
    assert result["is_fraud"] is False


def test_is_fraud_flag_respects_threshold():
    """Transactions above threshold are fraud, below are not."""
    import app.core.fraud_scorer as scorer
    from app.core.feature_engineer import FEATURE_COLUMNS

    mock_model = MagicMock()
    scorer._model = mock_model
    scorer._threshold = 0.7

    # Just below threshold
    mock_model.predict_proba.return_value = np.array([[0.32, 0.68]])
    features = {col: 0.0 for col in FEATURE_COLUMNS}
    result = scorer.score_transaction(features)
    assert result["is_fraud"] is False

    # Just above threshold
    mock_model.predict_proba.return_value = np.array([[0.29, 0.71]])
    result = scorer.score_transaction(features)
    assert result["is_fraud"] is True