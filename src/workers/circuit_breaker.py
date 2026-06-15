# src/workers/circuit_breaker.py
"""Circuit breaker implementation for preventing cascade failures."""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, Optional, Any, List
import threading

from src.utils.logging import get_logger

logger = get_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovery is possible


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 3   # Successes in half-open before closing
    timeout_seconds: float = 60.0  # Time before trying half-open
    excluded_exceptions: tuple = ()  # Exceptions that don't count as failures
    name: str = "default"


class CircuitBreaker:
    """Circuit breaker pattern implementation.
    
    Prevents cascade failures by stopping requests to a failing service.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests are rejected immediately
    - HALF_OPEN: Testing if service has recovered
    
    Transitions:
    - CLOSED -> OPEN: After failure_threshold consecutive failures
    - OPEN -> HALF_OPEN: After timeout_seconds
    - HALF_OPEN -> CLOSED: After success_threshold successes
    - HALF_OPEN -> OPEN: On any failure
    """
    
    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        """Initialize circuit breaker.
        
        Args:
            config: Circuit breaker configuration
        """
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()
        
        # Track by key for per-site circuit breakers
        self._state_by_key: Dict[str, CircuitState] = {}
        self._failure_count_by_key: Dict[str, int] = {}
        self._success_count_by_key: Dict[str, int] = {}
        self._last_failure_by_key: Dict[str, float] = {}
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state
    
    def get_state_for_key(self, key: str) -> CircuitState:
        """Get circuit state for a specific key (e.g., site name)."""
        return self._state_by_key.get(key, CircuitState.CLOSED)
    
    async def call(
        self,
        func: Callable,
        *args: Any,
        key: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """Execute function with circuit breaker protection.
        
        Args:
            func: Function to execute
            key: Optional key for per-key circuit breaking
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result of func
            
        Raises:
            CircuitBreakerOpen: If circuit is open
            Exception: Any exception from func (after recording)
        """
        state_key = key or "default"
        
        # Check if circuit allows request
        if not await self._can_execute(state_key):
            raise CircuitBreakerOpen(
                f"Circuit breaker is {self._state_by_key.get(state_key, self._state).value} "
                f"for key '{state_key}'"
            )
        
        try:
            # Execute function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # Record success
            await self._on_success(state_key)
            
            return result
            
        except self.config.excluded_exceptions:
            # Excluded exceptions don't affect circuit
            raise
        except Exception as e:
            # Record failure
            await self._on_failure(state_key, e)
            raise
    
    async def _can_execute(self, key: str) -> bool:
        """Check if execution is allowed."""
        state = self._state_by_key.get(key, CircuitState.CLOSED)
        
        if state == CircuitState.CLOSED:
            return True
        
        if state == CircuitState.OPEN:
            # Check if timeout has elapsed
            last_failure = self._last_failure_by_key.get(key)
            if last_failure:
                elapsed = time.time() - last_failure
                if elapsed >= self.config.timeout_seconds:
                    # Transition to half-open
                    await self._transition_to_half_open(key)
                    return True
            
            return False
        
        # Half-open: allow one request through
        return True
    
    async def _on_success(self, key: str) -> None:
        """Handle successful execution."""
        async with self._lock:
            if key == "default":
                self._failure_count = 0
                self._success_count += 1
                
                if self._state == CircuitState.HALF_OPEN:
                    if self._success_count >= self.config.success_threshold:
                        await self._transition_to_closed(key)
            else:
                self._failure_count_by_key[key] = 0
                self._success_count_by_key[key] = (
                    self._success_count_by_key.get(key, 0) + 1
                )
                
                state = self._state_by_key.get(key, CircuitState.CLOSED)
                if state == CircuitState.HALF_OPEN:
                    if self._success_count_by_key.get(key, 0) >= self.config.success_threshold:
                        await self._transition_to_closed(key)
    
    async def _on_failure(self, key: str, exception: Exception) -> None:
        """Handle failed execution."""
        async with self._lock:
            self._last_failure_time = time.time()
            self._last_failure_by_key[key] = time.time()
            
            if key == "default":
                self._failure_count += 1
                self._success_count = 0
                
                if self._state == CircuitState.HALF_OPEN:
                    await self._transition_to_open(key)
                elif (
                    self._state == CircuitState.CLOSED
                    and self._failure_count >= self.config.failure_threshold
                ):
                    await self._transition_to_open(key)
            else:
                self._failure_count_by_key[key] = (
                    self._failure_count_by_key.get(key, 0) + 1
                )
                self._success_count_by_key[key] = 0
                
                state = self._state_by_key.get(key, CircuitState.CLOSED)
                if state == CircuitState.HALF_OPEN:
                    await self._transition_to_open(key)
                elif (
                    state == CircuitState.CLOSED
                    and self._failure_count_by_key.get(key, 0) >= self.config.failure_threshold
                ):
                    await self._transition_to_open(key)
    
    async def _transition_to_open(self, key: str) -> None:
        """Transition circuit to OPEN state."""
        if key == "default":
            old_state = self._state
            self._state = CircuitState.OPEN
            logger.warning(
                f"Circuit breaker OPENED for '{key}' "
                f"(was {old_state.value})"
            )
        else:
            old_state = self._state_by_key.get(key, CircuitState.CLOSED)
            self._state_by_key[key] = CircuitState.OPEN
            logger.warning(
                f"Circuit breaker OPENED for '{key}' "
                f"(failures={self._failure_count_by_key.get(key, 0)})"
            )
    
    async def _transition_to_half_open(self, key: str) -> None:
        """Transition circuit to HALF-OPEN state."""
        if key == "default":
            old_state = self._state
            self._state = CircuitState.HALF_OPEN
            self._success_count = 0
            logger.info(
                f"Circuit breaker HALF-OPEN for '{key}' "
                f"(was {old_state.value})"
            )
        else:
            old_state = self._state_by_key.get(key, CircuitState.CLOSED)
            self._state_by_key[key] = CircuitState.HALF_OPEN
            self._success_count_by_key[key] = 0
            logger.info(
                f"Circuit breaker HALF-OPEN for '{key}' "
                f"(timeout elapsed)"
            )
    
    async def _transition_to_closed(self, key: str) -> None:
        """Transition circuit to CLOSED state."""
        if key == "default":
            old_state = self._state
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            logger.info(
                f"Circuit breaker CLOSED for '{key}' "
                f"(was {old_state.value})"
            )
        else:
            old_state = self._state_by_key.get(key, CircuitState.CLOSED)
            self._state_by_key[key] = CircuitState.CLOSED
            self._failure_count_by_key[key] = 0
            self._success_count_by_key[key] = 0
            logger.info(
                f"Circuit breaker CLOSED for '{key}' "
                f"(successes={self.config.success_threshold})"
            )
    
    async def reset(self, key: Optional[str] = None) -> None:
        """Reset circuit breaker to closed state.
        
        Args:
            key: Optional key to reset. If None, resets default.
        """
        if key:
            self._state_by_key[key] = CircuitState.CLOSED
            self._failure_count_by_key[key] = 0
            self._success_count_by_key[key] = 0
            self._last_failure_by_key.pop(key, None)
            logger.info(f"Circuit breaker reset for key '{key}'")
        else:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
            logger.info("Circuit breaker reset")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "default": {
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "last_failure": self._last_failure_time,
            },
            "by_key": {
                key: {
                    "state": state.value,
                    "failure_count": self._failure_count_by_key.get(key, 0),
                    "success_count": self._success_count_by_key.get(key, 0),
                    "last_failure": self._last_failure_by_key.get(key),
                }
                for key, state in self._state_by_key.items()
            },
        }


class CircuitBreakerOpen(Exception):
    """Exception raised when circuit breaker is open."""
    pass


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers by site."""
    
    def __init__(self):
        """Initialize registry."""
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()
        self._configs: Dict[str, CircuitBreakerConfig] = {}
    
    def register_site(
        self,
        site_name: str,
        config: Optional[CircuitBreakerConfig] = None,
    ) -> CircuitBreaker:
        """Register a circuit breaker for a site.
        
        Args:
            site_name: Name of the site
            config: Optional circuit breaker config
            
        Returns:
            Circuit breaker instance
        """
        if site_name not in self._breakers:
            self._configs[site_name] = config or CircuitBreakerConfig(
                name=site_name
            )
            self._breakers[site_name] = CircuitBreaker(self._configs[site_name])
            logger.info(f"Registered circuit breaker for site: {site_name}")
        
        return self._breakers[site_name]
    
    def get_breaker(self, site_name: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker for a site."""
        return self._breakers.get(site_name)
    
    async def call_site(
        self,
        site_name: str,
        func: Callable,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute function with circuit breaker for site.
        
        Args:
            site_name: Site name for circuit breaker
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Result of func
            
        Raises:
            CircuitBreakerOpen: If circuit is open
        """
        breaker = self.register_site(site_name)
        return await breaker.call(func, *args, key=site_name, **kwargs)
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get stats for all circuit breakers."""
        return {
            site: breaker.get_stats()
            for site, breaker in self._breakers.items()
        }
