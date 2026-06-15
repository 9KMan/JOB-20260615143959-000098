// src/core/metrics.py
"""Prometheus metrics collection for monitoring scraping operations."""
import time
from typing import Dict, Optional
from functools import wraps
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest


class MetricsCollector:
    """Central metrics collection for the scraping platform."""
    
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry
        
        # Request metrics
        self.requests_total = Counter(
            "scraping_requests_total",
            "Total number of scraping requests",
            ["status", "batch_id"],
            registry=registry
        )
        
        self.request_duration = Histogram(
            "scraping_request_duration_seconds",
            "Duration of scraping requests in seconds",
            ["batch_id", "status"],
            buckets=[0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600],
            registry=registry
        )
        
        # Job metrics
        self.jobs_total = Counter(
            "scraping_jobs_total",
            "Total number of scrape jobs",
            ["status", "error_category"],
            registry=registry
        )
        
        self.jobs_in_progress = Gauge(
            "scraping_jobs_in_progress",
            "Number of jobs currently being processed",
            registry=registry
        )
        
        # Batch metrics
        self.batches_total = Counter(
            "scraping_batches_total",
            "Total number of batches created",
            registry=registry
        )
        
        self.batch_items = Histogram(
            "scraping_batch_items",
            "Number of items per batch",
            buckets=[10, 50, 100, 500, 1000, 5000, 10000],
            registry=registry
        )
        
        # Proxy metrics
        self.proxy_requests = Counter(
            "scraping_proxy_requests_total",
            "Total proxy requests",
            ["proxy_host", "status"],
            registry=registry
        )
        
        self.proxy_errors = Counter(
            "scraping_proxy_errors_total",
            "Total proxy errors by type",
            ["error_type", "proxy_host"],
            registry=registry
        )
        
        self.active_proxy_sessions = Gauge(
            "scraping_active_proxy_sessions",
            "Number of active proxy sessions",
            registry=registry
        )
        
        # Circuit breaker metrics
        self.circuit_breaker_state = Gauge(
            "scraping_circuit_breaker_state",
            "Circuit breaker state (0=closed, 1=open, 2=half-open)",
            ["proxy_host"],
            registry=registry
        )
        
        # Queue metrics
        self.queue_messages_published = Counter(
            "scraping_queue_messages_published_total",
            "Total messages published to queue",
            ["queue", "status"],
            registry=registry
        )
        
        self.queue_messages_consumed = Counter(
            "scraping_queue_messages_consumed_total",
            "Total messages consumed from queue",
            ["queue", "status"],
            registry=registry
        )
        
        self.queue_depth = Gauge(
            "scraping_queue_depth",
            "Current queue depth",
            ["queue"],
            registry=registry
        )
        
        # LLM processing metrics
        self.llm_requests = Counter(
            "scraping_llm_requests_total",
            "Total LLM processing requests",
            ["status"],
            registry=registry
        )
        
        self.llm_duration = Histogram(
            "scraping_llm_processing_duration_seconds",
            "Duration of LLM processing in seconds",
            buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60],
            registry=registry
        )
        
        # Browser metrics
        self.browser_launches = Counter(
            "scraping_browser_launches_total",
            "Total browser launches",
            ["status"],
            registry=registry
        )
        
        self.browser_page_loads = Histogram(
            "scraping_browser_page_load_seconds",
            "Browser page load time in seconds",
            ["status"],
            buckets=[0.5, 1, 2, 5, 10, 30, 60, 120],
            registry=registry
        )
        
        # Error classification metrics
        self.error_classifications = Counter(
            "scraping_error_classifications_total",
            "Error classification counts",
            ["error_code", "classification"],
            registry=registry
        )

    def record_request(self, batch_id: str, status: str, duration: float):
        """Record a scraping request."""
        self.requests_total.labels(batch_id=batch_id, status=status).inc()
        self.request_duration.labels(batch_id=batch_id, status=status).observe(duration)

    def record_job(self, status: str, error_category: str = "none"):
        """Record a job completion."""
        self.jobs_total.labels(status=status, error_category=error_category).inc()

    def increment_jobs_in_progress(self):
        """Increment jobs in progress gauge."""
        self.jobs_in_progress.inc()

    def decrement_jobs_in_progress(self):
        """Decrement jobs in progress gauge."""
        self.jobs_in_progress.dec()

    def record_batch_created(self, item_count: int):
        """Record a batch creation."""
        self.batches_total.inc()
        self.batch_items.observe(item_count)

    def record_proxy_request(self, proxy_host: str, status: str):
        """Record a proxy request."""
        self.proxy_requests.labels(proxy_host=proxy_host, status=status).inc()

    def record_proxy_error(self, error_type: str, proxy_host: str):
        """Record a proxy error."""
        self.proxy_errors.labels(error_type=error_type, proxy_host=proxy_host).inc()

    def record_circuit_breaker_state(self, proxy_host: str, state: int):
        """Record circuit breaker state change."""
        self.circuit_breaker_state.labels(proxy_host=proxy_host).set(state)

    def record_llm_processing(self, status: str, duration: float):
        """Record LLM processing."""
        self.llm_requests.labels(status=status).inc()
        self.llm_duration.observe(duration)

    def record_browser_launch(self, status: str):
        """Record browser launch."""
        self.browser_launches.labels(status=status).inc()

    def record_page_load(self, status: str, duration: float):
        """Record page load time."""
        self.browser_page_loads.labels(status=status).observe(duration)

    def record_error_classification(self, error_code: str, classification: str):
        """Record error classification."""
        self.error_classifications.labels(
            error_code=error_code, 
            classification=classification
        ).inc()


# Global metrics instance
_metrics: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    """Get global metrics collector instance."""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics


def track_duration(histogram: Histogram, labels: Dict[str, str]):
    """Decorator to track function duration."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                histogram.labels(**labels).observe(duration)
        return wrapper
    return decorator
