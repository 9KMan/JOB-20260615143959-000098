// models/result.py
"""ScrapeResult model for storing successful scrape data.

Stores extracted data, LLM-processed results, and performance metrics
for completed scrape tasks.
"""
from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import (
    Column,
    Integer,
    Boolean,
    String,
    Text,
    DateTime,
    Index,
    ForeignKey,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column

from models import Base


class ScrapeResult(Base):
    """Stores successful scrape results and LLM-processed data.
    
    Raw HTML is truncated for storage efficiency; full content
    should be stored in object storage if needed.
    
    Attributes:
        id: UUID primary key.
        task_id: Foreign key to the scrape task.
        status_code: HTTP status code from the scrape.
        content_hash: SHA-256 hash of content for deduplication.
        raw_html: Truncated raw HTML content.
        extracted_data: JSONB with structured extraction results.
        llm_processed: Whether LLM post-processing was applied.
        llm_result: LLM extraction/processing results.
        llm_error: Error message if LLM processing failed.
        scrape_duration_ms: Time taken to complete the scrape.
        proxy_session_id: Proxy session used for this scrape.
        created_at: When result was created.
    """
    __tablename__ = "scrape_results"
    __table_args__ = (
        Index("idx_results_task_id", "task_id", unique=True),
        Index("idx_results_created_at", "created_at"),
        Index("idx_results_content_hash", "content_hash"),
        {
            "comment": "Successful scrape results with LLM processing support",
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
        unique=True,
    )
    
    status_code: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="HTTP status code from scrape",
    )
    
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 hash for deduplication",
    )
    
    raw_html: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Truncated raw HTML (store full in object storage)",
    )
    
    extracted_data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
        comment="Structured extraction results",
    )
    
    llm_processed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    
    llm_result: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="LLM extraction/processing results",
    )
    
    llm_error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if LLM processing failed",
    )
    
    scrape_duration_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Time taken to complete scrape in milliseconds",
    )
    
    proxy_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("proxy_sessions.id", ondelete="SET NULL"),
        nullable=True,
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
        back_populates="result",
        foreign_keys=[task_id],
    )
    
    proxy_session: Mapped[Optional["ProxySession"]] = relationship(
        "ProxySession",
        back_populates="results",
    )

    def __repr__(self) -> str:
        return f"<ScrapeResult(id={self.id}, task_id={self.task_id}, status={self.status_code})>"

    @property
    def is_success(self) -> bool:
        """Check if this was a successful scrape."""
        return 200 <= self.status_code < 300

    def mark_llm_processed(self, result: dict) -> None:
        """Mark result as processed by LLM with results.
        
        Args:
            result: LLM processing results.
        """
        self.llm_processed = True
        self.llm_result = result

    def mark_llm_failed(self, error: str) -> None:
        """Mark LLM processing as failed.
        
        Args:
            error: Error message from LLM processing.
        """
        self.llm_error = error


# Import at bottom to avoid circular imports
from models.scrape_task import ScrapeTask
from models.proxy_session import ProxySession
