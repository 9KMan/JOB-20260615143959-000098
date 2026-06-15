// models/proxy_session.py
"""ProxySession model for managing proxy connections and state.

Tracks proxy health, tunnel errors, and cooldown periods for
intelligent proxy rotation in the worker fleet.
"""
from datetime import datetime
from typing import Optional, List
import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Enum as SQLEnum,
    Index,
    text,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column

from models import Base
from models.enums import ProxyStatus


class ProxySession(Base):
    """Manages proxy session state and health tracking.
    
    Proxy sessions track tunnel errors, cooldown periods, and
    connection health for intelligent rotation.
    
    Attributes:
        id: UUID primary key.
        proxy_host: Proxy server hostname or IP.
        proxy_port: Proxy server port.
        exit_ip: Resolved exit IP address.
        session_key: Sticky session token for session persistence.
        status: Current proxy status.
        tunnel_error_count: Number of tunnel errors encountered.
        last_tunnel_error_at: When last tunnel error occurred.
        last_error: Most recent error message.
        last_used_at: When proxy was last used.
        created_at: When session was created.
        cooldown_until: Backoff window before reuse.
    """
    __tablename__ = "proxy_sessions"
    __table_args__ = (
        Index("idx_proxy_status_cooldown", "status", "cooldown_until"),
        Index("idx_proxy_exit_ip", "exit_ip"),
        Index("idx_proxy_last_used", "last_used_at"),
        CheckConstraint("proxy_port > 0 AND proxy_port <= 65535", name="check_valid_port"),
        CheckConstraint("tunnel_error_count >= 0", name="check_tunnel_errors_nonnegative"),
        {
            "comment": "Proxy session state and health tracking",
            "schema": "public",
        },
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    
    proxy_host: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Proxy server hostname or IP",
    )
    
    proxy_port: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Proxy server port",
    )
    
    exit_ip: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        comment="Resolved exit IP (IPv4 or IPv6)",
    )
    
    session_key: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Sticky session token for persistence",
    )
    
    status: Mapped[ProxyStatus] = mapped_column(
        SQLEnum(ProxyStatus, name="proxy_status", create_type=False),
        nullable=False,
        default=ProxyStatus.ACTIVE,
        server_default=text("'active'"),
        index=True,
    )
    
    tunnel_error_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    
    last_tunnel_error_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    last_error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Most recent error message",
    )
    
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("NOW()"),
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("NOW()"),
    )
    
    cooldown_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Backoff window before reuse",
    )

    # Relationships
    results: Mapped[List["ScrapeResult"]] = relationship(
        "ScrapeResult",
        back_populates="proxy_session",
        lazy="dynamic",
    )
    
    failures: Mapped[List["ScrapeFailure"]] = relationship(
        "ScrapeFailure",
        back_populates="proxy_session",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        return f"<ProxySession(id={self.id}, host={self.proxy_host}:{self.proxy_port}, status={self.status.value})>"

    @property
    def is_available(self) -> bool:
        """Check if proxy is available for use."""
        if self.status != ProxyStatus.ACTIVE:
            return False
        if self.cooldown_until and datetime.utcnow() < self.cooldown_until:
            return False
        return True

    @property
    def is_healthy(self) -> bool:
        """Check if proxy is considered healthy."""
        return (
            self.status == ProxyStatus.ACTIVE
            and self.tunnel_error_count < 10
        )

    def record_usage(self) -> None:
        """Record that this proxy was used."""
        self.last_used_at = datetime.utcnow()

    def record_tunnel_error(self, error_message: Optional[str] = None) -> None:
        """Record a tunnel error and update state.
        
        Args:
            error_message: Optional error description.
        """
        self.tunnel_error_count += 1
        self.last_tunnel_error_at = datetime.utcnow()
        self.last_error = error_message
        
        # Auto-degrade after threshold
        if self.tunnel_error_count >= 10:
            self.status = ProxyStatus.ERROR
        
        # Exhaust after severe threshold
        if self.tunnel_error_count >= 20:
            self.status = ProxyStatus.EXHAUSTED

    def set_cooldown(self, duration_seconds: int) -> None:
        """Set cooldown period before proxy can be reused.
        
        Args:
            duration_seconds: Duration of cooldown in seconds.
        """
        from datetime import timedelta
        self.cooldown_until = datetime.utcnow() + timedelta(seconds=duration_seconds)

    def mark_healthy(self) -> None:
        """Mark proxy as healthy and active."""
        self.status = ProxyStatus.ACTIVE
        self.tunnel_error_count = 0
        self.last_error = None
        self.cooldown_until = None

    def mark_exhausted(self, reason: Optional[str] = None) -> None:
        """Mark proxy as exhausted.
        
        Args:
            reason: Optional reason for exhaustion.
        """
        self.status = ProxyStatus.EXHAUSTED
        self.last_error = reason

    def mark_retired(self) -> None:
        """Mark proxy as retired (permanently removed from rotation)."""
        self.status = ProxyStatus.RETIRED


# Import at bottom to avoid circular imports
from models.result import ScrapeResult
from models.failure import ScrapeFailure
