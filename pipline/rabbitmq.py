"""
RabbitMQ connection and queue management for Nurliya Pipeline.
"""

import json
import pika

from logging_config import get_logger
from config import RABBITMQ_URL, QUEUE_NAME, DLQ_NAME, PREFETCH_COUNT

logger = get_logger(__name__, service="rabbitmq")

ANOMALY_QUEUE_NAME = "anomaly_insights"
TAXONOMY_CLUSTERING_QUEUE = "taxonomy_clustering"


def get_connection():
    """Create RabbitMQ connection."""
    params = pika.URLParameters(RABBITMQ_URL)
    return pika.BlockingConnection(params)


def setup_queues(channel):
    """Declare queues with dead-letter exchange."""
    # Dead letter exchange
    channel.exchange_declare(exchange="dlx", exchange_type="direct", durable=True)

    # Dead letter queue
    channel.queue_declare(queue=DLQ_NAME, durable=True)
    channel.queue_bind(exchange="dlx", queue=DLQ_NAME, routing_key=QUEUE_NAME)

    # Main queue with dead-letter config
    channel.queue_declare(
        queue=QUEUE_NAME,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": QUEUE_NAME,
        }
    )

    # Anomaly insights queue (for background LLM processing)
    channel.queue_declare(queue=ANOMALY_QUEUE_NAME, durable=True)

    # Taxonomy clustering queue (for HDBSCAN discovery jobs)
    channel.queue_declare(queue=TAXONOMY_CLUSTERING_QUEUE, durable=True)

    logger.debug("Queues configured", extra={"extra_data": {"queue": QUEUE_NAME, "dlq": DLQ_NAME, "anomaly_queue": ANOMALY_QUEUE_NAME, "taxonomy_queue": TAXONOMY_CLUSTERING_QUEUE}})


def publish_message(channel, message: dict):
    """Publish message to review analysis queue."""
    channel.basic_publish(
        exchange="",
        routing_key=QUEUE_NAME,
        body=json.dumps(message),
        properties=pika.BasicProperties(
            delivery_mode=2,  # Persistent
            content_type="application/json",
        )
    )


def get_consumer_channel():
    """Get channel configured for consuming."""
    logger.info("Connecting to RabbitMQ (consumer)...")
    connection = get_connection()
    channel = connection.channel()
    setup_queues(channel)
    channel.basic_qos(prefetch_count=PREFETCH_COUNT)
    logger.info("RabbitMQ consumer connected", extra={"extra_data": {"queue": QUEUE_NAME, "prefetch": PREFETCH_COUNT}})
    return connection, channel


def get_producer_channel():
    """Get channel configured for producing."""
    logger.debug("Connecting to RabbitMQ (producer)...")
    connection = get_connection()
    channel = connection.channel()
    setup_queues(channel)
    logger.debug("RabbitMQ producer connected")
    return connection, channel


# Singleton connection for API use
_api_connection = None
_api_channel = None


def get_channel():
    """Get a channel for publishing messages (reuses connection)."""
    global _api_connection, _api_channel
    try:
        if _api_connection is None or _api_connection.is_closed:
            _api_connection = get_connection()
            _api_channel = _api_connection.channel()
            setup_queues(_api_channel)
        elif _api_channel is None or _api_channel.is_closed:
            _api_channel = _api_connection.channel()
            setup_queues(_api_channel)
        return _api_channel
    except Exception as e:
        logger.warning(f"Failed to get RabbitMQ channel: {e}")
        # Try to reconnect
        _api_connection = get_connection()
        _api_channel = _api_connection.channel()
        setup_queues(_api_channel)
        return _api_channel


if __name__ == "__main__":
    # Test connection
    connection, channel = get_producer_channel()
    logger.info("RabbitMQ connection test successful", extra={"extra_data": {"queue": QUEUE_NAME}})
    connection.close()
