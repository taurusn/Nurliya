import json
import pika
from config import RABBITMQ_URL, QUEUE_NAME, DLQ_NAME, PREFETCH_COUNT


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
    connection = get_connection()
    channel = connection.channel()
    setup_queues(channel)
    channel.basic_qos(prefetch_count=PREFETCH_COUNT)
    return connection, channel


def get_producer_channel():
    """Get channel configured for producing."""
    connection = get_connection()
    channel = connection.channel()
    setup_queues(channel)
    return connection, channel


if __name__ == "__main__":
    # Test connection
    connection, channel = get_producer_channel()
    print("RabbitMQ connection successful")
    print(f"Queue '{QUEUE_NAME}' ready")
    connection.close()
