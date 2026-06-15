// src/models/result.py
"""Result model for storing scraped data."""
import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import Column, String, Text, DateTime, JSON, ForeignKey, Integer, Boolean, Index
from sqlalchemy.orm import relationship

from .base import Base


class Result(Base):
    """Result model for storing scraped data and LLM-enriched content."""
    
    __tablename__ = "results"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    
    # Original scraped data
    raw_html = Column(Text, nullable=True)
    raw_data = Column(JSON, default=dict)
    http_status = Column(Integer, nullable=True)
    scrape_duration_ms = Column(Integer, nullable=True)
    
    # LLM enriched data
    enriched_data = Column(JSON, default=dict)
    extraction_confidence = Column Float, default=0.0
    llm_processed = Column(Boolean, default=False)
    llm_error = Column(Text, nullable=True)
    
    # Extraction metadata
    extracted_fields = Column(JSON, default=dict)
    validation_errors = Column(JSON, default=list)
    is_valid = Column(Boolean, default=True)
    
    # URLs found in page
    links_found = Column(JSON, default=list)
    images_found = Column(JSON, default=list)
    
    # Quality metrics
    content_hash = Column(String(64), nullable=True)  # SHA256 of raw content
    page_size_bytes = Column(Integer, nullable=True)
    load_time_ms = Column(Integer, nullable=True)
    
    # Timestamps
    scraped_at = Column(DateTime, default=datetime.utcnow)
    enriched_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    job = relationship("Job", back_populates="result", foreign_keys=[job_id])
    
    __table_args__ = (
        Index("ix_results_scraped_at", "scraped_at"),
        Index("ix_results_llm_processed", "llm_processed", "is_valid"),
    )
    
    def __repr__(self) -> str:
        return f"<Result(id={self.id}, job_id={self.job_id}, valid={self.is_valid})>"
    
    def to_dict(self, include_raw: bool = False) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        result = {
            "result_id": self.id,
            "job_id": self.job_id,
            "http_status": self.http_status,
            "scrape_duration_ms": self.scrape_duration_ms,
            "enriched_data": self.enriched_data,
            "extraction_confidence": self.extraction_confidence,
            "llm_processed": self.llm_processed,
            "llm_error": self.llm_error,
            "extracted_fields": self.extracted_fields,
            "validation_errors": self.validation_errors,
            "is_valid": self.is_valid,
            "links_count": len(self.links_found) if self.links_found else 0,
            "images_count": len(self.images_found) if self.images_found else 0,
            "content_hash": self.content_hash,
            "page_size_bytes": self.page_size_bytes,
            "load_time_ms": self.load_time_ms,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
            "enriched_at": self.enriched_at.isoformat() if self.enriched_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        
        if include_raw:
            result["raw_html"] = self.raw_html
            result["raw_data"] = self.raw_data
            result["links_found"] = self.links_found
            result["images_found"] = self.images_found
        
        return result
    
    def mark_llm_processed(
        self,
        enriched_data: Dict[str, Any],
        extraction_confidence: float = 0.0
    ):
        """Mark result as LLM processed with enriched data."""
        self.enriched_data = enriched_data
        self.extraction_confidence = extraction_confidence
        self.llm_processed = True
        self.enriched_at = datetime.utcnow()
    
    def mark_llm_error(self, error: str):
        """Mark LLM processing error."""
        self.llm_error = error
    
    def add_validation_error(self, field: str, issue: str):
        """Add a validation error."""
        if not self.validation_errors:
            self.validation_errors = []
        self.validation_errors.append({"field": field, "issue": issue})
        self.is_valid = False


# Need to add Float import
from sqlalchemy import Float
