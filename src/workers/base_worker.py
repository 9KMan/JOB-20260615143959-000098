# src/workers/base_worker.py
"""
Base worker implementation with circuit breaker, retry logic, and graceful shutdown.
"""
import asyncio
import logging
import signal
import sys
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Callable
from enum import Enum

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.exceptions import AMQPConnectionError, AMQPChannelError
from pika.spec import Basic, BasicProperties

from src.config import config
from src.models import get_session_factory, init_db

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovery possible


@dataclass
class CircuitBreaker:
    """
    Circuit breaker implementation for protecting against cascading failures.
    
    Failure modes handled:
    - Proxy throttling (ERR_TUNNEL errors)
    - Transient failures that should be retried
    - Anti-bot detection triggers
    """
    resource_id: str
    failure_threshold: int = config.rabbitmq.circuit_breaker_threshold
    reset_timeout: int = config.rabbitmq.circuit_breaker_timeout
    half_open_success_threshold: int = 3
    
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: Optional[datetime] = field(default=None, init=False)
    _last_success_time: Optional[datetime] = field(default=None, init=False)
    _half_open_successes: int = field(default=0, init=False)
    
    def __post_init__(self):
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state, checking for timeout transitions."""
        if self._state == CircuitState.OPEN:
            if self._should_attempt_reset():
                return CircuitState.HALF_OPEN
        return self._state
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self._last_failure_time is None:
            return True
        elapsed = (datetime.now(timezone.utc) - self._last_failure_time).total_seconds()
        return elapsed >= self.reset_timeout
    
    def record_success(self) -> None:
        """Record a successful operation."""
        self._failure_count = 0
        self._last_success_time = datetime.now(timezone.utc)
        
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_successes += 1
            if self._half_open_successes >= self.half_open_success_threshold:
                logger.info(f"Circuit {self.resource_id}: CLOSING after successful recovery")
                self._state = CircuitState.CLOSED
                self._half_open_successes = 0
        elif self._state == CircuitState.CLOSED:
            pass  # Normal operation
    
    def record_failure(self, error_type: str = "generic") -> bool:
        """
        Record a failed operation.
        
        Returns:
            True if circuit should trip (open), False otherwise
        """
        self._failure_count += 1
        self._last_failure_time = datetime.now(timezone.utc)
        
        # Determine if we should trip based on error type
        should_trip = self._failure_count >= self.failure_threshold
        
        if should_trip and self._state == CircuitState.CLOSED:
            logger.warning(
                f"Circuit {self.resource_id}: OPENING after {self._failure_count} "
                f"failures (last error: {error_type})"
            )
            self._state = CircuitState.OPEN
            return True
        
        if self._state == CircuitState.HALF_OPEN:
            logger.warning(f"Circuit {self.resource_id}: Tripping back to OPEN after failure in half-open")
            self._state = CircuitState.OPEN
            self._half_open_successes = 0
            return True
        
        return False
    
    def is_available(self) -> bool:
        """Check if the resource is available for requests."""
        return self.state != CircuitState.OPEN
    
    def get_status(self) -> Dict[str, Any]:
        """Get circuit breaker status for monitoring."""
        return {
            "resource_id": self.resource_id,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "last_failure": self._last_failure_time.isoformat() if self._last_failure_time else None,
            "last_success": self._last_success_time.isoformat() if self._last_success_time else None,
        }


@dataclass
class ExponentialBackoff:
    """Exponential backoff with jitter for retry delays."""
    initial_delay_ms: int = config.proxy.initial_backoff_ms
    max_delay_ms: int = config.proxy.max_backoff_ms
    multiplier: float = config.proxy.backoff_multiplier
    jitter: float = 0.1
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number."""
        delay = self.initial_delay_ms * (self.multiplier ** attempt)
        delay = min(delay, self.max_delay_ms)
        
        # Add jitter
        jitter_range = delay * self.jitter
        delay += (hash(attempt) % 100) / 100 * jitter_range * 2 - jitter_range
        
        return delay / 1000  # Return seconds


class BaseWorker(ABC):
    """
    Base worker class with common functionality:
    - RabbitMQ connection management
    - Circuit breaker for proxy/exit nodes
    - Exponential backoff retry logic
    - Graceful shutdown handling
    - Database session management
    """
    
    def __init__(self, worker_id: Optional[str] = None):
        self.worker_id = worker_id or config.worker.worker_id
        self.logger = logging.getLogger(f"{__name__}.{self.worker_id}")
        
        # Connection state
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[BlockingChannel] = None
        self._should_stop = False
        self._is_consuming = False
        
        # Circuit breakers
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # Backoff strategy
        self._backoff = ExponentialBackoff()
        
        # Session factory
        self._session_factory = get_session_factory()
        
        # Register signal handlers
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """Set up graceful shutdown handlers."""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self._should_stop = True
            if self._is_consuming:
                self.stop_consuming()
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
    
    def _get_circuit_breaker(self, resource_id: str) -> CircuitBreaker:
        """Get or create circuit breaker for a resource."""
        if resource_id not in self._circuit_breakers:
            self._circuit_breakers[resource_id] = CircuitBreaker(resource_id=resource_id)
        return self._circuit_breakers[resource_id]
    
    def _get_proxy_circuit_breaker(self, exit_node: Optional[int] = None) -> CircuitBreaker:
        """Get circuit breaker for proxy/exit node."""
        resource_id = f"proxy_exit_{exit_node}" if exit_node is not None else "proxy_default"
        return self._get_circuit_breaker(resource_id)
    
    def _get_site_circuit_breaker(self, site: str) -> CircuitBreaker:
        """Get circuit breaker for a specific site."""
        return self._get_circuit_breaker(f"site_{site}")
    
    def _connect(self) -> bool:
        """
        Establish connection to RabbitMQ.
        
        Returns:
            True if connection successful, False otherwise
        """
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
                heartbeat=config.worker.heartbeat_interval,
                blocked_connection_timeout=config.worker.heartbeat_timeout,
                connection_attempts=3,
                retry_delay=5,
            )
            
            self._connection = pika.BlockingConnection(parameters)
            self._channel = self._connection.channel()
            
            # Set QoS
            self._channel.basic_qos(prefetch_count=config.worker.prefetch_count)
            
            # Declare queues
            self._declare_queues()
            
            self.logger.info(f"Connected to RabbitMQ at {config.rabbitmq.host}:{config.rabbitmq.port}")
            return True
            
        except AMQPConnectionError as e:
            self.logger.error(f"Failed to connect to RabbitMQ: {e}")
            return False
    
    def _declare_queues(self):
        """Declare all required queues with DLX configuration."""
        # Dead letter exchange
        self._channel.exchange_declare(
            exchange="dlx",
            exchange_type="direct",
            durable=True
        )
        
        # Main scrape queue with DLX
        self._channel.queue_declare(
            queue=config.rabbitmq.scrape_queue,
            durable=True,
            arguments={
                "x-dead-letter-exchange": "dlx",
                "x-dead-letter-routing-key": config.rabbitmq.dead_letter_queue,
            }
        )
        
        # Retry queue with TTL (messages will be redelivered after delay)
        self._channel.queue_declare(
            queue=config.rabbitmq.retry_queue,
            durable=True,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": config.rabbitmq.scrape_queue,
                "x-message-ttl": config.rabbitmq.retry_delay_seconds * 1000,
            }
        )
        
        # Dead letter queue
        self._channel.queue_declare(
            queue=config.rabbitmq.dead_letter_queue,
            durable=True
        )
        
        # Completed queue (for tracking)
        self._channel.queue_declare(
            queue=config.rabbitmq.completed_queue,
            durable=True
        )
        
        self.logger.debug("All queues declared successfully")
    
    def _reconnect(self) -> bool:
        """Attempt to reconnect with exponential backoff."""
        max_attempts = 5
        for attempt in range(max_attempts):
            delay = self._backoff.get_delay(attempt)
            self.logger.info(f"Reconnection attempt {attempt + 1}/{max_attempts} after {delay:.1f}s...")
            time.sleep(delay)
            
            if self._connect():
                return True
        
        self.logger.error("Failed to reconnect after all attempts")
        return False
    
    def start_consuming(self):
        """Start consuming messages from the scrape queue."""
        if not self._connect():
            if not self._reconnect():
                return
        
        self._is_consuming = True
        
        self._channel.basic_consume(
            queue=config.rabbitmq.scrape_queue,
            on_message_callback=self._on_message,
            auto_ack=False
        )
        
        self.logger.info(f"Worker {self.worker_id} started consuming from {config.rabbitmq.scrape_queue}")
        
        try:
            while not self._should_stop:
                self._connection.process_data_events(time_limit=1)
        except Exception as e:
            self.logger.error(f"Error during consumption: {e}")
        finally:
            self._cleanup()
    
    def stop_consuming(self):
        """Stop consuming messages."""
        self._should_stop = True
        self._is_consuming = False
        if self._channel and self._channel.is_open:
            self._channel.stop_consuming()
    
    def _cleanup(self):
        """Clean up resources."""
        self.logger.info("Cleaning up worker resources...")
        
        if self._channel and self._channel.is_open:
            try:
                self._channel.close()
            except Exception as e:
                self.logger.warning(f"Error closing channel: {e}")
        
        if self._connection and self._connection.is_open:
            try:
                self._connection.close()
            except Exception as e:
                self.logger.warning(f"Error closing connection: {e}")
        
        self.logger.info("Worker cleanup complete")
    
    def _on_message(self, channel, method, properties, body):
        """
        Handle incoming message.
        
        This method handles:
        - Message acknowledgment
        - Retry logic
        - Dead letter routing
        - Error classification
        """
        delivery_tag = method.delivery_tag
        
        try:
            message = self._parse_message(body)
            job_id = message.get("job_id", "unknown")
            
            self.logger.info(f"Processing job {job_id} (delivery_tag={delivery_tag})")
            
            # Execute the actual scraping
            result = self._process_job(message)
            
            if result.success:
                self._acknowledge_message(delivery_tag, job_id)
            else:
                self._handle_failure(message, result, delivery_tag)
                
        except Exception as e:
            self.logger.exception(f"Unexpected error processing message: {e}")
            # Reject without requeue to prevent infinite loops
            self._nack_message(delivery_tag, requeue=False)
    
    @abstractmethod
    def _process_job(self, message: Dict[str, Any]) -> "JobResult":
        """Process a single scraping job. Must be implemented by subclasses."""
        pass
    
    @abstractmethod
    def _parse_message(self, body: bytes) -> Dict[str, Any]:
        """Parse message body into job data. Must be implemented by subclasses."""
        pass
    
    def _acknowledge_message(self, delivery_tag: int, job_id: str):
        """Acknowledge successful job completion."""
        self._channel.basic_ack(delivery_tag=delivery_tag)
        self.logger.info(f"Job {job_id} completed successfully")
    
    def _handle_failure(self, message: Dict[str, Any], result: "JobResult", delivery_tag: int):
        """
        Handle job failure based on error classification.
        
        Routing logic:
        - TRANSIENT: Retry with backoff (up to max_retries)
        - PROXY: Retry with different exit node (circuit breaker)
        - TERMINAL: Move to dead letter queue
        - INFRA: Retry with backoff
        """
        job_id = message.get("job_id", "unknown")
        retry_count = message.get("retry_count", 0)
        max_retries = config.rabbitmq.max_retries
        
        # Update circuit breaker if proxy error
        if result.error_category == "proxy" and result.exit_node is not None:
            cb = self._get_proxy_circuit_breaker(result.exit_node)
            should_trip = cb.record_failure(result.error_code or "proxy_error")
            
            if should_trip:
                self.logger.warning(
                    f"Proxy circuit breaker tripped for exit node {result.exit_node}"
                )
        
        # Determine routing
        if result.is_permanent:
            # Terminal error - send to DLQ
            self.logger.warning(f"Job {job_id} moved to dead letter queue (permanent error)")
            self._send_to_dlq(message, result)
            self._channel.basic_ack(delivery_tag=delivery_tag)
            
        elif retry_count >= max_retries:
            # Max retries exceeded
            self.logger.warning(f"Job {job_id} moved to DLQ after {retry_count} retries")
            message["max_retries_exceeded"] = True
            self._send_to_dlq(message, result)
            self._channel.basic_ack(delivery_tag=delivery_tag)
            
        elif result.error_category == "transient" or result.error_category == "infra":
            # Transient error - retry with backoff
            self._schedule_retry(message, result, retry_count + 1)
            self._channel.basic_ack(delivery_tag=delivery_tag)
            
        elif result.error_category == "proxy":
            # Proxy error - retry with different exit node if circuit is open
            cb = self._get_proxy_circuit_breaker(result.exit_node)
            if cb.is_available():
                self._schedule_retry(message, result, retry_count + 1)
            else:
                self.logger.warning(f"Exit node {result.exit_node} circuit is open, waiting...")
                self._schedule_retry(message, result, retry_count + 1)
            self._channel.basic_ack(delivery_tag=delivery_tag)
            
        else:
            # Unknown error - retry up to max
            self._schedule_retry(message, result, retry_count + 1)
            self._channel.basic_ack(delivery_tag=delivery_tag)
    
    def _schedule_retry(self, message: Dict[str, Any], result: "JobResult", retry_count: int):
        """Schedule a job for retry with updated retry count."""
        message["retry_count"] = retry_count
        message["last_error"] = result.error_message
        message["last_error_category"] = result.error_category
        
        # Add exponential backoff delay for retry queue TTL
        body = self._serialize_message(message)
        
        # Calculate delay based on backoff
        delay_ms = int(self._backoff.get_delay(retry_count) * 1000)
        
        # Republish to retry queue with delay header
        properties = pika.BasicProperties(
            delivery_mode=2,  # Persistent
            headers={"x-delay": min(delay_ms, config.rabbitmq.max_retry_delay * 1000)},
        )
        
        self._channel.basic_publish(
            exchange="",
            routing_key=config.rabbitmq.retry_queue,
            body=body,
            properties=properties
        )
        
        self.logger.info(
            f"Job {message.get('job_id')} scheduled for retry "
            f"(attempt {retry_count}, delay {delay_ms}ms)"
        )
    
    def _send_to_dlq(self, message: Dict[str, Any], result: "JobResult"):
        """Send failed job to dead letter queue."""
        message["final_error"] = result.error_message
        message["final_error_category"] = result.error_category
        message["final_error_code"] = result.error_code
        message["final_is_permanent"] = result.is_permanent
        
        body = self._serialize_message(message)
        
        self._channel.basic_publish(
            exchange="",
            routing_key=config.rabbitmq.dead_letter_queue,
            body=body
        )
    
    def _serialize_message(self, message: Dict[str, Any]) -> bytes:
        """Serialize message to bytes."""
        import json
        return json.dumps(message).encode("utf-8")
    
    def _nack_message(self, delivery_tag: int, requeue: bool = False):
        """Reject a message."""
        self._channel.basic_nack(delivery_tag=delivery_tag, requeue=requeue)
    
    def get_circuit_status(self) -> Dict[str, Any]:
        """Get status of all circuit breakers for monitoring."""
        return {
            name: cb.get_status()
            for name, cb in self._circuit_breakers.items()
        }


@dataclass
class JobResult:
    """Result of a job processing attempt."""
    success: bool
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    error_category: Optional[str] = None  # transient, terminal, proxy, anti_bot, infra
    is_permanent: bool = False
    exit_node: Optional[int] = None
    data: Optional[Dict[str, Any]] = None
    warnings: Optional[List[str]] = None
