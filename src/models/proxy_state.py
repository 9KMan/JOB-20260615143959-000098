// src/models/proxy_state.py
"""Proxy state model for tracking proxy health and circuit breaker state."""
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any

from sqlalchemy import Column, String, DateTime, Integer, Float, Boolean, JSON, Enum as SQLEnum, Index, Text
from sqlalchemy.orm import relationship

from .base import Base


class ProxyStatus(str, Enum):
    """Proxy health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    DISABLED = "disabled"


class ProxyState(Base):
    """Proxy state tracking for Oxylabs residential proxy management."""
    
    __tablename__ = "proxy_states"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Proxy identification
    proxy_host = Column(String(255), nullable=False, unique=True, index=True)
    proxy_port = Column(Integer, nullable=False)
    country = Column(String(10), nullable=True)
    city = Column(String(100), nullable=True)
    exit_ip = Column(String(45), nullable=True)  # IPv4 or IPv6
    
    # Session information
    session_id = Column(String(255), nullable=True, unique=True)
    session_started_at = Column(DateTime, nullable=True)
    session_requests = Column(Integer, default=0)
    
    # Health metrics
    status = Column(
        SQLEnum(ProxyStatus),
        default=ProxyStatus.HEALTHY,
        nullable=False
    )
    total_requests = Column(Integer, default=0)
    successful_requests = Column(Integer, default=0)
    failed_requests = Column(Integer, default=0)
    
    # Performance metrics
    avg_response_time_ms = Column(Float, default=0.0)
    min_response_time_ms = Column(Float, nullable=True)
    max_response_time_ms = Column(Float, nullable=True)
    last_response_time_ms = Column(Integer, nullable=True)
    
    # Error tracking
    tunnel_errors = Column(Integer, default=0)
    auth_errors = Column(Integer, default=0)
    timeout_errors = Column(Integer, default=0)
    ban_count = Column(Integer, default=0)
    
    # Circuit breaker state
    circuit_breaker_failures = Column(Integer, default=0)
    circuit_breaker_state = Column(String(20), default="closed")  # closed, open, half_open
    circuit_breaker_opened_at = Column(DateTime, nullable=True)
    circuit_breaker_resets = Column(Integer, default=0)
    
    # Timestamps
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)
    last_health_check_at = Column(DateTime, nullable=True)
    last_error_at = Column(DateTime, nullable=True)
    disabled_at = Column(DateTime, nullable=True)
    
    # Configuration
    is_enabled = Column(Boolean, default=True)
    max_requests_per_session = Column(Integer, default=100)
    priority = Column(Integer, default=5)  # Higher = preferred
    
    # Metadata
    metadata = Column(JSON, default=dict)
    
    __table_args__ = (
        Index("ix_proxy_states_status_priority", "status", "priority"),
        Index("ix_proxy_states_circuit_breaker", "circuit_breaker_state", "status"),
        Index("ix_proxy_states_last_used", "last_used_at"),
    )
    
    def __repr__(self) -> str:
        return f"<ProxyState(host={self.proxy_host}, status={self.status})>"
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_requests == 0:
            return 100.0
        return round(self.successful_requests / self.total_requests * 100, 2)
    
    @property
    def failure_rate(self) -> float:
        """Calculate failure rate."""
        return 100.0 - self.success_rate
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "proxy_id": self.id,
            "proxy_host": self.proxy_host,
            "proxy_port": self.proxy_port,
            "country": self.country,
            "city": self.city,
            "exit_ip": self.exit_ip,
            "session_id": self.session_id,
            "status": self.status.value,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "success_rate": self.success_rate,
            "failure_rate": self.failure_rate,
            "avg_response_time_ms": self.avg_response_time_ms,
            "circuit_breaker_state": self.circuit_breaker_state,
            "is_enabled": self.is_enabled,
            "priority": self.priority,
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "last_health_check_at": self.last_health_check_at.isoformat() if self.last_health_check_at else None,
        }
    
    def record_success(self, response_time_ms: int):
        """Record a successful request."""
        self.total_requests += 1
        self.successful_requests += 1
        self.last_used_at = datetime.utcnow()
        self.last_response_time_ms = response_time_ms
        
        # Update rolling average
        if self.avg_response_time_ms == 0:
            self.avg_response_time_ms = float(response_time_ms)
        else:
            self.avg_response_time_ms = (
                (self.avg_response_time_ms * (self.total_requests - 1) + response_time_ms)
                / self.total_requests
            )
        
        # Update min/max
        if self.min_response_time_ms is None or response_time_ms < self.min_response_time_ms:
            self.min_response_time_ms = float(response_time_ms)
        if self.max_response_time_ms is None or response_time_ms > self.max_response_time_ms:
            self.max_response_time_ms = float(response_time_ms)
        
        # Reset circuit breaker on success
        if self.circuit_breaker_state != "closed":
            self.circuit_breaker_failures = 0
            self.circuit_breaker_state = "closed"
    
    def record_failure(self, error_type: str = "generic"):
        """Record a failed request."""
        self.total_requests += 1
        self.failed_requests += 1
        self.last_used_at = datetime.utcnow()
        self.last_error_at = datetime.utcnow()
        
        # Track error types
        if "tunnel" in error_type.lower():
            self.tunnel_errors += 1
        elif "auth" in error_type.lower():
            self.auth_errors += 1
        elif "timeout" in error_type.lower():
            self.timeout_errors += 1
        
        # Circuit breaker logic
        self.circuit_breaker_failures += 1
        
        # Trip at 50% failure rate over 10 requests
        recent_requests = min(self.total_requests, 10)
        recent_failures = min(self.failed_requests, self.circuit_breaker_failures)
        
        if recent_requests >= 5 and recent_failures / recent_requests >= 0.5:
            self.circuit_breaker_state = "open"
            self.circuit_breaker_opened_at = datetime.utcnow()
    
    def record_ban(self):
        """Record a ban/ban attempt."""
        self.ban_count += 1
        self.status = ProxyStatus.UNHEALTHY
        self.is_enabled = False
        self.disabled_at = datetime.utcnow()
    
    def enable(self):
        """Enable this proxy."""
        self.is_enabled = True
        self.disabled_at = None
        self.status = ProxyStatus.HEALTHY
    
    def disable(self, reason: str = None):
        """Disable this proxy."""
        self.is_enabled = False
        self.disabled_at = datetime.utcnow()
        self.status = ProxyStatus.DISABLED
        if reason:
            self.metadata = self.metadata or {}
            self.metadata["disable_reason"] = reason
    
    def start_session(self, session_id: str):
        """Start a new proxy session."""
        self.session_id = session_id
        self.session_started_at = datetime.utcnow()
        self.session_requests = 0
    
    def end_session(self):
        """End current proxy session."""
        self.session_id = None
        self.session_started_at = None
        self.session_requests = 0
