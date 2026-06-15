// tests/test_models.py
"""Unit tests for SQLAlchemy models.

Tests cover model creation, validation, and relationship integrity.
"""
import uuid
from datetime import datetime, timedelta
from typing import Generator
import pytest
import pytest_asyncio

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.pool import StaticPool

from models import Base, Job, ScrapeTask, ScrapeResult, ScrapeFailure, ProxySession, WorkerInstance
from models.enums import JobStatus, TaskStatus, CircuitState, FailureCategory, ProxyStatus, WorkerStatus


# Test database URL (in-memory SQLite for unit tests)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_session() -> Generator[AsyncSession, None, None]:
    """Create async session for testing."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    
    async with async_session_factory() as session:
        yield session
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


class TestJobModel:
    """Tests for Job model."""
    
    def test_job_creation(self):
        """Test creating a basic job."""
        job = Job(
            name="Test Job",
            total_tasks=100,
        )
        assert job.name == "Test Job"
        assert job.total_tasks == 100
        assert job.status == JobStatus.PENDING
        assert job.completed_tasks == 0
        assert job.failed_tasks == 0
        assert job.metadata == {}
    
    def test_job_progress(self):
        """Test job progress calculation."""
        job = Job(total_tasks=100)
        assert job.progress_percentage == 0.0
        
        job.completed_tasks = 50
        assert job.progress_percentage == 50.0
        
        job.failed_tasks = 25
        assert job.progress_percentage == 75.0
    
    def test_job_increment_completed(self):
        """Test incrementing completed tasks."""
        job = Job(total_tasks=10)
        job.completed_tasks = 5
        job.increment_completed()
        assert job.completed_tasks == 6
    
    def test_job_increment_failed(self):
        """Test incrementing failed tasks."""
        job = Job(total_tasks=10)
        job.failed_tasks = 5
        job.increment_failed()
        assert job.failed_tasks == 6
    
    def test_job_completion(self):
        """Test job completion detection."""
        job = Job(total_tasks=10)
        assert not job.is_finished
        
        job.completed_tasks = 10
        assert job.is_finished
    
    def test_job_metadata(self):
        """Test job metadata storage."""
        job = Job(metadata={"priority": "high", "source": "api"})
        assert job.metadata["priority"] == "high"
        assert job.metadata["source"] == "api"


class TestScrapeTaskModel:
    """Tests for ScrapeTask model."""
    
    def test_task_creation(self):
        """Test creating a basic task."""
        task = ScrapeTask(
            url="https://example.com/page1",
            job_id=uuid.uuid4(),
        )
        assert task.url == "https://example.com/page1"
        assert task.status == TaskStatus.PENDING
        assert task.attempt_count == 0
        assert task.max_attempts == 5
        assert task.circuit_state == CircuitState.CLOSED
    
    def test_task_claim(self):
        """Test claiming a task."""
        task = ScrapeTask(url="https://example.com")
        worker_id = uuid.uuid4()
        
        assert task.claim(worker_id)
        assert task.status == TaskStatus.CLAIMED
        assert task.claimed_by == worker_id
        assert task.claimed_at is not None
        
        # Cannot claim twice
        assert not task.claim(uuid.uuid4())
    
    def test_task_mark_processing(self):
        """Test marking task as processing."""
        task = ScrapeTask(url="https://example.com")
        task.mark_processing()
        assert task.status == TaskStatus.PROCESSING
        assert task.attempt_count == 1
    
    def test_task_mark_completed(self):
        """Test marking task as completed."""
        task = ScrapeTask(url="https://example.com")
        task.mark_completed()
        assert task.status == TaskStatus.COMPLETED
        assert task.completed_at is not None
    
    def test_task_mark_failed_with_retry(self):
        """Test marking task as failed with retry scheduled."""
        task = ScrapeTask(url="https://example.com", max_attempts=3)
        next_retry = datetime.utcnow() + timedelta(minutes=5)
        
        assert task.mark_failed(next_retry)
        assert task.status == TaskStatus.PENDING
        assert task.next_retry_at == next_retry
    
    def test_task_mark_failed_dead_letter(self):
        """Test marking task as dead letter after max attempts."""
        task = ScrapeTask(url="https://example.com", max_attempts=1, attempt_count=1)
        
        assert not task.mark_failed()
        assert task.status == TaskStatus.DEAD_LETTER
        assert task.completed_at is not None
    
    def test_task_can_retry(self):
        """Test retry eligibility."""
        task = ScrapeTask(url="https://example.com", max_attempts=5, attempt_count=3)
        assert task.can_retry
        
        task.attempt_count = 5
        assert not task.can_retry
    
    def test_task_circuit_breaker(self):
        """Test circuit breaker operations."""
        task = ScrapeTask(url="https://example.com")
        assert task.circuit_state == CircuitState.CLOSED
        
        task.open_circuit()
        assert task.circuit_state == CircuitState.OPEN
        assert task.circuit_opened_at is not None
        
        task.close_circuit()
        assert task.circuit_state == CircuitState.CLOSED
        assert task.circuit_opened_at is None


class TestScrapeResultModel:
    """Tests for ScrapeResult model."""
    
    def test_result_creation(self):
        """Test creating a basic result."""
        result = ScrapeResult(
            task_id=uuid.uuid4(),
            status_code=200,
            scrape_duration_ms=1500,
        )
        assert result.status_code == 200
        assert result.scrape_duration_ms == 1500
        assert not result.llm_processed
        assert result.extracted_data == {}
    
    def test_result_is_success(self):
        """Test success detection."""
        result_200 = ScrapeResult(task_id=uuid.uuid4(), status_code=200, scrape_duration_ms=100)
        assert result_200.is_success
        
        result_404 = ScrapeResult(task_id=uuid.uuid4(), status_code=404, scrape_duration_ms=100)
        assert not result_404.is_success
    
    def test_result_llm_processing(self):
        """Test LLM processing status."""
        result = ScrapeResult(task_id=uuid.uuid4(), status_code=200, scrape_duration_ms=100)
        assert not result.llm_processed
        
        result.mark_llm_processed({"summary": "test"})
        assert result.llm_processed
        assert result.llm_result == {"summary": "test"}
    
    def test_result_llm_failure(self):
        """Test LLM processing failure."""
        result = ScrapeResult(task_id=uuid.uuid4(), status_code=200, scrape_duration_ms=100)
        result.mark_llm_failed("API rate limit exceeded")
        assert result.llm_error == "API rate limit exceeded"


class TestScrapeFailureModel:
    """Tests for ScrapeFailure model."""
    
    def test_failure_creation(self):
        """Test creating a basic failure."""
        failure = ScrapeFailure(
            task_id=uuid.uuid4(),
            error_code="ERR_TUNNEL",
            error_message="Tunnel connection failed",
            attempt_number=1,
        )
        assert failure.error_code == "ERR_TUNNEL"
        assert failure.error_message == "Tunnel connection failed"
        assert failure.attempt_number == 1
    
    def test_failure_auto_classification(self):
        """Test automatic error classification."""
        # Transient error
        failure = ScrapeFailure.create(
            task_id=uuid.uuid4(),
            error_code="ERR_TUNNEL",
            error_message="Tunnel error",
            attempt_number=1,
        )
        assert failure.error_category == FailureCategory.TRANSIENT
        assert failure.is_retryable
        
        # Terminal error
        failure = ScrapeFailure.create(
            task_id=uuid.uuid4(),
            error_code="HTTP_403",
            error_message="Forbidden",
            attempt_number=1,
        )
        assert failure.error_category == FailureCategory.TERMINAL
        assert not failure.is_retryable
        
        # Unknown error
        failure = ScrapeFailure.create(
            task_id=uuid.uuid4(),
            error_code="UNKNOWN_ERROR",
            error_message="Unknown error",
            attempt_number=1,
        )
        assert failure.error_category == FailureCategory.UNKNOWN
        assert not failure.is_retryable
    
    def test_failure_reclassification(self):
        """Test manual reclassification."""
        failure = ScrapeFailure(
            task_id=uuid.uuid4(),
            error_code="UNKNOWN_123",
            error_message="Unknown error",
            attempt_number=1,
        )
        assert failure.error_category == FailureCategory.UNKNOWN
        
        failure.reclassify(FailureCategory.TRANSIENT)
        assert failure.error_category == FailureCategory.TRANSIENT
        assert failure.is_retryable


class TestProxySessionModel:
    """Tests for ProxySession model."""
    
    def test_proxy_creation(self):
        """Test creating a basic proxy session."""
        proxy = ProxySession(
            proxy_host="proxy.oxylabs.io",
            proxy_port=12345,
        )
        assert proxy.proxy_host == "proxy.oxylabs.io"
        assert proxy.proxy_port == 12345
        assert proxy.status == ProxyStatus.ACTIVE
        assert proxy.tunnel_error_count == 0
    
    def test_proxy_is_available(self):
        """Test availability check."""
        proxy = ProxySession(proxy_host="proxy.example.com", proxy_port=8080)
        assert proxy.is_available
        
        proxy.status = ProxyStatus.ERROR
        assert not proxy.is_available
        
        proxy.status = ProxyStatus.ACTIVE
        proxy.set_cooldown(3600)
        assert not proxy.is_available
    
    def test_proxy_tunnel_error(self):
        """Test recording tunnel errors."""
        proxy = ProxySession(proxy_host="proxy.example.com", proxy_port=8080)
        
        proxy.record_tunnel_error("Connection timeout")
        assert proxy.tunnel_error_count == 1
        assert proxy.last_error == "Connection timeout"
        assert proxy.status == ProxyStatus.ACTIVE
        
        # After 10 errors, auto-degrade
        proxy.tunnel_error_count = 9
        proxy.record_tunnel_error()
        assert proxy.status == ProxyStatus.ERROR
        
        # After 20 errors, exhaust
        proxy.tunnel_error_count = 19
        proxy.record_tunnel_error()
        assert proxy.status == ProxyStatus.EXHAUSTED
    
    def test_proxy_cooldown(self):
        """Test cooldown setting."""
        proxy = ProxySession(proxy_host="proxy.example.com", proxy_port=8080)
        proxy.set_cooldown(300)
        assert proxy.cooldown_until is not None
        assert proxy.cooldown_until > datetime.utcnow()
    
    def test_proxy_health_check(self):
        """Test health check."""
        proxy = ProxySession(proxy_host="proxy.example.com", proxy_port=8080)
        assert proxy.is_healthy
        
        proxy.tunnel_error_count = 5
        assert proxy.is_healthy
        
        proxy.tunnel_error_count = 15
        assert not proxy.is_healthy


class TestWorkerInstanceModel:
    """Tests for WorkerInstance model."""
    
    def test_worker_creation(self):
        """Test creating a basic worker."""
        worker = WorkerInstance(
            instance_name="worker-1",
        )
        assert worker.instance_name == "worker-1"
        assert worker.status == WorkerStatus.HEALTHY
        assert worker.claimed_tasks == 0
        assert worker.completed_tasks == 0
        assert worker.failed_tasks == 0
    
    def test_worker_heartbeat(self):
        """Test heartbeat update."""
        worker = WorkerInstance(instance_name="worker-1")
        old_heartbeat = worker.last_heartbeat_at
        worker.heartbeat()
        assert worker.last_heartbeat_at >= old_heartbeat
    
    def test_worker_task_claiming(self):
        """Test task claim/release."""
        worker = WorkerInstance(instance_name="worker-1")
        
        worker.claim_task()
        assert worker.claimed_tasks == 1
        
        worker.release_task()
        assert worker.claimed_tasks == 0
        
        # Cannot go negative
        worker.release_task()
        assert worker.claimed_tasks == 0
    
    def test_worker_task_completion(self):
        """Test task completion tracking."""
        worker = WorkerInstance(instance_name="worker-1")
        worker.claimed_tasks = 1
        
        worker.task_completed()
        assert worker.completed_tasks == 1
        assert worker.claimed_tasks == 0
    
    def test_worker_task_failure(self):
        """Test task failure tracking."""
        worker = WorkerInstance(instance_name="worker-1")
        worker.claimed_tasks = 1
        
        worker.task_failed()
        assert worker.failed_tasks == 1
        assert worker.claimed_tasks == 0
    
    def test_worker_circuit_breaker(self):
        """Test circuit breaker operations."""
        worker = WorkerInstance(instance_name="worker-1")
        
        assert not worker.is_circuit_open
        
        worker.open_circuit()
        assert worker.is_circuit_open
        assert worker.circuit_breaker_opened_at is not None
        
        worker.close_circuit()
        assert not worker.is_circuit_open
        
        worker.half_open_circuit()
        assert worker.circuit_breaker_global_state == CircuitState.HALF_OPEN
    
    def test_worker_status_changes(self):
        """Test worker status changes."""
        worker = WorkerInstance(instance_name="worker-1")
        
        worker.mark_degraded()
        assert worker.status == WorkerStatus.DEGRADED
        
        worker.mark_healthy()
        assert worker.status == WorkerStatus.HEALTHY
        
        worker.mark_offline()
        assert worker.status == WorkerStatus.OFFLINE
        assert worker.claimed_tasks == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
