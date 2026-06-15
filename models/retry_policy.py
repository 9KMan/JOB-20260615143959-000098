// models/retry_policy.py
"""RetryPolicy model for configurable retry behavior.

Defines retry strategies for different error types with
exponential backoff support.
"""
from datetime import datetime
from typing import List, Optional
import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship, Mapped, mapped_column

from models import Base


class RetryPolicy(Base):
    """Defines retry behavior for specific error codes.
    
    Policies use exponential backoff with configurable base delay,
    max delay, and multiplier.
    
    Attributes:
        id: UUID primary key.
        name: Human-readable policy name.
        error_codes: List of applicable error codes.
        base_delay_seconds: Initial delay between retries.
        max_delay_seconds: Maximum delay cap.
        multiplier: Exponential backoff multiplier.
        max_attempts: Maximum retry attempts.
        is_active: Whether this policy is active.
        created_at: When policy was created.
    """
    __tablename__ = "retry_policies"
    __table_args__ = (
        Index("idx_retry_policies_active", "is_active"),
        {
            "comment": "Retry policies for different error types",
            "schema": "public",
        },
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Human-readable policy name",
    )
    
    error_codes: Mapped[List[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        comment="Applicable error codes for this policy",
    )
    
    base_delay_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Initial delay between retries in seconds",
    )
    
    max_delay_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Maximum delay cap in seconds",
    )
    
    multiplier: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=2.0,
    )
    
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
    )
    
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("NOW()"),
    )

    def __repr__(self) -> str:
        return f"<RetryPolicy(id={self.id}, name={self.name}, active={self.is_active})>"

    def calculate_delay(self, attempt: int) -> int:
        """Calculate delay for a given attempt number.
        
        Uses exponential backoff: delay = base * (multiplier ^ attempt)
        Capped at max_delay_seconds.
        
        Args:
            attempt: Current attempt number (1-based).
            
        Returns:
            Delay in seconds.
        """
        delay = self.base_delay_seconds * (self.multiplier ** (attempt - 1))
        return min(int(delay), self.max_delay_seconds)

    def can_retry(self, attempt: int) -> bool:
        """Check if retry is allowed for given attempt.
        
        Args:
            attempt: Current attempt number.
            
        Returns:
            True if retry is allowed.
        """
        return self.is_active and attempt < self.max_attempts

    def applies_to(self, error_code: str) -> bool:
        """Check if this policy applies to an error code.
        
        Args:
            error_code: Error code to check.
            
        Returns:
            True if this policy handles the error code.
        """
        return error_code in self.error_codes
