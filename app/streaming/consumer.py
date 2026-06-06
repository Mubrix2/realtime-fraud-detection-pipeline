# app/streaming/consumer.py
"""
Kafka consumer for fraud detection scoring.

Now runs as a standalone process via app/consumer_main.py.
No longer manages its own thread — the process IS the thread.

For the portfolio demo:
- Consumer writes to its own _results_store (separate process memory)
- API reads from its own _results_store (populated by synchronous scoring)
- In production: both would write to a shared Redis or PostgreSQL store
"""
import sys
from pathlib import Path
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Optional


from confluent_kafka import Consumer, KafkaError, Producer

from app.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_CONSUMER_GROUP,
    KAFKA_RESULTS_TOPIC,
    KAFKA_TRANSACTIONS_TOPIC,
)
from app.services.detection_service import assess_transaction


logger = logging.getLogger(__name__)

# Allow imports from project root
sys.path.append(str(Path(__file__).resolve().parent.parent))


_results_store: dict[str, dict] = {}
_results_lock = threading.Lock()

_stats = {
    "messages_consumed": 0,
    "messages_flagged": 0,
    "messages_failed": 0,
    "started_at": None,
}

# Stop event — set by consumer_main.py signal handler for clean shutdown
stop_event = threading.Event()


def get_results_store() -> dict:
    with _results_lock:
        return dict(_results_store)


def get_result(transaction_id: str) -> Optional[dict]:
    with _results_lock:
        return _results_store.get(transaction_id)


def store_result(transaction_id: str, assessment: dict) -> None:
    with _results_lock:
        _results_store[transaction_id] = assessment
        if len(_results_store) > 1000:
            oldest_key = next(iter(_results_store))
            del _results_store[oldest_key]


def get_stats() -> dict:
    return {
        **_stats,
        "results_stored": len(_results_store),
        # consumer_running is always True when this function is called
        # from the consumer process itself
        "consumer_running": not stop_event.is_set(),
    }


def _create_results_producer() -> Producer:
    return Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
        "acks": "all",
        "retries": 3,
    })


def _publish_result(producer: Producer, result: dict) -> None:
    try:
        producer.produce(
            topic=KAFKA_RESULTS_TOPIC,
            key=result["transaction_id"].encode("utf-8"),
            value=json.dumps(result, default=str).encode("utf-8"),
        )
        producer.poll(0)
    except Exception as e:
        logger.error(f"Failed to publish result: {e}")


def _process_message(msg, results_producer: Producer) -> None:
    try:
        raw = json.loads(msg.value().decode("utf-8"))
        transaction_data = raw.get("data", raw)
        transaction_id = str(
            transaction_data.get("transaction_id", msg.key() or "unknown")
        )

        logger.info(f"Processing: {transaction_id}")
        assessment = assess_transaction(
            transaction_id=transaction_id,
            transaction_data=transaction_data,
        )

        store_result(transaction_id, assessment)
        _publish_result(results_producer, assessment)

        _stats["messages_consumed"] += 1
        if assessment.get("is_flagged"):
            _stats["messages_flagged"] += 1

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in message: {e}")
        _stats["messages_failed"] += 1
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        _stats["messages_failed"] += 1


def _run_consumer() -> None:
    """
    Main consumer loop. Blocks until stop_event is set.
    Called directly by consumer_main.py — no thread wrapping needed.
    """
    logger.info(
        f"Connecting to Kafka at {KAFKA_BOOTSTRAP_SERVERS} | "
        f"Topic: {KAFKA_TRANSACTIONS_TOPIC} | "
        f"Group: {KAFKA_CONSUMER_GROUP}"
    )

    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
        "group.id": KAFKA_CONSUMER_GROUP,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": True,
        "auto.commit.interval.ms": 5000,
        "session.timeout.ms": 30000,
        "heartbeat.interval.ms": 10000,
    })

    results_producer = _create_results_producer()

    try:
        consumer.subscribe([KAFKA_TRANSACTIONS_TOPIC])
        logger.info("Consumer subscribed and ready")
        _stats["started_at"] = datetime.now(timezone.utc).isoformat()

        while not stop_event.is_set():
            msg = consumer.poll(timeout=1.0)

            if msg is None:
                continue

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                logger.error(f"Consumer error: {msg.error()}")
                continue

            _process_message(msg, results_producer)

    except Exception as e:
        logger.error(f"Consumer loop error: {e}", exc_info=True)
    finally:
        logger.info("Closing consumer...")
        consumer.close()
        results_producer.flush(timeout=10)
        logger.info("Consumer closed cleanly")