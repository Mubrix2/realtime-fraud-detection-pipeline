# tests/test_explainer.py
import numpy as np
import pytest
from unittest.mock import MagicMock, patch
from app.core.feature_engineer import FEATURE_COLUMNS


def _base_features() -> dict:
    return {col: 0.0 for col in FEATURE_COLUMNS}


def test_returns_all_expected_keys():
    """Explanation result must always have these keys."""
    import app.core.explainer as explainer
    explainer._explainer = None

    result = explainer.explain_transaction(_base_features())
    assert "top_reasons" in result
    assert "explanation_available" in result
    assert "shap_values" in result


def test_returns_safe_default_when_not_initialised():
    """When explainer is not ready, degrade gracefully."""
    import app.core.explainer as explainer
    explainer._explainer = None

    result = explainer.explain_transaction(_base_features())
    assert result["explanation_available"] is False
    assert result["top_reasons"] == []


def test_top_reasons_count_respects_top_n():
    """Should return exactly top_n reasons when enough features exist."""
    import app.core.explainer as explainer

    mock_explainer = MagicMock()
    # Return SHAP values — one per feature, varying magnitudes
    shap_values = np.array(
        [[float(i) * 0.05 for i in range(len(FEATURE_COLUMNS))]]
    )
    mock_explainer.shap_values.return_value = shap_values
    mock_explainer.expected_value = 0.1
    explainer._explainer = mock_explainer

    result = explainer.explain_transaction(_base_features(), top_n=3)
    assert len(result["top_reasons"]) == 3


def test_direction_positive_shap_is_increased_risk():
    """Positive SHAP value means the feature increased fraud probability."""
    import app.core.explainer as explainer

    mock_explainer = MagicMock()
    # Make first feature have large positive SHAP value
    shap_vals = np.zeros(len(FEATURE_COLUMNS))
    shap_vals[0] = 0.5  # Strong positive — increases risk
    mock_explainer.shap_values.return_value = np.array([shap_vals])
    mock_explainer.expected_value = 0.1
    explainer._explainer = mock_explainer

    result = explainer.explain_transaction(_base_features(), top_n=1)
    top = result["top_reasons"][0]
    assert top["direction"] == "increased_risk"
    assert top["shap_value"] > 0


def test_direction_negative_shap_is_decreased_risk():
    """Negative SHAP value means the feature reduced fraud probability."""
    import app.core.explainer as explainer

    mock_explainer = MagicMock()
    shap_vals = np.zeros(len(FEATURE_COLUMNS))
    shap_vals[0] = -0.4  # Strong negative — decreases risk
    mock_explainer.shap_values.return_value = np.array([shap_vals])
    mock_explainer.expected_value = 0.1
    explainer._explainer = mock_explainer

    result = explainer.explain_transaction(_base_features(), top_n=1)
    top = result["top_reasons"][0]
    assert top["direction"] == "decreased_risk"
    assert top["shap_value"] < 0


def test_impact_high_for_large_shap_value():
    """SHAP value >= 0.2 should be classified as HIGH impact."""
    import app.core.explainer as explainer

    mock_explainer = MagicMock()
    shap_vals = np.zeros(len(FEATURE_COLUMNS))
    shap_vals[0] = 0.35
    mock_explainer.shap_values.return_value = np.array([shap_vals])
    mock_explainer.expected_value = 0.1
    explainer._explainer = mock_explainer

    result = explainer.explain_transaction(_base_features(), top_n=1)
    assert result["top_reasons"][0]["impact"] == "HIGH"


def test_format_explanation_text_no_explainer():
    """Format function should return safe text when explanation unavailable."""
    from app.core.explainer import format_explanation_text

    explanation = {"explanation_available": False, "top_reasons": []}
    text = format_explanation_text(explanation)
    assert "not available" in text.lower()


def test_format_explanation_text_with_reasons():
    """Format function should produce readable text from reasons."""
    from app.core.explainer import format_explanation_text

    explanation = {
        "explanation_available": True,
        "top_reasons": [
            {
                "description": "Sender account completely emptied",
                "direction": "increased_risk",
                "impact": "HIGH",
            },
            {
                "description": "Transaction occurred at 3am",
                "direction": "increased_risk",
                "impact": "MEDIUM",
            },
        ],
    }
    text = format_explanation_text(explanation)
    assert "Sender account completely emptied" in text
    assert "HIGH RISK" in text
    assert "MEDIUM RISK" in text