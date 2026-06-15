# src/app/models/models.py
"""
SQLAlchemy ORM Models.
Defines all database tables for the scraping infrastructure.
"""
import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    LargeBinary,
    Numeric,
    String,
    Text,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base


class JobStatus(str, PyEnum):
    """Job execution status."""
    PENDING = "pending"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"
    MANUAL_REVIEW = "manual_review"


class FailureCategory(str, PyEnum):
    """Categorization of failure types."""
    PROXY_ERROR = "proxy_error"
    ANTI_BOT = "anti_bot"
    NAVIGATION = "navigation"
    CONTENT = "content"
    TERMINAL = "terminal"
    INFRASTRUCTURE = "infrastructure"
    UNKNOWN = "unknown"


class FailureClass(str, PyEnum):
    """Failure classification: transient (recoverable) or terminal (permanent)."""
    TRANSIENT = "transient"
    TERMINAL = "terminal"
    AMBIGUOUS = "ambiguous"


class RecoveryStatus(str, PyEnum):
    """Recovery pipeline status."""
    PENDING = "pending"
    ATTEMPTED = "attempted"
    RECOVERED = "recovered"
    FAILED = "failed"
    SKIPPED = "skipped"


class ManualReviewStatus(str, PyEnum):
    """Manual review queue status."""
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class ProxyStatus(str, PyEnum):
    """Proxy health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    ROTATING = "rotating"


class BatchStatus(str, PyEnum):
    """Batch job status."""
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class User(Base):
    """User/operator account for API authentication."""
    __tablename__ = "users"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    # Relationships
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")
    manual_reviews: Mapped[list["ManualReview"]] = relationship(back_populates="reviewer")
    
    __table_args__ = (
        Index("ix_users_username", "username"),
        Index("ix_users_email", "email"),
    )


class ScrapingTarget(Base):
    """Configuration for scraping targets (URLs, selectors, etc.)."""
    __tablename__ = "scraping_targets"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    selectors: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    stealth_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rate_limit_requests: Mapped[int] = mapped_column(Integer, default=10)
    rate_limit_period: Mapped[int] = mapped_column(Integer, default=60)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    # Relationships
    jobs: Mapped[list["Job"]] = relationship(back_populates="target")
    
    __table_args__ = (
        Index("ix_scraping_targets_name", "name"),
        Index("ix_scraping_targets_active", "is_active"),
    )


class ProxyPool(Base):
    """Proxy pool entry tracking Oxylabs proxy health and usage."""
    __tablename__ = "proxy_pool"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    proxy_host: Mapped[str] = mapped_column(String(255), nullable=False)
    proxy_port: Mapped[int] = mapped_column(Integer, nullable=False)
    proxy_username: Mapped[str] = mapped_column(String(255), nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    isp: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[ProxyStatus] = mapped_column(
        Enum(ProxyStatus), default=ProxyStatus.HEALTHY
    )
    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    successful_requests: Mapped[int] = mapped_column(Integer, default=0)
    failed_requests: Mapped[int] = mapped_column(Integer, default=0)
    tunnel_errors: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_health_check_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    health_score: Mapped[float] = mapped_column(Float, default=100.0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    # Relationships
    health_records: Mapped[list["ProxyHealth"]] = relationship(back_populates="proxy")
    
    __table_args__ = (
        Index("ix_proxy_pool_status", "status"),
        Index("ix_proxy_pool_health_score", "health_score"),
        UniqueConstraint("proxy_host", "proxy_port", name="uq_proxy_host_port"),
    )
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100
    
    @property
    def tunnel_error_rate(self) -> float:
        """Calculate tunnel error rate percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.tunnel_errors / self.total_requests) * 100


class ProxyHealth(Base):
    """Historical proxy health checks for monitoring and analysis."""
    __tablename__ = "proxy_health"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    proxy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proxy_pool.id"), nullable=False
    )
    check_url: Mapped[str] = mapped_column(Text, nullable=False)
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_healthy: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    proxy: Mapped["ProxyPool"] = relationship(back_populates="health_records")
    
    __table_args__ = (
        Index("ix_proxy_health_proxy_id", "proxy_id"),
        Index("ix_proxy_health_created_at", "created_at"),
    )


class Batch(Base):
    """Batch of scraping jobs for grouped processing."""
    __tablename__ = "batches"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[BatchStatus] = mapped_column(Enum(BatchStatus), default=BatchStatus.CREATED)
    total_jobs: Mapped[int] = mapped_column(Integer, default=0)
    completed_jobs: Mapped[int] = mapped_column(Integer, default=0)
    failed_jobs: Mapped[int] = mapped_column(Integer, default=0)
    pending_jobs: Mapped[int] = mapped_column(Integer, default=0)
    success_rate: Mapped[float] = mapped_column(Float, default=0.0)
    validity_rate: Mapped[float] = mapped_column(Float, default=0.0)
    input_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    # Relationships
    jobs: Mapped[list["Job"]] = relationship(back_populates="batch")
    creator: Mapped[Optional["User"]] = relationship(back_populates="batches")
    
    __table_args__ = (
        Index("ix_batches_status", "status"),
        Index("ix_batches_created_at", "created_at"),
    )


class Job(Base):
    """Individual scraping job."""
    __tablename__ = "jobs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("batches.id"), nullable=True
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scraping_targets.id"), nullable=False
    )
    worker_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.PENDING)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    
    # Input parameters
    url: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Proxy assignment
    proxy_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proxy_pool.id"), nullable=True
    )
    session_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Retry tracking
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    last_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Timing
    queued_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    # Relationships
    batch: Mapped[Optional["Batch"]] = relationship(back_populates="jobs")
    target: Mapped["ScrapingTarget"] = relationship(back_populates="jobs")
    proxy: Mapped[Optional["ProxyPool"]] = relationship()
    result: Mapped[Optional["JobResult"]] = relationship(back_populates="job", uselist=False)
    failure: Mapped[Optional["JobFailure"]] = relationship(back_populates="job", uselist=False)
    
    __table_args__ = (
        Index("ix_jobs_batch_id", "batch_id"),
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_worker_id", "worker_id"),
        Index("ix_jobs_priority_status", "priority", "status"),
        Index("ix_jobs_created_at", "created_at"),
    )


class JobResult(Base):
    """Successful scraping result."""
    __tablename__ = "job_results"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), unique=True, nullable=False
    )
    
    # Raw and processed data
    raw_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    processed_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    llm_validated: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    llm_validation_details: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Quality metrics
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    validity_score: Mapped[float] = mapped_column(Float, default=1.0)
    validation_errors: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    
    # Timing metrics
    page_load_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    extraction_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Metadata
    screenshot_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    final_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    job: Mapped["Job"] = relationship(back_populates="result")


class JobFailure(Base):
    """Job failure record with classification."""
    __tablename__ = "job_failures"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), unique=True, nullable=False
    )
    
    # Failure details
    error_type: Mapped[str] = mapped_column(String(100), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    error_details: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    stack_trace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Classification
    failure_category: Mapped[FailureCategory] = mapped_column(
        Enum(FailureCategory), nullable=False
    )
    failure_class: Mapped[FailureClass] = mapped_column(
        Enum(FailureClass), nullable=False
    )
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0)
    classification_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Recovery
    recovery_status: Mapped[RecoveryStatus] = mapped_column(
        Enum(RecoveryStatus), default=RecoveryStatus.PENDING
    )
    recovery_attempts: Mapped[int] = mapped_column(Integer, default=0)
    recovered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Screenshot of failure state
    screenshot_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    # Relationships
    job: Mapped["Job"] = relationship(back_populates="failure")
    recovery_actions: Mapped[list["RecoveryAction"]] = relationship(back_populates="failure")
    manual_review: Mapped[Optional["ManualReview"]] = relationship(
        back_populates="failure", uselist=False
    )
    
    __table_args__ = (
        Index("ix_job_failures_category", "failure_category"),
        Index("ix_job_failures_class", "failure_class"),
        Index("ix_job_failures_recovery_status", "recovery_status"),
    )


class RecoveryAction(Base):
    """Record of recovery actions taken for a failure."""
    __tablename__ = "recovery_actions"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    failure_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_failures.id"), nullable=False
    )
    
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    action_details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    action_result: Mapped[str] = mapped_column(String(50), nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    failure: Mapped["JobFailure"] = relationship(back_populates="recovery_actions")


class ManualReview(Base):
    """Manual review queue for ambiguous or escalated failures."""
    __tablename__ = "manual_reviews"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    failure_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_failures.id"), unique=True, nullable=False
    )
    reviewer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    
    status: Mapped[ManualReviewStatus] = mapped_column(
        Enum(ManualReviewStatus), default=ManualReviewStatus.PENDING
    )
    
    # Review details
    priority: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decision: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_fix: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Classification after review
    final_failure_class: Mapped[Optional[FailureClass]] = mapped_column(
        Enum(FailureClass), nullable=True
    )
    
    assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    # Relationships
    failure: Mapped["JobFailure"] = relationship(back_populates="manual_review")
    reviewer: Mapped[Optional["User"]] = relationship(back_populates="manual_reviews")
    
    __table_args__ = (
        Index("ix_manual_reviews_status", "status"),
        Index("ix_manual_reviews_priority", "priority"),
    )


class AuditLog(Base):
    """Audit log for tracking all operations."""
    __tablename__ = "audit_logs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    
    details: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user: Mapped[Optional["User"]] = relationship(back_populates="audit_logs")
    
    __table_args__ = (
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_action", "action"),
    )
