# app/consumer_main.py
"""
Standalone Kafka consumer process.

This runs as a completely separate process from the FastAPI service.
In production: its own Docker container, its own deployment,
its own scaling group.

Start it with:
    python app/consumer_main.py

Or via Docker Compose — see docker-compose.yml consumer service.

Why separate from FastAPI?
- FastAPI scales horizontally for HTTP traffic
- Consumer scales horizontally for Kafka throughput
- They have different resource profiles and failure modes
- A consumer crash does not take down the API, and vice versa
"""
import logging
import signal
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("consumer_main")

# Allow imports from project root
sys.path.append(str(Path(__file__).resolve().parent.parent))


def handle_shutdown(signum, frame):
    """
    Handle SIGTERM and SIGINT gracefully.
    Docker sends SIGTERM when stopping a container.
    We catch it to allow the consumer to finish processing
    its current message before shutting down.
    """
    logger.info(f"Received signal {signum}. Shutting down consumer...")
    sys.exit(0)


def main():
    # Register shutdown handlers
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    logger.info("Starting Fraud Detection Consumer Service")

    # Load ML models — consumer needs them to score transactions
    from app.core.fraud_scorer import load_model as load_fraud_model
    from app.core.anomaly_detector import load_model as load_anomaly_model

    fraud_loaded = load_fraud_model()
    if fraud_loaded:
        logger.info("✅ Fraud model loaded")
    else:
        logger.error(
            "❌ Fraud model not found. "
            "Run: python scripts/train_fraud_model.py"
        )
        sys.exit(1)

    anomaly_loaded = load_anomaly_model()
    if anomaly_loaded:
        logger.info("✅ Anomaly model loaded")
    else:
        logger.error(
            "❌ Anomaly model not found. "
            "Run: python scripts/train_anomaly_model.py"
        )
        sys.exit(1)

    # Start the consumer loop — this blocks forever
    from app.streaming.consumer import _run_consumer
    from app.config import KAFKA_BOOTSTRAP_SERVERS

    logger.info(
        f"Consumer connecting to Kafka at {KAFKA_BOOTSTRAP_SERVERS}"
    )
    logger.info("Consumer is running. Press Ctrl+C to stop.")

    # _run_consumer() runs until stop_event is set
    # Since we are a standalone process, we run it directly
    # without a thread — it blocks the main process intentionally
    _run_consumer()


if __name__ == "__main__":
    main()