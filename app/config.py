# app/config.py
"""
Single source of truth for all application configuration.
All values come from environment variables, never hardcoded.
This is Twelve-Factor App Factor III — Config.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ── App ───────────────────────────────────────────────────────────────────────
APP_ENV: str = os.getenv("APP_ENV", "development")

# ── Kafka ─────────────────────────────────────────────────────────────────────
# KAFKA_BOOTSTRAP_SERVERS: address of the Kafka broker
# In development: localhost:9092
# In production: your Upstash Kafka bootstrap server
KAFKA_BOOTSTRAP_SERVERS: str = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
)
KAFKA_TRANSACTIONS_TOPIC: str = os.getenv(
    "KAFKA_TRANSACTIONS_TOPIC", "raw-transactions"
)
KAFKA_RESULTS_TOPIC: str = os.getenv(
    "KAFKA_RESULTS_TOPIC", "fraud-results"
)
KAFKA_CONSUMER_GROUP: str = os.getenv(
    "KAFKA_CONSUMER_GROUP", "fraud-detection-group"
)

# ── Model Thresholds ──────────────────────────────────────────────────────────
# These are business decisions, not technical ones.
# A lower FRAUD_THRESHOLD catches more fraud but flags more legitimate
# transactions (annoying customers). A higher threshold is more lenient.
FRAUD_THRESHOLD: float = float(os.getenv("FRAUD_THRESHOLD", "0.7"))

# Isolation Forest: scores below this value are considered anomalous.
# More negative = more isolated = stronger anomaly signal.
ANOMALY_THRESHOLD: float = float(os.getenv("ANOMALY_THRESHOLD", "-0.1"))

# ── Model Paths ───────────────────────────────────────────────────────────────
FRAUD_MODEL_PATH: Path = BASE_DIR / os.getenv(
    "FRAUD_MODEL_PATH", "app/models/fraud_model.pkl"
)
ANOMALY_MODEL_PATH: Path = BASE_DIR / os.getenv(
    "ANOMALY_MODEL_PATH", "app/models/anomaly_model.pkl"
)
SCALER_PATH: Path = BASE_DIR / os.getenv(
    "SCALER_PATH", "app/models/scaler.pkl"
)