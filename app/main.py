# app/main.py
import sys
from pathlib import Path
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, transactions
from app.config import APP_ENV
from app.core.anomaly_detector import load_model as load_anomaly_model
from app.core.fraud_scorer import load_model as load_fraud_model
from app.streaming.producer import initialise_producer, shutdown_producer

# Consumer imports REMOVED — consumer runs as a separate process

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Allow imports from project root
sys.path.append(str(Path(__file__).resolve().parent.parent))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── STARTUP ───────────────────────────────────────────────────────────
    logger.info(f"Starting Fraud Detection API | env={APP_ENV}")

    # API still loads models for the synchronous demo scoring endpoint
    # (GET /results/{id} scores synchronously as fallback)
    fraud_loaded = load_fraud_model()
    logger.info(
        "✅ Fraud model ready"
        if fraud_loaded
        else "⚠️  Fraud model not found"
    )

    anomaly_loaded = load_anomaly_model()
    logger.info(
        "✅ Anomaly model ready"
        if anomaly_loaded
        else "⚠️  Anomaly model not found"
    )

    kafka_ready = initialise_producer()
    logger.info(
        "✅ Kafka producer ready"
        if kafka_ready
        else "⚠️  Kafka unavailable"
    )

    # Consumer is now a SEPARATE PROCESS
    # It reads from raw-transactions and writes to fraud-results
    # It does not start here — see docker-compose.yml consumer service
    logger.info(
        "ℹ️  Consumer runs as a separate service. "
        "Start it with: python app/consumer_main.py"
    )

    logger.info("🚀 Fraud Detection API ready")

    yield

    # ── SHUTDOWN ──────────────────────────────────────────────────────────
    logger.info("Shutting down API...")
    shutdown_producer()
    logger.info("API shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Real-Time Fraud Detection & Anomaly Pipeline",
        description=(
            "Dual-model fraud detection using XGBoost + Isolation Forest. "
            "Event-driven architecture with Apache Kafka. "
            "Consumer runs as a separate microservice."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(transactions.router, prefix="/api/v1")

    return app


app = create_app()