// src/models/error_log.py
"""Error log model for aggregated error tracking and analysis."""
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List

from sqlalchemy import Column, String, DateTime, Text, JSON, Integer, Enum as SQLEnum, Index, Boolean
from sqlalchemy.orm import relationship

from .base import Base


class ErrorCategory(str, Enum):
    """Error category classification."""
    TRANSIENT = "transient"  # Can be retried
    TERMINAL = "terminal"  # Will not succeed with retries
    UNKNOWN = "unknown"  # Requires LLM analysis


class ErrorLog(Base):
    """Aggregated error log for analysis and recovery."""
    
    __tablename__ = "error_logs"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Error identification
    error_code = Column(String(50), nullable=False, index=True)
    error_message = Column(Text, nullable=True)
    category = Column(
        SQLEnum(ErrorCategory),
        default=ErrorCategory.UNKNOWN,
        nullable=False,
        index=True
    )
    
    # Classification details
    classification_confidence = Column(String(20), nullable=True)  # high, medium, low
    classification_reason = Column(Text, nullable=True)
    
    # Occurrence tracking
    occurrence_count = Column(Integer, default=1)
    first_occurrence = Column(DateTime, default=datetime.utcnow)
    last_occurrence = Column(DateTime, default=datetime.utcnow)
    unique_jobs_affected = Column(Integer, default=0)
    unique_proxies_affected = Column(Integer, default=0)
    
    # Resolution tracking
    auto_retry_enabled = Column(Boolean, default=True)
    recovery_attempts = Column(Integer, default=0)
    recovery_successes = Column(Integer, default=0)
    last_recovery_attempt = Column(DateTime, nullable=True)
    
    # Context
    affected_urls = Column(JSON, default=list)
    affected_proxy_exits = Column(JSON, default=list)
    
    # Metadata
    metadata = Column(JSON, default=dict)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_error_logs_category_code", "category", "error_code"),
        Index("ix_error_logs_last_occurrence", "last_occurrence"),
        Index("ix_error_logs_auto_retry", "auto_retry_enabled", "category"),
    )
    
    def __repr__(self) -> str:
        return f"<ErrorLog(code={self.error_code}, category={self.category}, count={self.occurrence_count})>"
    
    @property
    def recovery_rate(self) -> float:
        """Calculate recovery success rate."""
        if self.recovery_attempts == 0:
            return 0.0
        return round(self.recovery_successes / self.recovery_attempts * 100, 2)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "error_log_id": self.id,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "category": self.category.value,
            "classification_confidence": self.classification_confidence,
            "classification_reason": self.classification_reason,
            "occurrence_count": self.occurrence_count,
            "first_occurrence": self.first_occurrence.isoformat() if self.first_occurrence else None,
            "last_occurrence": self.last_occurrence.isoformat() if self.last_occurrence else None,
            "unique_jobs_affected": self.unique_jobs_affected,
            "unique_proxies_affected": self.unique_proxies_affected,
            "auto_retry_enabled": self.auto_retry_enabled,
            "recovery_attempts": self.recovery_attempts,
            "recovery_successes": self.recovery_successes,
            "recovery_rate": self.recovery_rate,
            "last_recovery_attempt": self.last_recovery_attempt.isoformat() if self.last_recovery_attempt else None,
            "affected_urls": self.affected_urls[:10] if self.affected_urls else [],  # Limit for API response
            "affected_proxy_exits": self.affected_proxy_exits[:10] if self.affected_proxy_exits else [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def record_occurrence(
        self,
        job_id: Optional[str] = None,
        url: Optional[str] = None,
        proxy_exit: Optional[str] = None
    ):
        """Record an error occurrence."""
        self.occurrence_count += 1
        self.last_occurrence = datetime.utcnow()
        
        if url and url not in (self.affected_urls or []):
            self.affected_urls = (self.affected_urls or []) + [url]
        
        if proxy_exit and proxy_exit not in (self.affected_proxy_exits or []):
            self.affected_proxy_exits = (self.affected_proxy_exits or []) + [proxy_exit]
    
    def record_recovery_attempt(self, success: bool):
        """Record a recovery attempt."""
        self.recovery_attempts += 1
        self.last_recovery_attempt = datetime.utcnow()
        if success:
            self.recovery_successes += 1
    
    def classify(
        self,
        category: ErrorCategory,
        confidence: str = "medium",
        reason: str = None
    ):
        """Update error classification."""
        self.category = category
        self.classification_confidence = confidence
        self.classification_reason = reason
        
        # Auto-retry only for transient errors
        self.auto_retry_enabled = (category == ErrorCategory.TRANSIENT)
