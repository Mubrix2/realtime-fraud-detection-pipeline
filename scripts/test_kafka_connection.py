# scripts/test_kafka_connection.py
"""
Run this script to verify Python can produce and consume
messages from your local Kafka broker.

Usage: python scripts/test_kafka_connection.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from confluent_kafka import Consumer, KafkaError, Producer

BOOTSTRAP_SERVERS = "localhost:9092"
TEST_TOPIC = "raw-transactions"


def test_producer():
    """Publish one test message to Kafka."""
    producer = Producer({"bootstrap.servers": BOOTSTRAP_SERVERS})

    test_message = {
        "transaction_id": "TEST-001",
        "amount": 150000.00,
        "type": "TRANSFER",
        "source": "python-test",
    }

    def delivery_report(err, msg):
        """Called when message is delivered or fails."""
        if err:
            print(f"❌ Delivery failed: {err}")
        else:
            print(
                f"✅ Message delivered to "
                f"{msg.topic()} partition [{msg.partition()}]"
            )

    producer.produce(
        TEST_TOPIC,
        key="TEST-001",
        value=json.dumps(test_message).encode("utf-8"),
        callback=delivery_report,
    )

    # flush() waits until all messages are delivered
    producer.flush()
    print("Producer test complete")


def test_consumer():
    """Read one message from Kafka and print it."""
    consumer = Consumer(
        {
            "bootstrap.servers": BOOTSTRAP_SERVERS,
            "group.id": "test-consumer-group",
            # Read from the beginning of the topic
            "auto.offset.reset": "earliest",
        }
    )

    consumer.subscribe([TEST_TOPIC])
    print(f"Consumer subscribed to '{TEST_TOPIC}'. Waiting 5 seconds...")

    start = time.time()
    while time.time() - start < 5:
        msg = consumer.poll(timeout=1.0)

        if msg is None:
            continue
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                print("Reached end of partition")
            else:
                print(f"Consumer error: {msg.error()}")
            continue

        data = json.loads(msg.value().decode("utf-8"))
        print(f"✅ Received message: {data}")
        break

    consumer.close()
    print("Consumer test complete")


if __name__ == "__main__":
    print("=== Testing Kafka Connection ===\n")
    test_producer()
    print()
    test_consumer()