"""
Circuit breaker pattern for external API calls.
Prevents cascading failures and enables graceful degradation.
"""

import time
import asyncio
from enum import Enum
from typing import Callable, Any, Optional
from functools import wraps
import logging

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """
    Circuit breaker for external API calls.
    Prevents cascading failures and enables fallback strategies.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_duration: float = 30.0,
        success_threshold: int = 3,
        name: str = "default"
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Failures before opening circuit
            timeout_duration: Seconds before trying again (half-open)
            success_threshold: Successes needed to close from half-open
            name: Circuit breaker identifier
        """
        self.failure_threshold = failure_threshold
        self.timeout_duration = timeout_duration
        self.success_threshold = success_threshold
        self.name = name
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
    
    def __call__(self, func: Callable) -> Callable:
        """Decorator for circuit breaker."""
        
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Check circuit state
            if self.state == CircuitState.OPEN:
                # Check if timeout expired
                if self.last_failure_time and (time.time() - self.last_failure_time) > self.timeout_duration:
                    logger.info(f"Circuit {self.name}: OPEN -> HALF_OPEN (timeout expired)")
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                else:
                    logger.warning(f"Circuit {self.name}: OPEN - rejecting call")
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker {self.name} is OPEN. "
                        f"Try again in {self.timeout_duration - (time.time() - (self.last_failure_time or 0)):.1f}s"
                    )
            
            try:
                # Attempt the call
                result = await func(*args, **kwargs)
                
                # Success handling
                if self.state == CircuitState.HALF_OPEN:
                    self.success_count += 1
                    logger.info(f"Circuit {self.name}: HALF_OPEN success count: {self.success_count}/{self.success_threshold}")
                    
                    if self.success_count >= self.success_threshold:
                        logger.info(f"Circuit {self.name}: HALF_OPEN -> CLOSED (recovery successful)")
                        self.state = CircuitState.CLOSED
                        self.failure_count = 0
                
                elif self.state == CircuitState.CLOSED:
                    # Reset failure count on success
                    self.failure_count = 0
                
                return result
            
            except Exception as e:
                # Failure handling
                self.failure_count += 1
                self.last_failure_time = time.time()
                
                logger.error(f"Circuit {self.name}: Failure {self.failure_count}/{self.failure_threshold} - {str(e)[:100]}")
                
                if self.state == CircuitState.HALF_OPEN:
                    # Go back to OPEN on any failure in HALF_OPEN
                    logger.warning(f"Circuit {self.name}: HALF_OPEN -> OPEN (test call failed)")
                    self.state = CircuitState.OPEN
                    self.success_count = 0
                
                elif self.state == CircuitState.CLOSED and self.failure_count >= self.failure_threshold:
                    # Open circuit on threshold
                    logger.error(f"Circuit {self.name}: CLOSED -> OPEN (failure threshold reached)")
                    self.state = CircuitState.OPEN
                
                raise
        
        return wrapper
    
    def reset(self):
        """Manually reset circuit breaker."""
        logger.info(f"Circuit {self.name}: Manual reset to CLOSED")
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
    
    def get_state(self) -> dict:
        """Get circuit breaker state."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "time_since_last_failure": time.time() - (self.last_failure_time or time.time())
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


# Pre-configured circuit breakers for different services
pinecone_breaker = CircuitBreaker(
    failure_threshold=5,
    timeout_duration=30.0,
    success_threshold=3,
    name="pinecone"
)

claude_breaker = CircuitBreaker(
    failure_threshold=3,
    timeout_duration=20.0,
    success_threshold=2,
    name="claude"
)

voyage_breaker = CircuitBreaker(
    failure_threshold=5,
    timeout_duration=30.0,
    success_threshold=3,
    name="voyage"
)

dms_breaker = CircuitBreaker(
    failure_threshold=5,
    timeout_duration=60.0,
    success_threshold=3,
    name="dms"
)

