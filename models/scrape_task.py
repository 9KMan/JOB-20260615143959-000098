// models/scrape_task.py
"""ScrapeTask model for individual URL scraping tasks.

Each task represents a single URL to scrape with retry logic,
circuit breaker state, and task ownership tracking.
"""
from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    DateTime,
    Enum as SQLEnum,
    Index,
    ForeignKey,
    text,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

from models import Base
from models.enums import TaskStatus, CircuitState


class ScrapeTask(Base):
    """Individual scraping task for a single URL.
    
    Tasks are claimed by workers using SELECT FOR UPDATE SKIP LOCKED
    to prevent race conditions in distributed processing.
    
    Attributes:
        id: UUID primary key.
        job_id: Foreign key to parent job.
        url: Target URL to scrape.
        priority: Higher priority tasks are claimed first.
        status: Current task status.
        attempt_count: Number of attempts made.
        max_attempts: Maximum retry attempts before dead-letter.
        circuit_state: Circuit breaker state for this task's domain.
        circuit_opened_at: When circuit was opened.
        claimed_by: Worker instance ID that claimed this task.
        claimed_at: When task was claimed.
        result_id: Foreign key to successful result (if any).
        failure_id: Foreign key to failure record (if any).
        created_at: When task was created.
        updated_at: Last update timestamp.
        completed_at: When task finished processing.
        next_retry_at: When to retry (for backoff).
        metadata: JSONB for page-specific params, selectors, etc.
    """
    __tablename__ = "scrape_tasks"
    __table_args__ = (
        # Composite index for worker task polling
        Index(
            "idx_tasks_poll",
            "status",
            text("priority DESC"),
            "next_retry_at",
            postgresql_where=(text("status IN ('pending', 'claimed')")),
        ),
        # Index for job progress tracking
        Index("idx_tasks_job_status", "job_id", "status"),
        # Index for worker ownership queries
        Index("idx_tasks_claimed_by", "claimed_by"),
        # Index for finding tasks ready for retry
        Index(
            "idx_tasks_retry",
            "status",
            "next_retry_at",
            postgresql_where=(text("status = 'pending' AND next_retry_at IS NOT NULL")),
        ),
        # Check constraint for attempt count
        CheckConstraint("attempt_count >= 0", name="check_attempt_count_positive"),
        CheckConstraint("attempt_count <= max_attempts", name="check_attempt_count_limit"),
        {
            "comment": "Individual scrape tasks with retry and circuit breaker support",
            "schema": "public",
        },
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    url: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="Target URL to scrape",
    )
    
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Higher priority tasks are claimed first",
    )
    
    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus, name="task_status", create_type=False),
        nullable=False,
        default=TaskStatus.PENDING,
        server_default=text("'pending'"),
        index=True,
    )
    
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
        server_default=text("5"),
    )
    
    circuit_state: Mapped[CircuitState] = mapped_column(
        SQLEnum(CircuitState, name="circuit_state", create_type=False),
        nullable=False,
        default=CircuitState.CLOSED,
        server_default=text("'closed'"),
    )
    
    circuit_opened_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    claimed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Worker instance ID that claimed this task",
    )
    
    claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    result_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scrape_results.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    failure_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scrape_failures.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("NOW()"),
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("NOW()"),
    )
    
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    
    metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
        comment="Page-specific params, selectors, headers, etc.",
    )

    # Relationships
    job: Mapped["Job"] = relationship("Job", back_populates="tasks")
    
    result: Mapped[Optional["ScrapeResult"]] = relationship(
        "ScrapeResult",
        back_populates="task",
        foreign_keys=[result_id],
    )
    
    failure: Mapped[Optional["ScrapeFailure"]] = relationship(
        "ScrapeFailure",
        back_populates="task",
        foreign_keys=[failure_id],
    )

    def __repr__(self) -> str:
        return f"<ScrapeTask(id={self.id}, url={self.url[:50]}, status={self.status.value})>"

    @property
    def can_retry(self) -> bool:
        """Check if task can be retried."""
        return (
            self.attempt_count < self.max_attempts
            and self.status in (TaskStatus.PENDING, TaskStatus.FAILED)
        )

    @property
    def is_terminal(self) -> bool:
        """Check if task has reached terminal state."""
        return self.status in (TaskStatus.COMPLETED, TaskStatus.DEAD_LETTER)

    def claim(self, worker_id: uuid.UUID) -> bool:
        """Attempt to claim this task for a worker.
        
        Args:
            worker_id: UUID of the worker claiming this task.
            
        Returns:
            True if claim was successful, False otherwise.
        """
        if self.status != TaskStatus.PENDING:
            return False
        self.status = TaskStatus.CLAIMED
        self.claimed_by = worker_id
        self.claimed_at = datetime.utcnow()
        return True

    def mark_processing(self) -> None:
        """Mark task as currently being processed."""
        self.status = TaskStatus.PROCESSING
        self.attempt_count += 1

    def mark_completed(self) -> None:
        """Mark task as successfully completed."""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.utcnow()

    def mark_failed(self, next_retry: Optional[datetime] = None) -> bool:
        """Mark task as failed, scheduling retry if allowed.
        
        Args:
            next_retry: Optional datetime to schedule retry.
            
        Returns:
            True if retry is scheduled, False if dead-lettered.
        """
        if self.attempt_count >= self.max_attempts:
            self.status = TaskStatus.DEAD_LETTER
            self.completed_at = datetime.utcnow()
            return False
        self.status = TaskStatus.PENDING
        self.next_retry_at = next_retry
        return True

    def open_circuit(self) -> None:
        """Open the circuit breaker for this task."""
        self.circuit_state = CircuitState.OPEN
        self.circuit_opened_at = datetime.utcnow()

    def close_circuit(self) -> None:
        """Close the circuit breaker for this task."""
        self.circuit_state = CircuitState.CLOSED
        self.circuit_opened_at = None
