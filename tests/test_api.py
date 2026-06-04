# tests/test_api.py
from datetime import datetime
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import create_app

client = TestClient(create_app())


def _valid_transaction(**overrides) -> dict:
    base = {
        "transaction_id": "TXN-TEST-001",
        "step": 10,
        "type": "TRANSFER",
        "amount": 150000.00,
        "name_orig": "C1234567890",
        "oldbalance_org": 300000.00,
        "newbalance_orig": 150000.00,
        "name_dest": "C9876543210",
        "oldbalance_dest": 0.00,
        "newbalance_dest": 150000.00,
    }
    base.update(overrides)
    return base


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "fraud_model_loaded" in data
    assert "kafka_connected" in data


def test_submit_transaction_returns_202():
    with patch("app.api.routes.transactions.publish_transaction") as mock_pub:
        mock_pub.return_value = {"status": "published", "error": None}
        response = client.post(
            "/api/v1/transactions/submit",
            json=_valid_transaction(),
        )
    assert response.status_code == 202
    data = response.json()
    assert data["transaction_id"] == "TXN-TEST-001"
    assert data["status"] == "accepted"


def test_submit_rejects_negative_amount():
    response = client.post(
        "/api/v1/transactions/submit",
        json=_valid_transaction(amount=-500.00),
    )
    assert response.status_code == 422


def test_submit_rejects_invalid_transaction_type():
    response = client.post(
        "/api/v1/transactions/submit",
        json=_valid_transaction(type="WIRE_FRAUD"),
    )
    assert response.status_code == 422


def test_submit_rejects_extra_fields():
    """
    extra="forbid" should reject any unknown fields.
    This tests our security boundary.
    """
    payload = _valid_transaction()
    payload["malicious_field"] = "injection_attempt"
    response = client.post(
        "/api/v1/transactions/submit",
        json=payload,
    )
    assert response.status_code == 422


def test_results_returns_404_for_unknown_transaction():
    response = client.get("/api/v1/transactions/results/UNKNOWN-TXN-999")
    assert response.status_code == 404


def test_results_returns_score_after_submission():
    with patch("app.api.routes.transactions.publish_transaction") as mock_pub:
        mock_pub.return_value = {"status": "published", "error": None}
        client.post(
            "/api/v1/transactions/submit",
            json=_valid_transaction(transaction_id="TXN-SCORE-TEST"),
        )

    response = client.get(
        "/api/v1/transactions/results/TXN-SCORE-TEST"
    )
    assert response.status_code == 200
    data = response.json()
    assert "fraud_probability" in data
    assert "is_fraud" in data
    assert "risk_level" in data
    assert "top_reasons" in data


def test_503_when_kafka_unavailable():
    with patch("app.api.routes.transactions.publish_transaction") as mock_pub:
        mock_pub.return_value = {
            "status": "failed",
            "error": "Broker not available"
        }
        response = client.post(
            "/api/v1/transactions/submit",
            json=_valid_transaction(transaction_id="TXN-KAFKA-FAIL"),
        )
    assert response.status_code == 503