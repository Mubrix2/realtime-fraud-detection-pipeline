# Dockerfile
# Builds the FastAPI fraud detection service.
# Includes trained ML models — run training scripts before building.
#
# Multi-stage is not used here because we have no build artifacts.
# Python dependencies are installed, source code is copied, done.

FROM python:3.12-slim

WORKDIR /app

# System dependencies for confluent-kafka (needs librdkafka)
# and for XGBoost/SHAP (need gcc for compilation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install Python dependencies first (Docker layer caching)
# When only source code changes, this layer is not rebuilt
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY app/ ./app/

# Verify models exist — fail fast if training was skipped
# This gives a clear error at build time rather than a runtime crash
RUN python -c "
import sys
from pathlib import Path
fraud_model = Path('app/models/fraud_model.pkl')
anomaly_model = Path('app/models/anomaly_model.pkl')
if not fraud_model.exists():
    print('ERROR: app/models/fraud_model.pkl not found.')
    print('Run: python scripts/train_fraud_model.py')
    sys.exit(1)
if not anomaly_model.exists():
    print('ERROR: app/models/anomaly_model.pkl not found.')
    print('Run: python scripts/train_anomaly_model.py')
    sys.exit(1)
print('Models verified.')
"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]