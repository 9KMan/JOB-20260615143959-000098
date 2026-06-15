// src/models/job.py
"""Scrape job model for individual URL scraping tasks."""
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List

from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, Enum as SQLEnum, ForeignKey, Index, Boolean
from sqlalchemy.orm import relationship

from .base import Base


class JobStatus(str, Enum):
    """Job processing status."""
    PENDING = "pending"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINAL = "terminal"  # Permanently failed
    CANCELLED = "cancelled"


class JobError(Base):
    """Embedded error information for jobs."""
    
    __tablename__ = "job_errors"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    
    # Error details
    code = Column(String(50), nullable=False)  # ERR_TUNNEL_CONNECTION_FAILED, etc.
    category = Column(String(20), nullable=False)  # transient, terminal, unknown
    message = Column(Text, nullable=True)
    
    # Context
    proxy_exit = Column(String(255), nullable=True)
    attempt = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    job = relationship("Job", back_populates="errors")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_id": self.id,
            "code": self.code,
            "category": self.category,
            "message": self.message,
            "proxy_exit": self.proxy_exit,
            "attempt": self.attempt,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Job(Base):
    """Scrape job model for individual URL scraping tasks."""
    
    __tablename__ = "jobs"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    batch_id = Column(String(36), ForeignKey("batches.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # URL and site configuration
    url = Column(Text, nullable=False)
    site_config = Column(String(50), default="default")
    
    # Status
    status = Column(
        SQLEnum(JobStatus),
        default=JobStatus.PENDING,
        nullable=False,
        index=True
    )
    
    # Priority (for queue ordering)
    priority = Column(Integer, default=5)  # 1-10, higher = more urgent
    
    # Retry information
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=5)
    last_retry_at = Column(DateTime, nullable=True)
    next_retry_at = Column(DateTime, nullable=True)
    
    # Proxy information
    proxy_session_id = Column(String(255), nullable=True)
    proxy_exit_used = Column(String(255), nullable=True)
    
    # Error information (latest)
    error_code = Column(String(50), nullable=True)
    error_category = Column(String(20), nullable=True)
    error_message = Column(Text, nullable=True)
    error_proxy_exit = Column(String(255), nullable=True)
    
    # Result reference
    result_id = Column(String(36), ForeignKey("results.id", ondelete="SET NULL"), nullable=True)
    
    # Metadata
    metadata = Column(JSON, default=dict)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    queued_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationship
    batch = relationship("Batch", back_populates="jobs")
    errors = relationship("JobError", back_populates="job", cascade="all, delete-orphan")
    result = relationship("Result", back_populates="job", foreign_keys=[result_id])
    
    __table_args__ = (
        Index("ix_jobs_batch_status", "batch_id", "status"),
        Index("ix_jobs_status_priority", "status", "priority"),
        Index("ix_jobs_next_retry", "next_retry_at", "status"),
    )
    
    def __repr__(self) -> str:
        return f"<Job(id={self.id}, url={self.url[:50]}, status={self.status})>"
    
    @property
    def is_recoverable(self) -> bool:
        """Check if job can be retried."""
        return (
            self.status in (JobStatus.FAILED, JobStatus.TERMINAL)
            and self.retry_count < self.max_retries
            and self.error_category != "terminal"
        )
    
    @property
    def attempts_remaining(self) -> int:
        """Get remaining retry attempts."""
        return max(0, self.max_retries - self.retry_count)
    
    def to_dict(self, include_errors: bool = False) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        result = {
            "job_id": self.id,
            "batch_id": self.batch_id,
            "url": self.url,
            "site_config": self.site_config,
            "status": self.status.value,
            "priority": self.priority,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "attempts_remaining": self.attempts_remaining,
            "is_recoverable": self.is_recoverable,
            "proxy_session_id": self.proxy_session_id,
            "proxy_exit_used": self.proxy_exit_used,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "queued_at": self.queued_at.isoformat() if self.queued_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        
        # Include error info
        if self.error_code:
            result["error"] = {
                "code": self.error_code,
                "category": self.error_category,
                "message": self.error_message,
                "proxy_exit": self.error_proxy_exit,
                "attempts": self.retry_count,
                "last_attempt": self.last_retry_at.isoformat() if self.last_retry_at else None,
            }
        
        # Include errors list
        if include_errors:
            result["errors"] = [e.to_dict() for e in self.errors]
        
        return result
    
    def mark_failed(
        self,
        error_code: str,
        error_category: str,
        error_message: str,
        proxy_exit: Optional[str] = None
    ):
        """Mark job as failed with error details."""
        self.status = JobStatus.FAILED
        self.error_code = error_code
        self.error_category = error_category
        self.error_message = error_message
        self.error_proxy_exit = proxy_exit
        self.last_retry_at = datetime.utcnow()
        self.retry_count += 1
        
        # Create error record
        error = JobError(
            job_id=self.id,
            code=error_code,
            category=error_category,
            message=error_message,
            proxy_exit=proxy_exit,
            attempt=self.retry_count
        )
        self.errors.append(error)
    
    def mark_completed(self):
        """Mark job as completed."""
        self.status = JobStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.error_code = None
        self.error_category = None
        self.error_message = None
    
    def mark_terminal(self, reason: str = "max_retries_exceeded"):
        """Mark job as terminal (permanently failed)."""
        self.status = JobStatus.TERMINAL
        self.completed_at = datetime.utcnow()
        self.metadata = self.metadata or {}
        self.metadata["terminal_reason"] = reason
