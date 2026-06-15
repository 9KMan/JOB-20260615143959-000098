# =============================================================================
# Base Worker Class
# Handles common worker functionality: connection, heartbeat, graceful shutdown
# =============================================================================

import asyncio
import logging
import signal
import socket
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import aio_pika
import structlog
from aio_pika import Channel, IncomingMessage
from prometheus_client import Counter, Gauge, Histogram

from scraper.config import settings
from scraper.rabbitmq import RabbitMQExchanges, RabbitMQQueues, get_connection

logger = structlog.get_logger(__name__)

# Metrics
jobs_processed = Counter(
    "scraper_jobs_processed_total",
    "Total number of jobs processed",
    ["status"],
)
jobs_in_progress = Gauge(
    "scraper_jobs_in_progress",
    "Number of jobs currently being processed",
)
job_duration_seconds = Histogram(
    "scraper_job_duration_seconds",
    "Time spent processing a job",
    buckets=[1, 5, 10, 30, 60, 120, 180, 300],
)


class BaseWorker(ABC):
    """Base worker class with common functionality."""
    
    def __init__(self, worker_id: Optional[str] = None):
        self.worker_id = worker_id or f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._channel: Optional[Channel] = None
        self._current_job_id: Optional[str] = None
        
        # Setup signal handlers
        self._setup_signal_handlers()
        
        # Setup structlog context
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            worker_id=self.worker_id,
            hostname=socket.gethostname(),
        )
        
        logger.info("Worker initialized", worker_id=self.worker_id)
    
    def _setup_signal_handlers(self) -> None:
        """Set up graceful shutdown signal handlers."""
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, self._handle_shutdown)
            except (ValueError, OSError):
                # Signal not available in this environment
                pass
    
    def _handle_shutdown(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals gracefully."""
        logger.info("Shutdown signal received", signal=signum)
        self._running = False
        self._shutdown_event.set()
    
    async def connect(self) -> None:
        """Connect to RabbitMQ."""
        connection = await get_connection()
        self._channel = await connection.channel()
        await self._channel.set_qos(prefetch_count=settings.rabbitmq.prefetch_count)
        logger.info("Connected to RabbitMQ")
    
    async def disconnect(self) -> None:
        """Disconnect from RabbitMQ."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            logger.info("Disconnected from RabbitMQ")
    
    async def start(self) -> None:
        """Start the worker."""
        self._running = True
        
        await self.connect()
        await self.register_heartbeat()
        
        # Start heartbeat task
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        # Start consuming jobs
        try:
            await self.consume_jobs()
        finally:
            heartbeat_task.cancel()
            await self.disconnect()
            await self.unregister_heartbeat()
    
    async def register_heartbeat(self) -> None:
        """Register worker in database or heartbeat queue."""
        await self._send_heartbeat(status="online")
    
    async def unregister_heartbeat(self) -> None:
        """Unregister worker."""
        await self._send_heartbeat(status="offline")
    
    async def _send_heartbeat(
        self,
        status: str,
        current_job_id: Optional[str] = None,
    ) -> None:
        """Send heartbeat message."""
        if not self._channel:
            return
        
        exchange = await self._channel.get_exchange(RabbitMQExchanges.DIRECT)
        
        heartbeat_data = {
            "worker_id": self.worker_id,
            "hostname": socket.gethostname(),
            "status": status,
            "current_job_id": current_job_id,
            "timestamp": time.time(),
            "jobs_processed": 0,
        }
        
        message = aio_pika.Message(
            body=str(heartbeat_data).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        
        await exchange.publish(message, routing_key="heartbeat")
    
    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats."""
        while self._running:
            try:
                await asyncio.sleep(settings.worker.heartbeat_interval)
                await self._send_heartbeat(
                    status="busy" if self._current_job_id else "idle",
                    current_job_id=self._current_job_id,
                )
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in heartbeat loop")
    
    async def consume_jobs(self) -> None:
        """Consume jobs from the queue."""
        if not self._channel:
            raise RuntimeError("Not connected to RabbitMQ")
        
        queue = await self._channel.get_queue(RabbitMQQueues.JOBS)
        
        logger.info("Starting to consume jobs", queue=RabbitMQQueues.JOBS)
        
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                if not self._running:
                    break
                
                async with message.process(requeue=False):
                    await self._handle_message(message)
    
    async def _handle_message(self, message: IncomingMessage) -> None:
        """Handle incoming job message."""
        import json
        
        start_time = time.time()
        self._current_job_id = message.headers.get("job_id")
        
        jobs_in_progress.inc()
        structlog.contextvars.bind_contextvars(job_id=self._current_job_id)
        
        try:
            body = json.loads(message.body.decode())
            logger.info("Processing job", job_data=body)
            
            # Process the job
            result = await self.process_job(body)
            
            # Update metrics
            jobs_processed.labels(status="success").inc()
            job_duration_seconds.observe(time.time() - start_time)
            
            logger.info("Job completed successfully", duration=time.time() - start_time)
            
        except Exception as e:
            jobs_processed.labels(status="error").inc()
            logger.exception("Job processing failed", error=str(e))
            raise
        finally:
            jobs_in_progress.dec()
            self._current_job_id = None
            structlog.contextvars.unbind_contextvars("job_id")
    
    @abstractmethod
    async def process_job(self, job_data: Dict[str, Any]) -> Any:
        """Process a single job. Must be implemented by subclass."""
        pass


async def run_worker(worker_class: type) -> None:
    """Run a worker instance."""
    worker = worker_class()
    
    try:
        await worker.start()
    except asyncio.CancelledError:
        logger.info("Worker cancelled")
    except Exception:
        logger.exception("Worker crashed")
        raise
