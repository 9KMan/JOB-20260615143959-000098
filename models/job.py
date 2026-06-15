// models/job.py
"""Job/Batch model for organizing scrape tasks.

A Job represents a batch of URLs to scrape with shared configuration
and progress tracking.
"""
from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Enum as SQLEnum,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column

from models import Base
from models.enums import JobStatus


class Job(Base):
    """Represents a scraping job/batch containing multiple tasks.
    
    Jobs track overall progress and status for a collection of URLs.
    Uses soft-delete pattern via metadata to preserve historical context.
    
    Attributes:
        id: UUID primary key.
        name: Optional human-readable name for the job.
        status: Current job status (pending, running, paused, completed, failed).
        total_tasks: Total number of tasks in this job.
        completed_tasks: Number of successfully completed tasks.
        failed_tasks: Number of failed tasks.
        created_at: Timestamp when job was created.
        updated_at: Timestamp of last update.
        completed_at: Timestamp when job finished (nullable).
        metadata: JSONB for input params, priority, configuration.
    """
    __tablename__ = "jobs"
    __table_args__ = (
        Index("idx_jobs_status", "status"),
        Index("idx_jobs_created_at", "created_at"),
        {
            "comment": "Scraping jobs/batches containing multiple tasks",
            "schema": "public",
        },
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    
    name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Human-readable job name",
    )
    
    status: Mapped[JobStatus] = mapped_column(
        SQLEnum(JobStatus, name="job_status", create_type=False),
        nullable=False,
        default=JobStatus.PENDING,
        server_default=text("'pending'"),
        comment="Current job status",
    )
    
    total_tasks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Total number of tasks in this job",
    )
    
    completed_tasks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Number of successfully completed tasks",
    )
    
    failed_tasks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Number of failed tasks",
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
        comment="Timestamp when job finished",
    )
    
    metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
        comment="Input params, priority, configuration",
    )

    # Relationships
    tasks: Mapped[list["ScrapeTask"]] = relationship(
        "ScrapeTask",
        back_populates="job",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    
    worker_instances: Mapped[list["WorkerInstance"]] = relationship(
        "WorkerInstance",
        back_populates="current_job",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, status={self.status.value}, tasks={self.total_tasks})>"

    @property
    def progress_percentage(self) -> float:
        """Calculate job progress as percentage."""
        if self.total_tasks == 0:
            return 0.0
        return (self.completed_tasks + self.failed_tasks) / self.total_tasks * 100

    @property
    def is_finished(self) -> bool:
        """Check if all tasks are done (completed or dead-letter)."""
        return (self.completed_tasks + self.failed_tasks) >= self.total_tasks

    def increment_completed(self) -> None:
        """Increment completed task counter."""
        self.completed_tasks += 1
        self._check_completion()

    def increment_failed(self) -> None:
        """Increment failed task counter."""
        self.failed_tasks += 1
        self._check_completion()

    def _check_completion(self) -> None:
        """Check if job is complete and update status."""
        if self.is_finished:
            self.completed_at = datetime.utcnow()
            if self.failed_tasks > 0 and self.completed_tasks == 0:
                self.status = JobStatus.FAILED
            else:
                self.status = JobStatus.COMPLETED
