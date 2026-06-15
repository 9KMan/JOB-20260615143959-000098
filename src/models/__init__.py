# src/models/__init__.py
"""
Database models for the scraping framework.
"""
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text, JSON, Boolean, Index, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional, List
from enum import Enum
import uuid

from src.config import config

Base = declarative_base()


class JobStatus(str, Enum):
    """Status of a scraping job."""
    PENDING = "pending"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"
    RETRYING = "retrying"


class ErrorCategory(str, Enum):
    """Category of scraping error."""
    TRANSIENT = "transient"
    TERMINAL = "terminal"
    PROXY = "proxy"
    ANTI_BOT = "anti_bot"
    INFRA = "infra"
    UNKNOWN = "unknown"


class ScrapeJob(Base):
    """Main scraping job entity."""
    __tablename__ = "scrape_jobs"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    target_url = Column(Text, nullable=False, index=True)
    target_site = Column(String(255), nullable=True, index=True)
    status = Column(String(50), nullable=False, default=JobStatus.PENDING.value, index=True)
    
    # Retry tracking
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=config.rabbitmq.max_retries)
    last_retry_at = Column(DateTime(timezone=True), nullable=True)
    
    # Error tracking
    error_category = Column(String(50), nullable=True, index=True)
    error_code = Column(String(100), nullable=True, index=True)
    error_message = Column(Text, nullable=True)
    error_context = Column(JSON, nullable=True)
    is_permanent_failure = Column(Boolean, default=False)
    
    # Results
    scraped_data = Column(JSON, nullable=True)
    extraction_confidence = Column(String(20), nullable=True)
    raw_html_length = Column(Integer, nullable=True)
    
    # Timing
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    queued_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    total_duration_ms = Column(Integer, nullable=True)
    
    # Worker info
    assigned_worker_id = Column(String(255), nullable=True, index=True)
    proxy_exit_node = Column(Integer, nullable=True)
    
    # Queue info
    queue_name = Column(String(255), nullable=True, index=True)
    delivery_tag = Column(Integer, nullable=True)
    
    # Relationships
    error_logs = relationship("ErrorLog", back_populates="job", cascade="all, delete-orphan")
    proxy_errors = relationship("ProxyError", back_populates="job", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_jobs_status_created", "status", "created_at"),
        Index("idx_jobs_status_retry", "status", "retry_count"),
        Index("idx_jobs_error_category", "error_category", "status"),
    )
    
    def to_dict(self) -> dict:
        """Convert job to dictionary."""
        return {
            "id": self.id,
            "target_url": self.target_url,
            "target_site": self.target_site,
            "status": self.status,
            "retry_count": self.retry_count,
            "error_category": self.error_category,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "is_permanent_failure": self.is_permanent_failure,
            "scraped_data": self.scraped_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_duration_ms": self.total_duration_ms,
        }


class ErrorLog(Base):
    """Detailed error logging for debugging."""
    __tablename__ = "error_logs"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), ForeignKey("scrape_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    
    error_code = Column(String(100), nullable=True, index=True)
    error_message = Column(Text, nullable=True)
    error_category = Column(String(50), nullable=True, index=True)
    error_context = Column(JSON, nullable=True)
    
    # Stack trace or full error
    stack_trace = Column(Text, nullable=True)
    full_response = Column(Text, nullable=True)
    
    # Browser state
    page_url = Column(Text, nullable=True)
    page_title = Column(Text, nullable=True)
    screenshot_path = Column(Text, nullable=True)
    
    # Proxy info
    proxy_url = Column(Text, nullable=True)
    proxy_exit_node = Column(Integer, nullable=True)
    
    # Timing
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    retry_number = Column(Integer, default=0)
    
    # Relationships
    job = relationship("ScrapeJob", back_populates="error_logs")
    
    __table_args__ = (
        Index("idx_error_logs_job_time", "job_id", "occurred_at"),
    )


class ProxyError(Base):
    """Track proxy-specific errors for pattern detection."""
    __tablename__ = "proxy_errors"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), ForeignKey("scrape_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    
    error_code = Column(String(100), nullable=False, index=True)
    error_message = Column(Text, nullable=True)
    
    # Proxy details
    proxy_url = Column(Text, nullable=True)
    exit_node = Column(Integer, nullable=True, index=True)
    session_id = Column(String(255), nullable=True)
    
    # Response details
    status_code = Column(Integer, nullable=True)
    response_headers = Column(JSON, nullable=True)
    
    # Timing
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relationships
    job = relationship("ScrapeJob", back_populates="proxy_errors")
    
    __table_args__ = (
        Index("idx_proxy_errors_exit_time", "exit_node", "occurred_at"),
        Index("idx_proxy_errors_code_time", "error_code", "occurred_at"),
    )


class WorkerMetrics(Base):
    """Worker performance metrics."""
    __tablename__ = "worker_metrics"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    worker_id = Column(String(255), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Job metrics
    jobs_processed = Column(Integer, default=0)
    jobs_succeeded = Column(Integer, default=0)
    jobs_failed = Column(Integer, default=0)
    jobs_retried = Column(Integer, default=0)
    
    # Error metrics
    total_errors = Column(Integer, default=0)
    error_by_category = Column(JSON, nullable=True)
    
    # Proxy metrics
    proxy_errors = Column(Integer, default=0)
    tunnel_errors = Column(Integer, default=0)
    
    # Performance
    avg_job_duration_ms = Column(Integer, nullable=True)
    queue_depth = Column(Integer, nullable=True)
    
    # Resource usage
    cpu_percent = Column(Integer, nullable=True)
    memory_mb = Column(Integer, nullable=True)


class CircuitBreakerState(Base):
    """Circuit breaker state for proxy/exit node management."""
    __tablename__ = "circuit_breaker_state"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # What the circuit breaker is protecting
    resource_type = Column(String(50), nullable=False, index=True)  # "proxy", "exit_node", "site"
    resource_id = Column(String(255), nullable=False, index=True)
    
    # State
    state = Column(String(20), nullable=False, default="closed")  # closed, open, half_open
    failure_count = Column(Integer, default=0)
    last_failure_at = Column(DateTime(timezone=True), nullable=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    
    # Thresholds
    failure_threshold = Column(Integer, default=config.rabbitmq.circuit_breaker_threshold)
    reset_timeout = Column(Integer, default=config.rabbitmq.circuit_breaker_timeout)
    
    # Metadata
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index("idx_circuit_breaker_resource", "resource_type", "resource_id"),
    )


# Database engine and session management
_engine = None
_SessionLocal = None


def get_engine():
    """Get or create database engine."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            config.database.url,
            pool_size=config.database.pool_size,
            max_overflow=config.database.max_overflow,
            pool_pre_ping=True,
            echo=config.debug,
        )
    return _engine


def get_session_factory():
    """Get or create session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal


def init_db():
    """Initialize database tables."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get database session (dependency injection pattern)."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
