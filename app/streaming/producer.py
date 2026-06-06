# app/streaming/producer.py
"""
Kafka producer for the fraud detection pipeline.

Responsibility: receive a validated transaction dict and
publish it to the raw-transactions Kafka topic.

Design decisions:
1. Singleton producer — creating a new producer per request is expensive.
   The producer maintains a connection pool to Kafka brokers.
   We create one at startup and reuse it.

2. Delivery callback — we track whether messages are actually delivered
   to Kafka, not just sent. Networks fail. Kafka brokers restart.
   The callback tells us what actually happened.

3. flush() is not called per-message in production — it blocks until
   all in-flight messages are delivered. We call it only on shutdown.
   For low-latency, we rely on the producer's internal batching.

Documentation:
https://docs.confluent.io/kafka-clients/python/current/overview.html
"""
import sys
from pathlib import Path
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from confluent_kafka import Producer, KafkaException

from app.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TRANSACTIONS_TOPIC,
)

logger = logging.getLogger(__name__)

# Allow imports from project root
sys.path.append(str(Path(__file__).resolve().parent.parent))

_producer: Optional[Producer] = None
_delivery_count = {"success": 0, "failure": 0}


def get_producer() -> Producer:
    """
    Return the singleton Kafka producer.
    Created on first call, reused for all subsequent calls.
    """
    global _producer
    if _producer is None:
        raise RuntimeError(
            "Kafka producer not initialised. "
            "Call initialise_producer() at application startup."
        )
    return _producer


def initialise_producer() -> bool:
    """
    Create and configure the Kafka producer.
    Called once during FastAPI lifespan startup.

    Producer configuration explained:
    - bootstrap.servers: Kafka broker address(es)
    - acks: "all" means wait for all replicas to acknowledge
      before considering message delivered. Maximum durability.
    - retries: retry up to 5 times on transient failures
    - retry.backoff.ms: wait 500ms between retries
    - linger.ms: wait 10ms to batch messages together for efficiency
    - compression.type: snappy compresses messages, reducing
      network bandwidth significantly for high-volume scenarios
    """
    global _producer

    try:
        config = {
            "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
            "acks": "all",
            "retries": 5,
            "retry.backoff.ms": 500,
            "linger.ms": 10,
            "compression.type": "snappy",
        }

        _producer = Producer(config)
        logger.info(
            f"Kafka producer initialised. "
            f"Broker: {KAFKA_BOOTSTRAP_SERVERS}"
        )
        return True

    except KafkaException as e:
        logger.error(f"Kafka producer initialisation failed: {e}")
        return False


def _delivery_callback(err, msg) -> None:
    """
    Called by Kafka when message delivery is confirmed or fails.

    This is asynchronous — it is called on a background thread
    by the confluent-kafka library, not in the request/response cycle.

    We use it to track delivery metrics and log failures.
    In production you would alert on high failure rates.
    """
    if err:
        _delivery_count["failure"] += 1
        logger.error(
            f"Message delivery failed: {err} | "
            f"Topic: {msg.topic()} | "
            f"Partition: {msg.partition()}"
        )
    else:
        _delivery_count["success"] += 1
        logger.debug(
            f"Message delivered to {msg.topic()} "
            f"partition [{msg.partition()}] "
            f"offset {msg.offset()}"
        )


def publish_transaction(transaction: dict) -> dict:
    """
    Publish a validated transaction to the raw-transactions Kafka topic.

    Args:
        transaction: Validated transaction dict from Pydantic schema

    Returns:
        Dict with delivery metadata:
        - topic: the topic it was published to
        - status: "published" or "failed"
        - error: error message if failed

    The message includes a metadata wrapper with:
    - the original transaction data
    - published_at timestamp
    - source service identifier

    This wrapper helps downstream consumers know when a message
    was published and from where — useful for debugging and auditing.
    """
    producer = get_producer()

    # Wrap the transaction with metadata
    message = {
        "data": transaction,
        "metadata": {
            "published_at": datetime.now(timezone.utc).isoformat(),
            "source": "fraud-detection-api",
            "version": "1.0",
        },
    }

    try:
        # produce() is non-blocking — it adds to internal buffer
        # The delivery callback fires when Kafka confirms delivery
        producer.produce(
            topic=KAFKA_TRANSACTIONS_TOPIC,
            # Use transaction_id as the message key
            # This ensures all transactions from the same account
            # go to the same partition (ordering guarantee)
            key=str(transaction.get("transaction_id", "")).encode("utf-8"),
            value=json.dumps(message).encode("utf-8"),
            callback=_delivery_callback,
        )

        # poll(0) triggers any pending delivery callbacks
        # without blocking — keeps the callback queue from growing
        producer.poll(0)

        logger.info(
            f"Transaction published to Kafka: "
            f"{transaction.get('transaction_id')}"
        )

        return {
            "topic": KAFKA_TRANSACTIONS_TOPIC,
            "status": "published",
            "error": None,
        }

    except KafkaException as e:
        logger.error(f"Failed to publish transaction: {e}")
        return {
            "topic": KAFKA_TRANSACTIONS_TOPIC,
            "status": "failed",
            "error": str(e),
        }
    except BufferError:
        # Internal Kafka producer buffer is full
        # This means we are producing faster than Kafka can consume
        logger.error("Kafka producer buffer full — backpressure!")
        return {
            "topic": KAFKA_TRANSACTIONS_TOPIC,
            "status": "failed",
            "error": "Producer buffer full. System under high load.",
        }


def get_delivery_stats() -> dict:
    """Return message delivery success/failure counts."""
    total = _delivery_count["success"] + _delivery_count["failure"]
    return {
        "messages_delivered": _delivery_count["success"],
        "messages_failed": _delivery_count["failure"],
        "total_attempted": total,
        "success_rate": (
            _delivery_count["success"] / total
            if total > 0 else 1.0
        ),
    }


def shutdown_producer() -> None:
    """
    Flush all pending messages and close the producer.
    Called during FastAPI lifespan shutdown.

    flush() blocks until all in-flight messages are delivered
    or the timeout expires. This prevents message loss on shutdown.
    """
    global _producer
    if _producer:
        logger.info("Flushing Kafka producer before shutdown...")
        _producer.flush(timeout=30)
        logger.info("Kafka producer flushed and closed")
        _producer = None