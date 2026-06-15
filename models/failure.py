// models/failure.py
"""ScrapeFailure model for tracking and classifying scrape failures.

Stores detailed failure information with error classification
to support retry decisions and analytics.
"""
from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    Text,
    DateTime,
    Enum as SQLEnum,
    Index,
    ForeignKey,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column

from models import Base
from models.enums import FailureCategory, classify_error, TRANSIENT_ERRORS


class ScrapeFailure(Base):
    """Records detailed failure information for scrape tasks.
    
    Failures are classified as transient (retryable), terminal (permanent),
    or unknown (requires manual review).
    
    Attributes:
        id: UUID primary key.
        task_id: Foreign key to the scrape task.
        error_code: Short error code (e.g., ERR_TUNNEL, CAPTCHA).
        error_category: Classification of the error.
        error_message: Human-readable error description.
        stack_trace: Full stack trace if available.
        attempt_number: Which attempt this failure occurred on.
        proxy_session_id: Proxy session used when failure occurred.
        is_retryable: Whether this error can be retried.
        retry_count_at_failure: Number of retries before this failure.
        created_at: When failure was recorded.
    """
    __tablename__ = "scrape_failures"
    __table_args__ = (
        Index("idx_failures_task_id", "task_id"),
        Index("idx_failures_error_code", "error_code"),
        Index("idx_failures_category", "error_category", "created_at"),
        Index("idx_failures_created_at", "created_at"),
        Index("idx_failures_retryable", "is_retryable"),
        {
            "comment": "Failure records with error classification for retry decisions",
            "schema": "public",
        },
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scrape_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    error_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Short error code (ERR_TUNNEL, CAPTCHA, etc.)",
    )
    
    error_category: Mapped[FailureCategory] = mapped_column(
        SQLEnum(FailureCategory, name="failure_category", create_type=False),
        nullable=False,
        default=FailureCategory.UNKNOWN,
        server_default=text("'unknown'"),
        comment="Classification: transient, terminal, unknown",
    )
    
    error_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Human-readable error description",
    )
    
    stack_trace: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Full stack trace if available",
    )
    
    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    
    proxy_session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("proxy_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    is_retryable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        comment="Whether this error can be retried",
    )
    
    retry_count_at_failure: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("NOW()"),
    )

    # Relationships
    task: Mapped["ScrapeTask"] = relationship(
        "ScrapeTask",
        back_populates="failure",
        foreign_keys=[task_id],
    )
    
    proxy_session: Mapped[Optional["ProxySession"]] = relationship(
        "ProxySession",
        back_populates="failures",
    )

    def __repr__(self) -> str:
        return f"<ScrapeFailure(id={self.id}, error_code={self.error_code}, category={self.error_category.value})>"

    @classmethod
    def create(
        cls,
        task_id: uuid.UUID,
        error_code: str,
        error_message: str,
        attempt_number: int,
        retry_count: int = 0,
        proxy_session_id: Optional[uuid.UUID] = None,
        stack_trace: Optional[str] = None,
    ) -> "ScrapeFailure":
        """Factory method to create a failure with auto-classification.
        
        Args:
            task_id: UUID of the task that failed.
            error_code: Short error code.
            error_message: Human-readable error message.
            attempt_number: Which attempt this was.
            retry_count: Number of retries already attempted.
            proxy_session_id: Optional proxy session used.
            stack_trace: Optional full stack trace.
            
        Returns:
            New ScrapeFailure instance with auto-classified category.
        """
        category = classify_error(error_code)
        is_retryable = category == FailureCategory.TRANSIENT
        
        return cls(
            task_id=task_id,
            error_code=error_code,
            error_category=category,
            error_message=error_message,
            stack_trace=stack_trace,
            attempt_number=attempt_number,
            proxy_session_id=proxy_session_id,
            is_retryable=is_retryable,
            retry_count_at_failure=retry_count,
        )

    def reclassify(self, category: FailureCategory) -> None:
        """Reclassify this failure (e.g., after manual review).
        
        Args:
            category: New category to assign.
        """
        self.error_category = category
        self.is_retryable = category == FailureCategory.TRANSIENT


# Import at bottom to avoid circular imports
from models.scrape_task import ScrapeTask
from models.proxy_session import ProxySession
