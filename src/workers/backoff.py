# src/workers/backoff.py
"""Exponential backoff strategies for retry logic."""

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, TypeVar, Generic

from src.utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class BackoffStrategy(Enum):
    """Available backoff strategies."""
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    CONSTANT = "constant"
    FIBONACCI = "fibonacci"
    DECORRELATED = "decorrelated"


@dataclass
class BackoffConfig:
    """Configuration for backoff behavior."""
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 300.0  # 5 minutes
    multiplier: float = 2.0
    jitter: float = 0.1  # 10% jitter
    max_attempts: int = 5
    strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL


class BackoffCalculator:
    """Calculate delays for exponential backoff with various strategies."""
    
    def __init__(self, config: Optional[BackoffConfig] = None):
        """Initialize backoff calculator.
        
        Args:
            config: Backoff configuration
        """
        self.config = config or BackoffConfig()
    
    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number.
        
        Args:
            attempt: Attempt number (0-indexed)
            
        Returns:
            Delay in seconds
        """
        base_delay = self._calculate_base_delay(attempt)
        delay = min(base_delay, self.config.max_delay_seconds)
        
        # Apply jitter
        if self.config.jitter > 0:
            jitter_range = delay * self.config.jitter
            delay = delay + random.uniform(-jitter_range, jitter_range)
        
        return max(0.1, delay)  # Minimum 100ms
    
    def _calculate_base_delay(self, attempt: int) -> float:
        """Calculate base delay based on strategy."""
        if self.config.strategy == BackoffStrategy.EXPONENTIAL:
            return self.config.initial_delay_seconds * (
                self.config.multiplier ** attempt
            )
        
        elif self.config.strategy == BackoffStrategy.LINEAR:
            return self.config.initial_delay_seconds + (
                self.config.multiplier * attempt
            )
        
        elif self.config.strategy == BackoffStrategy.CONSTANT:
            return self.config.initial_delay_seconds
        
        elif self.config.strategy == BackoffStrategy.FIBONACCI:
            fib = self._fibonacci(attempt + 1)
            return self.config.initial_delay_seconds * fib
        
        elif self.config.strategy == BackoffStrategy.DECORRELATED:
            # Decorrelated jitter (AWS style)
            if attempt == 0:
                return self.config.initial_delay_seconds
            # Use previous delay with randomization
            prev_delay = self.config.initial_delay_seconds * (
                self.config.multiplier ** (attempt - 1)
            )
            return min(
                prev_delay * 3 * random.random(),
                self.config.max_delay_seconds
            )
        
        return self.config.initial_delay_seconds
    
    def _fibonacci(self, n: int) -> int:
        """Calculate nth Fibonacci number."""
        if n <= 1:
            return n
        a, b = 0, 1
        for _ in range(n - 1):
            a, b = b, a + b
        return b
    
    def get_schedule(self, max_attempts: Optional[int] = None) -> list:
        """Get full delay schedule for configured attempts.
        
        Args:
            max_attempts: Override max attempts
            
        Returns:
            List of delays in seconds
        """
        attempts = max_attempts or self.config.max_attempts
        return [self.calculate_delay(i) for i in range(attempts)]


class ExponentialBackoff:
    """Exponential backoff with retry logic for async operations.
    
    Usage:
        backoff = ExponentialBackoff(config=BackoffConfig(max_attempts=5))
        result = await backoff.execute(my_async_function, arg1, arg2)
    """
    
    def __init__(
        self,
        config: Optional[BackoffConfig] = None,
        on_retry: Optional[Callable[[int, Exception, float], None]] = None,
    ):
        """Initialize exponential backoff.
        
        Args:
            config: Backoff configuration
            on_retry: Optional callback on each retry (attempt, error, delay)
        """
        self.config = config or BackoffConfig()
        self.calculator = BackoffCalculator(self.config)
        self.on_retry = on_retry
        self._attempt = 0
        self._last_error: Optional[Exception] = None
    
    async def execute(
        self,
        func: Callable,
        *args,
        predicate: Optional[Callable[[Any], bool]] = None,
        **kwargs,
    ) -> Any:
        """Execute function with exponential backoff retry.
        
        Args:
            func: Function to execute (can be sync or async)
            *args: Positional arguments for func
            predicate: Optional function to determine if result is valid
            **kwargs: Keyword arguments for func
            
        Returns:
            Result of func
            
        Raises:
            Exception: After all retries exhausted
        """
        self._attempt = 0
        self._last_error = None
        
        while self._attempt < self.config.max_attempts:
            try:
                # Execute function
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                # Check predicate if provided
                if predicate and not predicate(result):
                    raise RetryableError("Result did not pass predicate check")
                
                # Success
                return result
                
            except Exception as e:
                self._last_error = e
                
                # Check if should retry
                if not self._should_retry(e):
                    raise
                
                # Check if more attempts available
                if self._attempt >= self.config.max_attempts - 1:
                    logger.warning(
                        f"Max retry attempts ({self.config.max_attempts}) exhausted"
                    )
                    raise
                
                # Calculate delay
                delay = self.calculator.calculate_delay(self._attempt)
                
                logger.debug(
                    f"Retry {self._attempt + 1}/{self.config.max_attempts} "
                    f"after {delay:.2f}s: {e}"
                )
                
                # Notify callback
                if self.on_retry:
                    self.on_retry(self._attempt + 1, e, delay)
                
                # Wait before retry
                await asyncio.sleep(delay)
                
                self._attempt += 1
        
        # Should not reach here, but just in case
        if self._last_error:
            raise self._last_error
        raise RuntimeError("Exponential backoff exhausted without error")
    
    def _should_retry(self, error: Exception) -> bool:
        """Determine if error is retryable.
        
        Args:
            error: The exception that occurred
            
        Returns:
            True if should retry
        """
        # Never retry these
        non_retryable = (
            ValueError,
            TypeError,
            SyntaxError,
        )
        
        if isinstance(error, non_retryable):
            return False
        
        # Check for terminal error messages
        terminal_messages = [
            "authentication failed",
            "invalid api key",
            "not found",
            "forbidden",
            "access denied",
        ]
        
        error_str = str(error).lower()
        for msg in terminal_messages:
            if msg in error_str:
                return False
        
        return True
    
    @property
    def attempt(self) -> int:
        """Get current attempt number."""
        return self._attempt
    
    @property
    def last_error(self) -> Optional[Exception]:
        """Get last error that occurred."""
        return self._last_error


class RetryableError(Exception):
    """Error indicating the operation should be retried."""
    pass


class RateLimiter:
    """Rate limiter using token bucket algorithm."""
    
    def __init__(
        self,
        rate: float,
        burst: Optional[float] = None,
    ):
        """Initialize rate limiter.
        
        Args:
            rate: Tokens per second
            burst: Maximum burst size (defaults to rate)
        """
        self.rate = rate
        self.burst = burst or rate
        self._tokens = self.burst
        self._last_update = time.time()
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: float = 1.0) -> float:
        """Acquire tokens, waiting if necessary.
        
        Args:
            tokens: Number of tokens to acquire
            
        Returns:
            Time waited in seconds
        """
        async with self._lock:
            # Add tokens based on elapsed time
            now = time.time()
            elapsed = now - self._last_update
            self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
            self._last_update = now
            
            if self._tokens >= tokens:
                self._tokens -= tokens
                return 0.0
            
            # Need to wait for tokens
            wait_time = (tokens - self._tokens) / self.rate
            
            # Update for when we return
            self._tokens = 0
            self._last_update = now + wait_time
            
            # Wait
            await asyncio.sleep(wait_time)
            
            return wait_time
    
    @property
    def available_tokens(self) -> float:
        """Get current available tokens."""
        now = time.time()
        elapsed = now - self._last_update
        return min(self.burst, self._tokens + elapsed * self.rate)
