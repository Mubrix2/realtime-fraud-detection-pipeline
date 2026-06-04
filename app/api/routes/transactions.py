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
    transaction_data = request.model_dump()

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
    Score a transaction synchronously and store results.

    This function exists for the demo — in production, scoring
    happens in the Kafka consumer (Phase 7) after the message
    is consumed from the raw-transactions topic.

    In the full architecture:
    1. /submit publishes to Kafka and returns 202
    2. Kafka consumer picks up the message
    3. Consumer scores and publishes to fraud-results topic
    4. Results consumer stores in Redis/PostgreSQL
    5. /results/{id} reads from Redis/PostgreSQL
    """
    import time
    start = time.time()

    try:
        # Convert transaction to internal format for feature engineering
        internal = {
            "step": transaction_data.get("step", 1),
            "type": transaction_data.get("type", "TRANSFER"),
            "amount": transaction_data.get("amount", 0.0),
            "oldbalanceOrg": transaction_data.get("oldbalance_org", 0.0),
            "newbalanceOrig": transaction_data.get("newbalance_orig", 0.0),
            "oldbalanceDest": transaction_data.get("oldbalance_dest", 0.0),
            "newbalanceDest": transaction_data.get("newbalance_dest", 0.0),
        }

        features = engineer_features(internal)
        fraud_result = fraud_score(features)
        anomaly_result = anomaly_score(features)
        explanation = explain_transaction(features, top_n=5)
        explanation_text = format_explanation_text(explanation)

        elapsed_ms = (time.time() - start) * 1000

        _results_store[transaction_id] = {
            "transaction_id": transaction_id,
            "fraud_probability": fraud_result["fraud_probability"],
            "is_fraud": fraud_result["is_fraud"],
            "risk_level": fraud_result["risk_level"],
            "is_anomalous": anomaly_result["is_anomalous"],
            "anomaly_severity": anomaly_result["anomaly_severity"],
            "top_reasons": explanation["top_reasons"],
            "explanation_text": explanation_text,
            "scored_at": datetime.now(timezone.utc),
            "processing_time_ms": round(elapsed_ms, 2),
        }

        logger.info(
            f"Scored {transaction_id}: "
            f"fraud={fraud_result['fraud_probability']:.3f} "
            f"({fraud_result['risk_level']}) | "
            f"anomaly={anomaly_result['anomaly_severity']} | "
            f"{elapsed_ms:.1f}ms"
        )

    except Exception as e:
        logger.error(f"Scoring failed for {transaction_id}: {e}")