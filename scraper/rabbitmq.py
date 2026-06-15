# =============================================================================
# RabbitMQ Connection Management
# =============================================================================

import json
import logging
from typing import Any, Callable, Dict, Optional

import aio_pika
from aio_pika import Channel, Connection, Exchange, Message, Queue
from aio_pika.abc import AbstractRobustConnection
from aio_pika.pool import Pool

from scraper.config import settings

logger = logging.getLogger(__name__)

# Global connection and channel pools
_connection: Optional[AbstractRobustConnection] = None
_channel_pool: Optional[Pool[Channel]] = None


class RabbitMQExchanges:
    """Exchange definitions."""
    
    DIRECT = "scraper.direct"
    DLX = "scraper.dlx"
    RETRY = "scraper.retry"


class RabbitMQQueues:
    """Queue definitions."""
    
    JOBS = "scraper.jobs"
    RETRY = "scraper.jobs.retry"
    DLQ = "scraper.jobs.dlq"
    RESULTS = "scraper.results"
    HEARTBEAT = "scraper.heartbeat"


async def init_rabbitmq() -> None:
    """Initialize RabbitMQ connection and channel pool."""
    global _connection, _channel_pool
    
    logger.info("Initializing RabbitMQ connection...")
    
    # Create robust connection with automatic reconnection
    _connection = await aio_pika.connect_robust(
        settings.rabbitmq.url,
        client_properties={
            "connection_name": "scraper-client",
            "product": "scraper-framework",
        },
    )
    
    # Create channel pool
    _channel_pool = Pool(
        get_channel,
        max_size=settings.rabbitmq.prefetch_count * 2,
    )
    
    # Setup exchanges and queues
    await setup_exchanges_and_queues()
    
    logger.info("RabbitMQ connection initialized successfully")


async def get_channel() -> Channel:
    """Get a channel from the connection."""
    global _connection
    
    if _connection is None:
        raise RuntimeError("RabbitMQ not initialized. Call init_rabbitmq() first.")
    
    return await _connection.channel()


async def setup_exchanges_and_queues() -> None:
    """Set up exchanges and queues with proper bindings."""
    global _connection
    
    if _connection is None:
        raise RuntimeError("RabbitMQ not initialized.")
    
    channel = await _connection.channel()
    
    # Declare exchanges
    logger.info("Declaring exchanges...")
    
    direct_exchange = await channel.declare_exchange(
        RabbitMQExchanges.DIRECT,
        aio_pika.ExchangeType.DIRECT,
        durable=True,
    )
    
    dlx_exchange = await channel.declare_exchange(
        RabbitMQExchanges.DLX,
        aio_pika.ExchangeType.DIRECT,
        durable=True,
    )
    
    retry_exchange = await channel.declare_exchange(
        RabbitMQExchanges.RETRY,
        aio_pika.ExchangeType.DIRECT,
        durable=True,
    )
    
    # Declare queues with DLX configuration
    logger.info("Declaring queues...")
    
    # Main jobs queue with DLX
    jobs_queue = await channel.declare_queue(
        RabbitMQQueues.JOBS,
        durable=True,
        arguments={
            "x-dead-letter-exchange": RabbitMQExchanges.DLX,
            "x-dead-letter-routing-key": "dlq",
            "x-message-ttl": 30000,
            "x-max-priority": 10,
        },
    )
    await jobs_queue.bind(direct_exchange, routing_key="jobs")
    
    # Retry queue - routes back to main queue after TTL
    retry_queue = await channel.declare_queue(
        RabbitMQQueues.RETRY,
        durable=True,
        arguments={
            "x-dead-letter-exchange": RabbitMQExchanges.DIRECT,
            "x-dead-letter-routing-key": "jobs",
            "x-message-ttl": 30000,
            "x-max-priority": 10,
        },
    )
    await retry_queue.bind(retry_exchange, routing_key="jobs.retry")
    
    # Dead letter queue
    dlq = await channel.declare_queue(
        RabbitMQQueues.DLQ,
        durable=True,
    )
    await dlq.bind(dlx_exchange, routing_key="dlq")
    
    # Results queue
    results_queue = await channel.declare_queue(
        RabbitMQQueues.RESULTS,
        durable=True,
        arguments={
            "x-message-ttl": 86400000,  # 24 hours
        },
    )
    await results_queue.bind(direct_exchange, routing_key="results")
    
    # Heartbeat queue
    heartbeat_queue = await channel.declare_queue(
        RabbitMQQueues.HEARTBEAT,
        durable=True,
        arguments={
            "x-message-ttl": 60000,  # 1 minute
            "x-max-length": 10000,
        },
    )
    await heartbeat_queue.bind(direct_exchange, routing_key="heartbeat")
    
    await channel.close()
    
    logger.info("Exchanges and queues setup complete")


async def close_rabbitmq() -> None:
    """Close RabbitMQ connection."""
    global _connection, _channel_pool
    
    if _connection:
        logger.info("Closing RabbitMQ connection...")
        await _connection.close()
        _connection = None
        _channel_pool = None
        logger.info("RabbitMQ connection closed")


async def get_connection() -> AbstractRobustConnection:
    """Get RabbitMQ connection."""
    if _connection is None:
        raise RuntimeError("RabbitMQ not initialized. Call init_rabbitmq() first.")
    return _connection


async def publish_message(
    exchange_name: str,
    routing_key: str,
    message_body: Dict[str, Any],
    priority: int = 5,
    headers: Optional[Dict[str, Any]] = None,
) -> None:
    """Publish a message to an exchange."""
    connection = await get_connection()
    channel = await connection.channel()
    
    exchange = await channel.get_exchange(exchange_name)
    
    message = Message(
        body=json.dumps(message_body).encode(),
        content_type="application/json",
        priority=priority,
        headers=headers or {},
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )
    
    await exchange.publish(message, routing_key=routing_key)
    await channel.close()


async def consume_messages(
    queue_name: str,
    callback: Callable,
    prefetch_count: int = 1,
) -> None:
    """Consume messages from a queue."""
    connection = await get_connection()
    channel = await connection.channel()
    
    await channel.set_qos(prefetch_count=prefetch_count)
    
    queue = await channel.get_queue(queue_name)
    
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            async with message.process():
                await callback(message)
