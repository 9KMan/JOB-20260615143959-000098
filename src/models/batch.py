// src/models/batch.py
"""Batch model for grouping scrape jobs."""
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any

from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, Enum as SQLEnum, Index
from sqlalchemy.orm import relationship

from .base import Base


class BatchStatus(str, Enum):
    """Batch processing status."""
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Batch(Base):
    """Batch model for grouping related scrape jobs."""
    
    __tablename__ = "batches"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    priority = Column(String(20), default="normal")  # low, normal, high
    status = Column(
        SQLEnum(BatchStatus),
        default=BatchStatus.QUEUED,
        nullable=False
    )
    
    # Counts
    total_items = Column(Integer, default=0)
    pending_items = Column(Integer, default=0)
    in_progress_items = Column(Integer, default=0)
    completed_items = Column(Integer, default=0)
    failed_items = Column(Integer, default=0)
    
    # Optional callback
    callback_url = Column(Text, nullable=True)
    
    # Metadata
    metadata = Column(JSON, default=dict)
    client_id = Column(String(36), nullable=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    estimated_completion = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Soft delete
    deleted_at = Column(DateTime, nullable=True)
    
    # Relationships
    jobs = relationship("Job", back_populates="batch", lazy="dynamic")
    
    __table_args__ = (
        Index("ix_batches_status_created", "status", "created_at"),
        Index("ix_batches_client_status", "client_id", "status"),
    )
    
    def __repr__(self) -> str:
        return f"<Batch(id={self.id}, name={self.name}, status={self.status})>"
    
    @property
    def progress_percentage(self) -> float:
        """Calculate progress percentage."""
        if self.total_items == 0:
            return 0.0
        return round((self.completed_items + self.failed_items) / self.total_items * 100, 2)
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate for completed items."""
        completed = self.completed_items + self.failed_items
        if completed == 0:
            return 0.0
        return round(self.completed_items / completed * 100, 2)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "batch_id": self.id,
            "name": self.name,
            "priority": self.priority,
            "status": self.status.value,
            "progress": {
                "total": self.total_items,
                "pending": self.pending_items,
                "in_progress": self.in_progress_items,
                "completed": self.completed_items,
                "failed": self.failed_items,
                "percentage": self.progress_percentage,
                "success_rate": self.success_rate,
            },
            "callback_url": self.callback_url,
            "metadata": self.metadata,
            "client_id": self.client_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "estimated_completion": self.estimated_completion.isoformat() if self.estimated_completion else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
    
    def update_progress(self, session=None):
        """Update progress counts from jobs."""
        from sqlalchemy import func
        
        # Refresh from database if session provided
        if session:
            session.refresh(self)
        
        # Query job counts
        from .job import Job, JobStatus
        
        # Note: This would need a proper query, simplified here
        pass  # Will be implemented in service layer
    
    def cancel(self):
        """Cancel the batch."""
        self.status = BatchStatus.CANCELLED
        self.deleted_at = datetime.utcnow()
