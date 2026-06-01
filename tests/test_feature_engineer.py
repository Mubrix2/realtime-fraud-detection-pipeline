# tests/test_feature_engineer.py
import pytest
from app.core.feature_engineer import engineer_features, FEATURE_COLUMNS


def _make_transaction(**overrides) -> dict:
    """Helper to create a base transaction with optional overrides."""
    base = {
        "step": 10,
        "type": "TRANSFER",
        "amount": 100000.0,
        "oldbalanceOrg": 200000.0,
        "newbalanceOrig": 100000.0,
        "oldbalanceDest": 0.0,
        "newbalanceDest": 100000.0,
    }
    base.update(overrides)
    return base


def test_returns_all_expected_features():
    tx = _make_transaction()
    features = engineer_features(tx)
    for col in FEATURE_COLUMNS:
        assert col in features, f"Missing feature: {col}"


def test_transfer_flag_is_set():
    tx = _make_transaction(type="TRANSFER")
    features = engineer_features(tx)
    assert features["is_transfer"] == 1
    assert features["is_cashout"] == 0


def test_cashout_flag_is_set():
    tx = _make_transaction(type="CASH_OUT")
    features = engineer_features(tx)
    assert features["is_cashout"] == 1
    assert features["is_transfer"] == 0


def test_payment_type_neither_flag():
    tx = _make_transaction(type="PAYMENT")
    features = engineer_features(tx)
    assert features["is_transfer"] == 0
    assert features["is_cashout"] == 0


def test_hour_of_day_calculation():
    # step 25 = hour 1 (25 % 24 = 1)
    tx = _make_transaction(step=25)
    features = engineer_features(tx)
    assert features["hour_of_day"] == 1


def test_balance_diff_orig():
    # Sender had 200k, now has 100k — diff = 100k
    tx = _make_transaction(
        oldbalanceOrg=200000.0,
        newbalanceOrig=100000.0,
    )
    features = engineer_features(tx)
    assert features["balance_diff_orig"] == 100000.0


def test_error_balance_orig_legitimate_transaction():
    # For a legitimate transaction the error should be close to 0
    # Sender pays exactly amount: old=200k, new=100k, amount=100k
    # error = (200k - 100k) - 100k = 0
    tx = _make_transaction(
        amount=100000.0,
        oldbalanceOrg=200000.0,
        newbalanceOrig=100000.0,
    )
    features = engineer_features(tx)
    assert features["error_balance_orig"] == pytest.approx(0.0)


def test_dest_zero_before_flag():
    # Fresh recipient account — strong fraud signal
    tx = _make_transaction(oldbalanceDest=0.0)
    features = engineer_features(tx)
    assert features["dest_balance_zero_before"] == 1


def test_orig_balance_zeroed_flag():
    # Account completely drained — account takeover signal
    tx = _make_transaction(newbalanceOrig=0.0)
    features = engineer_features(tx)
    assert features["orig_balance_zeroed"] == 1


def test_amount_ratio_high_for_full_drain():
    # Sending entire balance: amount = 200k, old_balance = 200k
    # ratio = 200k / (200k + 1) ≈ 1.0 (nearly 100% of balance)
    tx = _make_transaction(
        amount=200000.0,
        oldbalanceOrg=200000.0,
    )
    features = engineer_features(tx)
    assert features["amount_ratio_orig"] > 0.99