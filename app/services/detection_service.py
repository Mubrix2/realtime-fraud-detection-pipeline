# app/services/detection_service.py
"""
Fraud detection orchestration service.

This is the brain of the pipeline. It coordinates:
1. Feature engineering
2. XGBoost fraud classification
3. Isolation Forest anomaly detection
4. SHAP explainability

Design principle: this service knows nothing about Kafka,
FastAPI, or any transport layer. It takes a transaction dict
and returns a result dict. Pure business logic.

This makes it testable without any infrastructure running.
"""
import sys
from pathlib import Path
import logging
import time
from datetime import datetime, timezone

from app.core.anomaly_detector import score_transaction as anomaly_score
from app.core.explainer import explain_transaction, format_explanation_text
from app.core.feature_engineer import engineer_features
from app.core.fraud_scorer import score_transaction as fraud_score

logger = logging.getLogger(__name__)

# Allow imports from project root
sys.path.append(str(Path(__file__).resolve().parent.parent))


SCOREABLE_TYPES = {"TRANSFER", "CASH_OUT"}


def _map_transaction_fields(raw: dict) -> dict:
    """
    Map transaction fields to the internal format expected
    by feature_engineer.engineer_features().

    The API uses snake_case (oldbalance_org).
    The PaySim dataset uses camelCase (oldbalanceOrg).
    The feature engineer expects camelCase.

    This mapping layer means the API schema can change without
    touching the feature engineering code.
    """
    return {
        "step": raw.get("step", raw.get("step", 1)),
        "type": raw.get("type", "TRANSFER"),
        "amount": float(raw.get("amount", 0.0)),
        "oldbalanceOrg": float(
            raw.get("oldbalanceOrg",
            raw.get("oldbalance_org", 0.0))
        ),
        "newbalanceOrig": float(
            raw.get("newbalanceOrig",
            raw.get("newbalance_orig", 0.0))
        ),
        "oldbalanceDest": float(
            raw.get("oldbalanceDest",
            raw.get("oldbalance_dest", 0.0))
        ),
        "newbalanceDest": float(
            raw.get("newbalanceDest",
            raw.get("newbalance_dest", 0.0))
        ),
    }


def assess_transaction(
    transaction_id: str,
    transaction_data: dict,
    top_n_explanations: int = 5,
) -> dict:
    """
    Run the complete fraud assessment pipeline on one transaction.

    Steps:
    1. Map and validate input fields
    2. Engineer features (16 derived features)
    3. XGBoost fraud classification
    4. Isolation Forest anomaly detection
    5. SHAP explanation (top N features)
    6. Format plain English explanation

    Args:
        transaction_id: Unique identifier for this transaction
        transaction_data: Raw transaction fields
        top_n_explanations: How many SHAP reasons to include

    Returns:
        Complete fraud assessment dict ready for storage and API response

    This function never raises — if any component fails,
    it logs the error and returns a partial result.
    The transaction must be scored and stored even if SHAP fails.
    """
    start_time = time.perf_counter()

     # ── Type guard ────────────────────────────────────────────────────────
    # This model was trained exclusively on TRANSFER and CASH_OUT
    # transactions because PaySim fraud only occurs in those types.
    # Scoring PAYMENT, CASH_IN, or DEBIT produces out-of-distribution
    # results — the model has never seen is_transfer=0 AND is_cashout=0.
    # We return a safe approval for non-scoreable types.
    transaction_type = str(
        transaction_data.get("type", "")
    ).upper()

    if transaction_type not in SCOREABLE_TYPES:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"✅ AUTO-APPROVED | {transaction_id} | "
            f"type={transaction_type} | not in model scope | "
            f"{elapsed_ms:.1f}ms"
        )
        return {
            "transaction_id": transaction_id,
            "transaction": {
                "type": transaction_type,
                "amount": transaction_data.get("amount"),
                "step": transaction_data.get("step"),
            },
            "fraud_probability": 0.0,
            "is_fraud": False,
            "action": "APPROVE",
            "risk_level": "LOW",
            "anomaly_score": 0.0,
            "is_anomalous": False,
            "anomaly_severity": "NORMAL",
            "is_flagged": False,
            "top_reasons": [],
            "explanation_text": (
                f"{transaction_type} transactions are outside this "
                f"model's scope. Model trained on TRANSFER and "
                f"CASH_OUT only."
            ),
            "explanation_available": False,
            "scored_at": datetime.now(timezone.utc).isoformat(),
            "processing_time_ms": round(elapsed_ms, 2),
            "models_available": {
                "fraud_model": True,
                "anomaly_model": True,
                "shap": False,
            },
            "note": "Auto-approved — transaction type outside model scope",
        }

    try:
        # ── Step 1: Field mapping ──────────────────────────────────────────
        internal = _map_transaction_fields(transaction_data)

        # ── Step 2: Feature engineering ───────────────────────────────────
        features = engineer_features(internal)

        # ── Step 3: Fraud classification ──────────────────────────────────
        fraud_result = fraud_score(features)
        logger.debug(
            f"{transaction_id} | fraud_prob="
            f"{fraud_result['fraud_probability']:.4f} | "
            f"level={fraud_result['risk_level']}"
        )

        # ── Step 4: Anomaly detection ──────────────────────────────────────
        anomaly_result = anomaly_score(features)
        logger.debug(
            f"{transaction_id} | anomaly_score="
            f"{anomaly_result['anomaly_score']:.4f} | "
            f"severity={anomaly_result['anomaly_severity']}"
        )

        # ── Step 5: SHAP explanation ───────────────────────────────────────
        explanation = explain_transaction(features, top_n=top_n_explanations)

        # ── Step 6: Plain English text ─────────────────────────────────────
        explanation_text = format_explanation_text(explanation)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # ── Combine verdict ────────────────────────────────────────────────
        # A transaction is flagged if EITHER model signals risk.
        # This maximises recall — we prefer to investigate a legitimate
        # transaction than to miss real fraud.
        combined_flag = (
            fraud_result["is_fraud"] or anomaly_result["is_anomalous"]
        )

        assessment = {
            "transaction_id": transaction_id,
            # Original transaction fields for display
            "transaction": {
                "type": transaction_data.get("type"),
                "amount": transaction_data.get("amount"),
                "step": transaction_data.get("step"),
            },
            # XGBoost results
            "fraud_probability": fraud_result["fraud_probability"],
            "is_fraud": fraud_result["is_fraud"],
            "risk_level": fraud_result["risk_level"],
            # Isolation Forest results
            "anomaly_score": anomaly_result["anomaly_score"],
            "is_anomalous": anomaly_result["is_anomalous"],
            "anomaly_severity": anomaly_result["anomaly_severity"],
            # Combined verdict
            "is_flagged": combined_flag,
            # SHAP explanation
            "top_reasons": explanation.get("top_reasons", []),
            "explanation_text": explanation_text,
            "explanation_available": explanation.get(
                "explanation_available", False
            ),
            # Metadata
            "scored_at": datetime.now(timezone.utc).isoformat(),
            "processing_time_ms": round(elapsed_ms, 2),
            "models_available": {
                "fraud_model": fraud_result["model_available"],
                "anomaly_model": anomaly_result["model_available"],
                "shap": explanation.get("explanation_available", False),
            },
        }

        log_level = logging.WARNING if combined_flag else logging.INFO
        logger.log(
            log_level,
            f"{'🚨 FLAGGED' if combined_flag else '✅ CLEARED'} | "
            f"{transaction_id} | "
            f"fraud={fraud_result['fraud_probability']:.3f} "
            f"({fraud_result['risk_level']}) | "
            f"anomaly={anomaly_result['anomaly_severity']} | "
            f"{elapsed_ms:.1f}ms"
        )

        return assessment

    except Exception as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.error(
            f"Assessment failed for {transaction_id}: {e}",
            exc_info=True,
        )
        # Return a safe partial result — never crash the consumer
        return {
            "transaction_id": transaction_id,
            "transaction": transaction_data,
            "fraud_probability": 0.0,
            "is_fraud": False,
            "risk_level": "UNKNOWN",
            "anomaly_score": 0.0,
            "is_anomalous": False,
            "anomaly_severity": "UNKNOWN",
            "is_flagged": False,
            "top_reasons": [],
            "explanation_text": f"Assessment failed: {str(e)}",
            "explanation_available": False,
            "scored_at": datetime.now(timezone.utc).isoformat(),
            "processing_time_ms": round(elapsed_ms, 2),
            "error": str(e),
        }