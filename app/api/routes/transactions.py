# app/api/routes/transactions.py
"""
Transaction submission endpoints.

Two endpoints:
1. POST /submit — receive a transaction, publish to Kafka, return immediately
2. GET /results/{transaction_id} — poll for fraud scoring result

The separation between submission and results reflects the async
nature of the system. The client does not wait for fraud scoring.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.api.schemas import (
    FraudResultResponse,
    TransactionRequest,
    TransactionResponse,
)
from app.core.feature_engineer import engineer_features
from app.core.fraud_scorer import score_transaction as fraud_score
from app.core.anomaly_detector import score_transaction as anomaly_score
from app.core.explainer import explain_transaction, format_explanation_text
from app.streaming.producer import publish_transaction

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/transactions", tags=["Transactions"])

# In-memory results store for demo purposes
# In production this would be Redis or PostgreSQL
_results_store: dict[str, dict] = {}


@router.post(
    "/submit",
    response_model=TransactionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a transaction for fraud screening",
)
async def submit_transaction(request: TransactionRequest):
    """
    Submit a transaction for asynchronous fraud screening.

    Returns HTTP 202 Accepted — not 200 OK.
    202 means: "I have received your request and will process it."
    200 means: "I have processed your request and here is the result."

    The distinction matters: fraud scoring has not happened yet
    when this endpoint responds. Using 202 communicates this correctly.
    """
    transaction_data = request.model_dump(mode="json")

    # Publish to Kafka
    result = publish_transaction(transaction_data)

    if result["status"] == "failed":
        logger.error(
            f"Failed to publish {request.transaction_id}: {result['error']}"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Message broker unavailable: {result['error']}",
        )

    # Also score synchronously for the demo results endpoint
    # In production, this would happen in the Kafka consumer
    _score_and_store(request.transaction_id, transaction_data)

    return TransactionResponse(
        transaction_id=request.transaction_id,
        status="accepted",
        message=(
            "Transaction submitted for fraud screening. "
            f"Poll /api/v1/transactions/results/{request.transaction_id} "
            "for scoring results."
        ),
        submitted_at=datetime.now(timezone.utc),
    )


@router.get(
    "/results/{transaction_id}",
    response_model=FraudResultResponse,
    summary="Get fraud scoring result for a transaction",
)
async def get_results(transaction_id: str):
    """
    Retrieve the fraud scoring result for a submitted transaction.

    The client should poll this endpoint after submitting a transaction.
    In production, results would also be pushed via WebSocket.
    """
    if transaction_id not in _results_store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No result found for transaction {transaction_id}. "
                "Either it has not been scored yet or the ID is incorrect."
            ),
        )

    return FraudResultResponse(**_results_store[transaction_id])


def _score_and_store(transaction_id: str, transaction_data: dict) -> None:
    """
    Score a transaction and store the result in the API results store.

    Delegates entirely to assess_transaction() in detection_service.py
    which handles in order:
    1. Transaction type guard (PAYMENT → auto-approve, no ML)
    2. Feature engineering
    3. XGBoost fraud scoring with tiered action system
    4. Isolation Forest anomaly detection
    5. SHAP explainability
    6. Circuit breaker fallback if ML fails
    7. Audit logging

    """
    from app.services.detection_service import assess_transaction

    assessment = assess_transaction(
        transaction_id=transaction_id,
        transaction_data=transaction_data,
    )
    _results_store[transaction_id] = assessment


@router.get(
    "/recent",
    summary="Get recent transaction assessments for dashboard",
)
async def get_recent_transactions(limit: int = 100):
    """
    Returns results from the API's own scoring store.
    Populated by synchronous scoring when transactions are submitted.
    """
    sorted_results = sorted(
        _results_store.values(),
        key=lambda x: x.get("scored_at", ""),
        reverse=True,
    )
    return {
        "transactions": sorted_results[:limit],
        "total": len(_results_store),
    }


@router.get(
    "/stats",
    summary="Get fraud detection system statistics",
)
async def get_system_stats():
    """
    Derives stats directly from the API's results store.
    Always accurate — no dependency on consumer process memory.
    """
    total = len(_results_store)
    flagged = sum(
        1 for r in _results_store.values() if r.get("is_flagged")
    )
    blocked = sum(
        1 for r in _results_store.values() if r.get("action") == "BLOCK"
    )
    challenged = sum(
        1 for r in _results_store.values() if r.get("action") == "CHALLENGE"
    )
    critical = sum(
        1 for r in _results_store.values() if r.get("risk_level") == "CRITICAL"
    )

    return {
        "total_processed": total,
        "total_flagged": flagged,
        "fraud_rate": round(flagged / total, 4) if total > 0 else 0.0,
        "blocked": blocked,
        "challenged": challenged,
        "critical": critical,
    }

@router.get(
    "/results/{transaction_id}",
    response_model=FraudResultResponse,
)
async def get_results(transaction_id: str):
    result = _results_store.get(transaction_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No result found for {transaction_id}",
        )
    return FraudResultResponse(**result)