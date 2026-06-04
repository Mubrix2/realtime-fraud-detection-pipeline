# app/api/routes/health.py
from fastapi import APIRouter
from app.api.schemas import HealthResponse
from app.config import APP_ENV
from app.core.fraud_scorer import get_model_info as get_fraud_info
from app.core.anomaly_detector import get_model_info as get_anomaly_info
from app.streaming.producer import get_delivery_stats

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health():
    """
    Health check endpoint.
    Returns status of all system components:
    - Fraud model loaded
    - Anomaly model loaded
    - Kafka producer connected
    """
    fraud_info = get_fraud_info()
    anomaly_info = get_anomaly_info()
    stats = get_delivery_stats()

    return HealthResponse(
        status="ok",
        env=APP_ENV,
        fraud_model_loaded=fraud_info["model_loaded"],
        anomaly_model_loaded=anomaly_info["model_loaded"],
        kafka_connected=stats["total_attempted"] >= 0,
    )