# tests/test_consumer.py
import pytest
import json
from unittest.mock import MagicMock, patch
from app.streaming.consumer import (
    store_result,
    get_result,
    get_results_store,
    get_stats,
    _results_store,
    _stats,
    stop_event,
)


def setup_function():
    """Clear state before each test."""
    _results_store.clear()
    _stats["messages_consumed"] = 0
    _stats["messages_flagged"] = 0
    _stats["messages_failed"] = 0
    stop_event.clear()


# ── Store operations ───────────────────────────────────────────────────────────

def test_store_and_retrieve_result():
    assessment = {
        "transaction_id": "TXN-001",
        "fraud_probability": 0.95,
        "is_fraud": True,
        "is_flagged": True,
        "scored_at": "2026-05-01T10:00:00",
    }
    store_result("TXN-001", assessment)
    retrieved = get_result("TXN-001")
    assert retrieved is not None
    assert retrieved["fraud_probability"] == 0.95


def test_get_result_returns_none_for_unknown():
    result = get_result("DOES-NOT-EXIST")
    assert result is None


def test_get_results_store_returns_copy():
    """get_results_store returns a copy — modifying it does not affect store."""
    store_result("TXN-A", {"transaction_id": "TXN-A"})
    store = get_results_store()
    store["injected"] = "malicious"
    assert "injected" not in _results_store


def test_results_store_capped_at_1000():
    """Memory safety — store should not grow beyond 1000 entries."""
    for i in range(1005):
        store_result(f"TXN-{i:04d}", {"transaction_id": f"TXN-{i:04d}"})
    assert len(_results_store) <= 1000


def test_oldest_entry_evicted_when_cap_reached():
    """When cap is reached, the oldest entry is removed first."""
    for i in range(1001):
        store_result(f"TXN-{i:04d}", {"transaction_id": f"TXN-{i:04d}"})
    # TXN-0000 was inserted first — should be evicted
    assert get_result("TXN-0000") is None
    # TXN-1000 was inserted last — should still be there
    assert get_result("TXN-1000") is not None


# ── Stats ──────────────────────────────────────────────────────────────────────

def test_stats_initial_state():
    stats = get_stats()
    assert stats["messages_consumed"] == 0
    assert stats["messages_flagged"] == 0
    assert stats["messages_failed"] == 0
    assert "consumer_running" in stats
    assert "results_stored" in stats


def test_stats_consumer_running_reflects_stop_event():
    """
    consumer_running should be True when stop_event is not set,
    False when it is set.
    """
    stop_event.clear()
    assert get_stats()["consumer_running"] is True

    stop_event.set()
    assert get_stats()["consumer_running"] is False


# ── Message processing ─────────────────────────────────────────────────────────

@patch("app.streaming.consumer.assess_transaction")
@patch("app.streaming.consumer._publish_result")
def test_process_message_increments_consumed(mock_publish, mock_assess):
    from app.streaming.consumer import _process_message

    mock_assess.return_value = {
        "transaction_id": "TXN-TEST",
        "fraud_probability": 0.9,
        "is_fraud": True,
        "is_flagged": True,
        "scored_at": "2026-05-01T10:00:00",
        "top_reasons": [],
        "explanation_text": "Test",
    }

    mock_msg = MagicMock()
    mock_msg.value.return_value = json.dumps({
        "data": {
            "transaction_id": "TXN-TEST",
            "type": "TRANSFER",
            "amount": 100000,
            "step": 5,
        }
    }).encode("utf-8")
    mock_msg.key.return_value = b"TXN-TEST"
    mock_msg.error.return_value = None

    _process_message(mock_msg, MagicMock())

    assert _stats["messages_consumed"] == 1
    assert _stats["messages_flagged"] == 1


@patch("app.streaming.consumer.assess_transaction")
@patch("app.streaming.consumer._publish_result")
def test_process_message_stores_result(mock_publish, mock_assess):
    """Processed message should appear in results store."""
    from app.streaming.consumer import _process_message

    mock_assess.return_value = {
        "transaction_id": "TXN-STORE",
        "fraud_probability": 0.3,
        "is_fraud": False,
        "is_flagged": False,
        "scored_at": "2026-05-01T10:00:00",
        "top_reasons": [],
        "explanation_text": "Low risk",
    }

    mock_msg = MagicMock()
    mock_msg.value.return_value = json.dumps({
        "data": {"transaction_id": "TXN-STORE", "type": "PAYMENT"}
    }).encode("utf-8")
    mock_msg.key.return_value = b"TXN-STORE"
    mock_msg.error.return_value = None

    _process_message(mock_msg, MagicMock())

    result = get_result("TXN-STORE")
    assert result is not None
    assert result["fraud_probability"] == 0.3


@patch("app.streaming.consumer.assess_transaction")
@patch("app.streaming.consumer._publish_result")
def test_non_flagged_message_does_not_increment_flagged_count(
    mock_publish, mock_assess
):
    from app.streaming.consumer import _process_message

    mock_assess.return_value = {
        "transaction_id": "TXN-LEGIT",
        "fraud_probability": 0.05,
        "is_fraud": False,
        "is_flagged": False,  # ← not flagged
        "scored_at": "2026-05-01T10:00:00",
        "top_reasons": [],
        "explanation_text": "Low risk",
    }

    mock_msg = MagicMock()
    mock_msg.value.return_value = json.dumps({
        "data": {"transaction_id": "TXN-LEGIT"}
    }).encode("utf-8")
    mock_msg.key.return_value = b"TXN-LEGIT"
    mock_msg.error.return_value = None

    _process_message(mock_msg, MagicMock())

    assert _stats["messages_consumed"] == 1
    assert _stats["messages_flagged"] == 0  # ← not incremented


def test_process_message_handles_invalid_json():
    """Bad JSON must not crash the consumer."""
    from app.streaming.consumer import _process_message

    mock_msg = MagicMock()
    mock_msg.value.return_value = b"not valid json {"
    mock_msg.error.return_value = None

    _process_message(mock_msg, MagicMock())

    assert _stats["messages_failed"] == 1
    assert _stats["messages_consumed"] == 0


def test_process_message_handles_unexpected_exception():
    """Any unexpected error must not crash the consumer."""
    from app.streaming.consumer import _process_message

    mock_msg = MagicMock()
    # value() raises an unexpected error
    mock_msg.value.side_effect = RuntimeError("Unexpected error")
    mock_msg.error.return_value = None

    _process_message(mock_msg, MagicMock())

    assert _stats["messages_failed"] == 1