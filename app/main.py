# app/main.py
"""
FastAPI application entry point.

Lifespan pattern:
- Code before `yield` runs at startup
- Code after `yield` runs at shutdown

This is the correct FastAPI pattern for managing resources
like database connections, ML models, and Kafka producers.
The deprecated @app.on_event("startup") approach is NOT used.

Documentation:
https://fastapi.tiangolo.com/advanced/events/
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, transactions
from app.config import APP_ENV
from app.core.fraud_scorer import load_model as load_fraud_model
from app.core.anomaly_detector import load_model as load_anomaly_model
from app.streaming.producer import initialise_producer, shutdown_producer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application startup and shutdown.

    Startup order matters:
    1. Load fraud model first (also initialises SHAP explainer)
    2. Load anomaly model second
    3. Initialise Kafka producer last
       (producer needs to be ready before routes can use it)

    Shutdown order:
    1. Flush Kafka producer (ensure no messages are lost)
    """
    # ── STARTUP ───────────────────────────────────────────────────────────
    logger.info(f"Starting Fraud Detection Service | env={APP_ENV}")

    fraud_loaded = load_fraud_model()
    if fraud_loaded:
        logger.info("✅ Fraud model ready")
    else:
        logger.warning(
            "⚠️  Fraud model not found. "
            "Run: python scripts/train_fraud_model.py"
        )

    anomaly_loaded = load_anomaly_model()
    if anomaly_loaded:
        logger.info("✅ Anomaly model ready")
    else:
        logger.warning(
            "⚠️  Anomaly model not found. "
            "Run: python scripts/train_anomaly_model.py"
        )

    kafka_ready = initialise_producer()
    if kafka_ready:
        logger.info("✅ Kafka producer ready")
    else:
        logger.warning(
            "⚠️  Kafka producer failed to initialise. "
            "Is Kafka running? Start with: "
            "kafka-server-start.sh ~/kafka/config/kraft/server.properties"
        )

    logger.info("Fraud Detection Service ready to receive transactions")

    yield

    # ── SHUTDOWN ──────────────────────────────────────────────────────────
    logger.info("Shutting down Fraud Detection Service...")
    shutdown_producer()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Real-Time Fraud Detection & Anomaly Pipeline",
        description=(
            "Dual-model fraud detection system using XGBoost + Isolation Forest. "
            "Every transaction is scored, explained with SHAP, and published "
            "to Kafka for downstream processing."
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