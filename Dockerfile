FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libssl-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

RUN python -c "
import sys
from pathlib import Path
models = ['fraud_model.pkl', 'anomaly_model.pkl', 'scaler.pkl']
missing = [m for m in models if not Path(f'app/models/{m}').exists()]
if missing:
    print(f'ERROR: Missing models: {missing}')
    print('Run training scripts first:')
    print('  python scripts/prepare_data.py')
    print('  python scripts/train_fraud_model.py')
    print('  python scripts/train_anomaly_model.py')
    sys.exit(1)
print('All models verified.')
"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]