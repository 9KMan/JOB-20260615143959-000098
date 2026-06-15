// models/worker.py
"""WorkerInstance model for tracking worker fleet state.

Monitors worker health, circuit breaker state, and task assignments
across the distributed worker fleet.
"""
from datetime import datetime
from typing import Optional, List
import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Enum as SQLEnum,
    Index,
    ForeignKey,
    text,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column

from models import Base
from models.enums import WorkerStatus, CircuitState


class WorkerInstance(Base):
    """Tracks worker fleet state and health.
    
    Each worker instance is identified by container hostname and
    maintains its own circuit breaker state.
    
    Attributes:
        id: UUID primary key.
        instance_name: Container hostname.
        status: Current worker status.
        current_job_id: Job currently being processed.
        claimed_tasks: Number of tasks currently claimed.
        completed_tasks: Total completed tasks.
        failed_tasks: Total failed tasks.
        circuit_breaker_global_state: Global circuit breaker state.
        circuit_breaker_opened_at: When global circuit was opened.
        last_heartbeat_at: Last heartbeat timestamp.
        created_at: When worker registered.
    """
    __tablename__ = "worker_instances"
    __table_args__ = (
        Index("idx_workers_status", "status"),
        Index("idx_workers_circuit_state", "circuit_breaker_global_state"),
        Index("idx_workers_heartbeat", "last_heartbeat_at"),
        CheckConstraint("claimed_tasks >= 0", name="check_claimed_tasks_nonnegative"),
        CheckConstraint("completed_tasks >= 0", name="check_completed_tasks_nonnegative"),
        CheckConstraint("failed_tasks >= 0", name="check_failed_tasks_nonnegative"),
        {
            "comment": "Worker fleet state and health tracking",
            "schema": "public",
        },
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    
    instance_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        comment="Container hostname",
    )
    
    status: Mapped[WorkerStatus] = mapped_column(
        SQLEnum(WorkerStatus, name="worker_status", create_type=False),
        nullable=False,
        default=WorkerStatus.HEALTHY,
        server_default=text("'healthy'"),
        index=True,
    )
    
    current_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    claimed_tasks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    
    completed_tasks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    
    failed_tasks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    
    circuit_breaker_global_state: Mapped[CircuitState] = mapped_column(
        SQLEnum(CircuitState, name="circuit_state", create_type=False),
        nullable=False,
        default=CircuitState.CLOSED,
        server_default=text("'closed'"),
    )
    
    circuit_breaker_opened_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("NOW()"),
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("NOW()"),
    )

    # Relationships
    current_job: Mapped[Optional["Job"]] = relationship(
        "Job",
        back_populates="worker_instances",
    )

    def __repr__(self) -> str:
        return f"<WorkerInstance(id={self.id}, name={self.instance_name}, status={self.status.value})>"

    @property
    def is_healthy(self) -> bool:
        """Check if worker is healthy."""
        return self.status == WorkerStatus.HEALTHY

    @property
    def is_circuit_open(self) -> bool:
        """Check if global circuit breaker is open."""
        return self.circuit_breaker_global_state == CircuitState.OPEN

    def heartbeat(self) -> None:
        """Update heartbeat timestamp."""
        self.last_heartbeat_at = datetime.utcnow()

    def claim_task(self) -> None:
        """Increment claimed task count."""
        self.claimed_tasks += 1

    def release_task(self) -> None:
        """Decrement claimed task count."""
        self.claimed_tasks = max(0, self.claimed_tasks - 1)

    def task_completed(self) -> None:
        """Record successful task completion."""
        self.completed_tasks += 1
        self.release_task()

    def task_failed(self) -> None:
        """Record task failure."""
        self.failed_tasks += 1
        self.release_task()

    def mark_degraded(self, reason: Optional[str] = None) -> None:
        """Mark worker as degraded.
        
        Args:
            reason: Optional reason for degradation.
        """
        self.status = WorkerStatus.DEGRADED

    def mark_offline(self) -> None:
        """Mark worker as offline."""
        self.status = WorkerStatus.OFFLINE
        self.claimed_tasks = 0

    def mark_healthy(self) -> None:
        """Mark worker as healthy."""
        self.status = WorkerStatus.HEALTHY

    def open_circuit(self) -> None:
        """Open global circuit breaker."""
        self.circuit_breaker_global_state = CircuitState.OPEN
        self.circuit_breaker_opened_at = datetime.utcnow()

    def close_circuit(self) -> None:
        """Close global circuit breaker."""
        self.circuit_breaker_global_state = CircuitState.CLOSED
        self.circuit_breaker_opened_at = None

    def half_open_circuit(self) -> None:
        """Set circuit to half-open (testing)."""
        self.circuit_breaker_global_state = CircuitState.HALF_OPEN


# Import at bottom to avoid circular imports
from models.job import Job
