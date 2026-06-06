# realtime-fraud-detection-pipeline
# Real-Time Fraud Detection & Anomaly Pipeline

A production-grade, event-driven fraud detection microservice for
financial transactions. Every transaction is scored by two independent
AI models, explained with SHAP values for compliance, and results are
streamed through Apache Kafka — all within milliseconds.

**Live Demo:** [your-dashboard.vercel.app](https://your-dashboard.vercel.app)
**API Docs:** [your-api.onrender.com/docs](https://your-api.onrender.com/docs)

---

## What It Does

A transaction is submitted to the API. Within milliseconds:

1. **FastAPI** validates the payload and publishes to Kafka
2. **Kafka Consumer** reads the transaction from `raw-transactions`
3. **XGBoost classifier** scores known fraud patterns (supervised)
4. **Isolation Forest** detects novel anomalies (unsupervised)
5. **SHAP explainer** explains exactly why the transaction was flagged
6. Results published to `fraud-results` topic and stored for the API
7. **React dashboard** displays the result with a live SHAP bar chart

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT                                    │
│              React Dashboard / API Client                        │
└───────────────────────────┬─────────────────────────────────────┘
                            │ POST /api/v1/transactions/submit
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Service                             │
│  • Pydantic v2 validation (extra=forbid security)               │
│  • Publishes to Kafka raw-transactions topic                     │
│  • Returns HTTP 202 Accepted immediately                         │
└───────────────────────────┬─────────────────────────────────────┘
                            │ produce()
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│               Apache Kafka (KRaft mode)                          │
│  Topic: raw-transactions (3 partitions)                          │
│  Topic: fraud-results    (3 partitions)                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │ consume()
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Fraud Consumer Thread                          │
│                                                                  │
│  Feature Engineering (16 features from transaction fields)       │
│         │                                                        │
│         ├── XGBoost Classifier ──────► fraud probability 0–1    │
│         │   (trained on PaySim, SMOTE balanced)                  │
│         │                                                        │
│         ├── Isolation Forest ─────────► anomaly score           │
│         │   (trained on legitimate transactions only)            │
│         │                                                        │
│         └── SHAP TreeExplainer ────────► top 5 reasons          │
│             (compliance-ready explanation)                        │
│                                                                  │
│  → Publishes to fraud-results topic                              │
│  → Stores in results store for REST API                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Why Two Models

**XGBoost (supervised):** Trained on labelled fraud examples.
Catches known fraud patterns with high confidence.
Cannot catch fraud patterns it has never seen.

**Isolation Forest (unsupervised):** Trained on legitimate
transactions only — it learns what normal looks like.
Flags anything statistically unusual, including novel fraud
patterns that the supervised model has never encountered.

Together: maximum recall. A transaction is flagged if either
model signals risk.

---

## SHAP Explainability

Every flagged transaction includes a compliance-ready explanation:

```
HIGH RISK: Sender account completely emptied by this transaction
           — increased fraud risk significantly.

HIGH RISK: Recipient account had zero balance before transaction
           — typical pattern in mule accounts.

MEDIUM RISK: Transaction amount is 8.3x sender's average
             — increased fraud risk.
```

This satisfies:
- **GDPR Article 22** — right to explanation for automated decisions
- **CBN AI Guidelines** — explainability requirement for financial AI
- **US Fair Credit Reporting Act** — adverse action explanation

---

## Model Performance

Evaluated on 20% held-out test set (real-world class distribution):

| Metric | XGBoost | Isolation Forest |
|---|---|---|
| Fraud Recall | 98.2% | 71.4% |
| Fraud Precision | 94.7% | 8.3% |
| F1 Score | 0.964 | 0.153 |
| ROC-AUC | 0.998 | — |

**Combined strategy (either flags):**
Recall: 98.9% — catches 989 in every 1000 fraudulent transactions.

Note: Isolation Forest precision is low by design — it flags unusual
transactions, not specifically fraud. Its value is catching novel fraud
patterns the supervised model misses entirely.

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Streaming | Apache Kafka 3.8.1 (KRaft) | Event-driven transaction pipeline |
| Kafka Client | confluent-kafka-python | Sub-millisecond C library bindings |
| ML — Supervised | XGBoost | Fraud classification on tabular data |
| ML — Unsupervised | Isolation Forest | Novel anomaly detection |
| Explainability | SHAP TreeExplainer | Compliance-ready feature attribution |
| Class Balance | SMOTE (imbalanced-learn) | Synthetic minority oversampling |
| Backend | FastAPI + Pydantic v2 | High-performance async REST API |
| Frontend | React + Vite + Recharts | Live fraud monitoring dashboard |
| Styling | Tailwind CSS | Utility-first component styling |
| Containers | Docker + Docker Compose | Full system orchestration |
| Deployment — API | Render | FastAPI via Docker |
| Deployment — Frontend | Vercel | React/Vite static hosting |
| Deployment — Kafka | Upstash Kafka | Serverless managed Kafka |

---

## Key Engineering Decisions

**Why Kafka instead of direct API calls?**
Kafka decouples transaction submission from fraud scoring.
The payment system does not wait for ML inference — it submits
and continues. Fraud scoring happens asynchronously. This pattern
handles thousands of concurrent transactions without the API
becoming a bottleneck.

**Why SMOTE only on training data?**
Applying SMOTE to test data would create synthetic fraud examples
that inflate recall metrics artificially. The test set uses real-world
class distribution (~0.3% fraud) to give honest performance numbers.

**Why Pydantic `extra="forbid"`?**
Any field not in the schema is rejected at the API boundary.
This prevents parameter pollution and field injection attacks
before they reach the Kafka topic or ML pipeline.

**Why a background thread instead of a separate process?**
For this portfolio project, the consumer runs as a daemon thread
inside the FastAPI process. In production, it would be a separate
microservice — its own Docker container, auto-scaling group, and
deployment pipeline. The Kafka integration is identical either way.

---

## Project Structure

```
ai-fraud-detection-pipeline/
├── app/
│   ├── api/routes/
│   │   ├── transactions.py  # submit, results, recent, stats endpoints
│   │   └── health.py
│   ├── api/schemas.py       # Pydantic v2 models with extra=forbid
│   ├── core/
│   │   ├── feature_engineer.py  # 16 fraud-signal features
│   │   ├── fraud_scorer.py      # XGBoost inference singleton
│   │   ├── anomaly_detector.py  # Isolation Forest inference
│   │   └── explainer.py         # SHAP TreeExplainer
│   ├── models/              # Trained .pkl files (gitignored)
│   ├── services/
│   │   └── detection_service.py # Pipeline orchestration
│   ├── streaming/
│   │   ├── producer.py      # Kafka producer with delivery callback
│   │   └── consumer.py      # Consumer thread with thread-safe store
│   └── main.py
├── data/                    # Raw and processed data (gitignored)
├── notebooks/               # Exploratory analysis
├── scripts/
│   ├── prepare_data.py      # SMOTE, scaling, train/test split
│   ├── train_fraud_model.py # XGBoost training + threshold search
│   ├── train_anomaly_model.py
│   └── evaluate_models.py   # Combined model comparison
├── tests/                   # 30+ unit tests
├── frontend/                # React + Vite dashboard
├── Dockerfile
├── Dockerfile.frontend
├── docker-compose.yml
└── nginx.conf
```

---

## Running Locally

### Prerequisites
- Python 3.12+
- Node.js 20+
- Java 17+ (for Kafka)
- Kafka 3.8.1 installed in WSL2

### 1 — Train the models

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Download PaySim to data/raw/paysim.csv from:
# https://www.kaggle.com/datasets/ntnu-testimon/paysim1

python scripts/prepare_data.py
python scripts/train_fraud_model.py
python scripts/train_anomaly_model.py
```

### 2 — With Docker Compose (recommended)

```bash
docker compose build
docker compose up
```

- API: http://localhost:8000/docs
- Dashboard: http://localhost:80

### 3 — Without Docker

**Terminal 1 — Kafka:**
```bash
kafka-server-start.sh ~/kafka/config/kraft/server.properties
```

**Terminal 2 — FastAPI:**
```bash
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**Terminal 3 — React:**
```bash
cd frontend && npm install && npm run dev
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/transactions/submit` | Submit transaction for screening |
| `GET` | `/api/v1/transactions/results/{id}` | Poll for fraud result |
| `GET` | `/api/v1/transactions/recent` | Last N transactions for dashboard |
| `GET` | `/api/v1/transactions/stats` | System processing statistics |
| `GET` | `/health` | Component health check |

---

## Running Tests

```bash
python -m pytest tests/ -v
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | ✅ | `localhost:9092` | Kafka broker address |
| `KAFKA_TRANSACTIONS_TOPIC` | ❌ | `raw-transactions` | Input topic |
| `KAFKA_RESULTS_TOPIC` | ❌ | `fraud-results` | Output topic |
| `FRAUD_THRESHOLD` | ❌ | `0.7` | Fraud classification threshold |
| `ANOMALY_THRESHOLD` | ❌ | `-0.1` | Isolation Forest threshold |

---

## Author

**Mubarak Olalekan Oladipo**
AI Software Engineer — Fintech AI Engineer
[GitHub](https://github.com/Mubrix2) · [LinkedIn](https://linkedin.com/in/YOUR_PROFILE)