// src/core/circuit_breaker.py
"""Circuit breaker implementation for fault tolerance."""
import asyncio
import time
from enum import IntEnum
from typing import Callable, Optional, Any, Dict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import Lock
import logging

from .metrics import get_metrics


logger = logging.getLogger(__name__)


class CircuitBreakerState(IntEnum):
    """Circuit breaker states."""
    CLOSED = 0
    OPEN = 1
    HALF_OPEN = 2


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""
    pass


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    failure_threshold: int = 5
    success_threshold: int = 3
    timeout: float = 30.0
    half_open_max_calls: int = 1
    excluded_exceptions: tuple = ()


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker monitoring."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state_changes: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "rejected_calls": self.rejected_calls,
            "state_changes": self.state_changes,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "last_success_time": self.last_success_time.isoformat() if self.last_success_time else None,
        }


class CircuitBreaker:
    """
    Circuit breaker implementation for protecting against cascading failures.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Circuit is tripped, requests are rejected
    - HALF_OPEN: Testing if service recovered
    
    State Transitions:
    - CLOSED -> OPEN: After failure_threshold consecutive failures
    - OPEN -> HALF_OPEN: After timeout seconds
    - HALF_OPEN -> CLOSED: After success_threshold consecutive successes
    - HALF_OPEN -> OPEN: On any failure
    """
    
    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        metrics_enabled: bool = True
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.metrics_enabled = metrics_enabled
        
        self._state = CircuitBreakerState.CLOSED
        self._stats = CircuitBreakerStats()
        self._lock = Lock()
        self._last_state_change_time = time.time()
        self._half_open_calls = 0
        
    @property
    def state(self) -> CircuitBreakerState:
        """Get current circuit breaker state."""
        with self._lock:
            # Check if we should transition from OPEN to HALF_OPEN
            if self._state == CircuitBreakerState.OPEN:
                elapsed = time.time() - self._last_state_change_time
                if elapsed >= self.config.timeout:
                    self._transition_to(CircuitBreakerState.HALF_OPEN)
            return self._state
    
    @property
    def stats(self) -> CircuitBreakerStats:
        """Get circuit breaker statistics."""
        with self._lock:
            return CircuitBreakerStats(
                total_calls=self._stats.total_calls,
                successful_calls=self._stats.successful_calls,
                failed_calls=self._stats.failed_calls,
                rejected_calls=self._stats.rejected_calls,
                state_changes=self._stats.state_changes,
                last_failure_time=self._stats.last_failure_time,
                last_success_time=self._stats.last_success_time,
                consecutive_failures=self._stats.consecutive_failures,
                consecutive_successes=self._stats.consecutive_successes,
            )
    
    def _transition_to(self, new_state: CircuitBreakerState):
        """Transition to a new state."""
        old_state = self._state
        self._state = new_state
        self._last_state_change_time = time.time()
        self._stats.state_changes += 1
        self._half_open_calls = 0
        
        logger.info(
            f"Circuit breaker '{self.name}' state change: {old_state.name} -> {new_state.name}"
        )
        
        if self.metrics_enabled:
            metrics = get_metrics()
            metrics.record_circuit_breaker_state(self.name, new_state.value)
    
    def _record_success(self):
        """Record a successful call."""
        self._stats.successful_calls += 1
        self._stats.consecutive_successes += 1
        self._stats.consecutive_failures = 0
        self._stats.last_success_time = datetime.utcnow()
        
        # Check if we should close from HALF_OPEN
        if (
            self._state == CircuitBreakerState.HALF_OPEN
            and self._stats.consecutive_successes >= self.config.success_threshold
        ):
            self._transition_to(CircuitBreakerState.CLOSED)
    
    def _record_failure(self):
        """Record a failed call."""
        self._stats.failed_calls += 1
        self._stats.consecutive_failures += 1
        self._stats.consecutive_successes = 0
        self._stats.last_failure_time = datetime.utcnow()
        
        # Check if we should open from CLOSED or HALF_OPEN
        if self._state == CircuitBreakerState.CLOSED:
            if self._stats.consecutive_failures >= self.config.failure_threshold:
                self._transition_to(CircuitBreakerState.OPEN)
        elif self._state == CircuitBreakerState.HALF_OPEN:
            self._transition_to(CircuitBreakerState.OPEN)
    
    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        with self._lock:
            current_state = self.state  # This may trigger state transition
            
            if current_state == CircuitBreakerState.CLOSED:
                return True
            
            if current_state == CircuitBreakerState.HALF_OPEN:
                if self._half_open_calls < self.config.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False
            
            # OPEN state
            self._stats.rejected_calls += 1
            return False
    
    async def call_async(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function with circuit breaker protection (async).
        
        Args:
            func: Async function to call
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            Result of the function call
            
        Raises:
            CircuitBreakerError: If circuit breaker is open
            Exception: Any exception from the wrapped function
        """
        if not self.allow_request():
            raise CircuitBreakerError(
                f"Circuit breaker '{self.name}' is OPEN"
            )
        
        self._stats.total_calls += 1
        
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = await asyncio.to_thread(func, *args, **kwargs)
            self._record_success()
            return result
        except self.config.excluded_exceptions:
            # Don't count excluded exceptions as failures
            raise
        except Exception:
            self._record_failure()
            raise
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function with circuit breaker protection (sync).
        
        Args:
            func: Function to call
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            Result of the function call
            
        Raises:
            CircuitBreakerError: If circuit breaker is open
            Exception: Any exception from the wrapped function
        """
        if not self.allow_request():
            raise CircuitBreakerError(
                f"Circuit breaker '{self.name}' is OPEN"
            )
        
        self._stats.total_calls += 1
        
        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except self.config.excluded_exceptions:
            raise
        except Exception:
            self._record_failure()
            raise
    
    def reset(self):
        """Manually reset the circuit breaker to CLOSED state."""
        with self._lock:
            self._transition_to(CircuitBreakerState.CLOSED)
            self._stats = CircuitBreakerStats()


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers."""
    
    _instance: Optional["CircuitBreakerRegistry"] = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._breakers = {}
                    cls._instance._registry_lock = Lock()
        return cls._instance
    
    def get_or_create(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None
    ) -> CircuitBreaker:
        """Get an existing circuit breaker or create a new one."""
        with self._registry_lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name, config)
            return self._breakers[name]
    
    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get a circuit breaker by name."""
        with self._registry_lock:
            return self._breakers.get(name)
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all circuit breakers."""
        with self._registry_lock:
            return {
                name: {
                    "state": breaker.state.name,
                    "stats": breaker.stats.to_dict()
                }
                for name, breaker in self._breakers.items()
            }
    
    def reset_all(self):
        """Reset all circuit breakers."""
        with self._registry_lock:
            for breaker in self._breakers.values():
                breaker.reset()
    
    def reset(self, name: str) -> bool:
        """Reset a specific circuit breaker."""
        with self._registry_lock:
            if name in self._breakers:
                self._breakers[name].reset()
                return True
            return False


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Get the global circuit breaker registry."""
    return CircuitBreakerRegistry()
