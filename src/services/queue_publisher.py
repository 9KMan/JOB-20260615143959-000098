# src/services/queue_publisher.py
"""
RabbitMQ message publisher for job submission.
"""
import json
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import BasicProperties

from src.config import config

logger = logging.getLogger(__name__)


@dataclass
class ScrapeJob:
    """Scrape job message structure."""
    job_id: str
    url: str
    site: Optional[str] = None
    target_fields: List[str] = None
    priority: int = 5
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.target_fields is None:
            self.target_fields = []
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_json(self) -> bytes:
        return json.dumps(self.to_dict()).encode("utf-8")


class QueuePublisher:
    """
    Publisher for sending jobs to RabbitMQ scrape queue.
    
    Features:
    - Connection management with reconnection
    - Message persistence
    - Batch publishing
    - Publisher confirms
    """
    
    def __init__(self):
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[BlockingChannel] = None
        self._connected = False
    
    def connect(self) -> bool:
        """Establish connection to RabbitMQ."""
        try:
            credentials = pika.PlainCredentials(
                config.rabbitmq.user,
                config.rabbitmq.password
            )
            
            parameters = pika.ConnectionParameters(
                host=config.rabbitmq.host,
                port=config.rabbitmq.port,
                virtual_host=config.rabbitmq.vhost,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300,
            )
            
            self._connection = pika.BlockingConnection(parameters)
            self._channel = self._connection.channel()
            
            # Enable publisher confirms
            self._channel.confirm_delivery()
            
            # Declare queue
            self._channel.queue_declare(
                queue=config.rabbitmq.scrape_queue,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": "dlx",
                    "x-dead-letter-routing-key": config.rabbitmq.dead_letter_queue,
                }
            )
            
            self._connected = True
            logger.info(f"Connected to RabbitMQ at {config.rabbitmq.host}:{config.rabbitmq.port}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            return False
    
    def disconnect(self):
        """Close connection to RabbitMQ."""
        if self._channel and self._channel.is_open:
            try:
                self._channel.close()
            except Exception:
                pass
        
        if self._connection and self._connection.is_open:
            try:
                self._connection.close()
            except Exception:
                pass
        
        self._connected = False
    
    def ensure_connected(self) -> bool:
        """Ensure connection is established, reconnect if needed."""
        if not self._connected or not self._connection or not self._connection.is_open:
            return self.connect()
        return True
    
    def publish_job(self, job: ScrapeJob) -> bool:
        """
        Publish a single scrape job.
        
        Args:
            job: ScrapeJob to publish
            
        Returns:
            True if published successfully
        """
        if not self.ensure_connected():
            return False
        
        try:
            properties = BasicProperties(
                delivery_mode=2,  # Persistent
                content_type="application/json",
                priority=job.priority,
            )
            
            self._channel.basic_publish(
                exchange="",
                routing_key=config.rabbitmq.scrape_queue,
                body=job.to_json(),
                properties=properties,
                mandatory=True
            )
            
            logger.debug(f"Published job {job.job_id} to queue")
            return True
            
        except Exception as e:
            logger.error(f"Failed to publish job {job.job_id}: {e}")
            self._connected = False
            return False
    
    def publish_batch(self, jobs: List[ScrapeJob]) -> tuple[int, int]:
        """
        Publish multiple jobs in batch.
        
        Args:
            jobs: List of ScrapeJob to publish
            
        Returns:
            Tuple of (successful_count, failed_count)
        """
        if not self.ensure_connected():
            return 0, len(jobs)
        
        successful = 0
        failed = 0
        
        properties = BasicProperties(
            delivery_mode=2,
            content_type="application/json",
        )
        
        for job in jobs:
            try:
                self._channel.basic_publish(
                    exchange="",
                    routing_key=config.rabbitmq.scrape_queue,
                    body=job.to_json(),
                    properties=properties,
                    mandatory=True
                )
                successful += 1
            except Exception as e:
                logger.error(f"Failed to publish job {job.job_id}: {e}")
                failed += 1
        
        logger.info(f"Published batch: {successful} successful, {failed} failed")
        return successful, failed
    
    def get_queue_depth(self) -> int:
        """Get current queue depth."""
        if not self.ensure_connected():
            return -1
        
        try:
            queue = self._channel.queue_declare(
                queue=config.rabbitmq.scrape_queue,
                passive=True
            )
            return queue.method.message_count
        except Exception as e:
            logger.error(f"Failed to get queue depth: {e}")
            return -1
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


def create_job(
    job_id: str,
    url: str,
    site: Optional[str] = None,
    target_fields: Optional[List[str]] = None,
    priority: int = 5,
    **metadata
) -> ScrapeJob:
    """Create a scrape job from parameters."""
    return ScrapeJob(
        job_id=job_id,
        url=url,
        site=site,
        target_fields=target_fields or [],
        priority=priority,
        metadata=metadata
    )


def submit_jobs(jobs: List[ScrapeJob]) -> tuple[int, int]:
    """
    Submit multiple jobs to the queue.
    
    Returns:
        Tuple of (successful_count, failed_count)
    """
    with QueuePublisher() as publisher:
        return publisher.publish_batch(jobs)
