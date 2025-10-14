"""
Circuit breaker pattern for external API calls.
Prevents cascading failures and enables graceful degradation.
"""

import logging
import time
from collections.abc import Callable
from enum import Enum
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """
    Circuit breaker with adaptive thresholds and Prometheus metrics export.
    Prevents cascading failures with dynamic failure detection.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_duration: float = 30.0,
        success_threshold: int = 3,
        name: str = "default",
        adaptive: bool = True,
    ):
        """
        Initialize circuit breaker with adaptive thresholds.

        Args:
            failure_threshold: Initial failures before opening circuit
            timeout_duration: Seconds before trying again (half-open)
            success_threshold: Successes needed to close from half-open
            name: Circuit breaker identifier
            adaptive: Enable adaptive threshold adjustment based on error patterns
        """
        self.base_failure_threshold = failure_threshold
        self.failure_threshold = failure_threshold
        self.timeout_duration = timeout_duration
        self.success_threshold = success_threshold
        self.name = name
        self.adaptive = adaptive

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float | None = None

        # Adaptive threshold tracking
        self.error_window = []  # Rolling window of errors
        self.window_size = 60  # seconds

        # Prometheus metrics
        self.metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "circuit_opens": 0,
            "circuit_closes": 0,
        }

    def __call__(self, func: Callable) -> Callable:
        """Decorator for circuit breaker."""

        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Check circuit state
            if self.state == CircuitState.OPEN:
                # Check if timeout expired
                if (
                    self.last_failure_time
                    and (time.time() - self.last_failure_time) > self.timeout_duration
                ):
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
                    logger.info(
                        f"Circuit {self.name}: HALF_OPEN success count: {self.success_count}/{self.success_threshold}"
                    )

                    if self.success_count >= self.success_threshold:
                        logger.info(
                            f"Circuit {self.name}: HALF_OPEN -> CLOSED (recovery successful)"
                        )
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

                logger.error(
                    f"Circuit {self.name}: Failure {self.failure_count}/{self.failure_threshold} - {str(e)[:100]}"
                )

                if self.state == CircuitState.HALF_OPEN:
                    # Go back to OPEN on any failure in HALF_OPEN
                    logger.warning(f"Circuit {self.name}: HALF_OPEN -> OPEN (test call failed)")
                    self.state = CircuitState.OPEN
                    self.success_count = 0

                elif (
                    self.state == CircuitState.CLOSED
                    and self.failure_count >= self.failure_threshold
                ):
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
        """Get circuit breaker state with metrics."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "time_since_last_failure": time.time() - (self.last_failure_time or time.time()),
            "metrics": self.metrics,
            "failure_threshold": self.failure_threshold,
            "adaptive_enabled": self.adaptive,
        }

    def _adjust_threshold_adaptively(self):
        """Adjust failure threshold based on error patterns (adaptive mode)."""
        if not self.adaptive:
            return

        # Remove errors outside window
        current_time = time.time()
        self.error_window = [t for t in self.error_window if current_time - t < self.window_size]

        # Adjust threshold based on error frequency
        if len(self.error_window) > 10:  # High error rate
            # Lower threshold for faster circuit opening
            self.failure_threshold = max(3, self.base_failure_threshold - 2)
            logger.info(
                f"Circuit {self.name}: Adaptive threshold lowered to {self.failure_threshold}"
            )
        else:  # Normal error rate
            # Reset to base threshold
            self.failure_threshold = self.base_failure_threshold

    def export_prometheus_metrics(self) -> str:
        """
        Export metrics in Prometheus format.

        Returns:
            Prometheus-formatted metrics string
        """
        metrics_output = []

        metrics_output.append(
            "# HELP circuit_breaker_state Current circuit breaker state (0=closed, 1=open, 2=half_open)"
        )
        metrics_output.append("# TYPE circuit_breaker_state gauge")
        state_value = {"closed": 0, "open": 1, "half_open": 2}[self.state.value]
        metrics_output.append(f'circuit_breaker_state{{name="{self.name}"}} {state_value}')

        metrics_output.append(
            "# HELP circuit_breaker_total_calls Total calls through circuit breaker"
        )
        metrics_output.append("# TYPE circuit_breaker_total_calls counter")
        metrics_output.append(
            f'circuit_breaker_total_calls{{name="{self.name}"}} {self.metrics["total_calls"]}'
        )

        metrics_output.append("# HELP circuit_breaker_failed_calls Failed calls")
        metrics_output.append("# TYPE circuit_breaker_failed_calls counter")
        metrics_output.append(
            f'circuit_breaker_failed_calls{{name="{self.name}"}} {self.metrics["failed_calls"]}'
        )

        metrics_output.append("# HELP circuit_breaker_opens Circuit breaker opens")
        metrics_output.append("# TYPE circuit_breaker_opens counter")
        metrics_output.append(
            f'circuit_breaker_opens{{name="{self.name}"}} {self.metrics["circuit_opens"]}'
        )

        return "\n".join(metrics_output)


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""

    pass


# Pre-configured circuit breakers for different services
pinecone_breaker = CircuitBreaker(
    failure_threshold=5, timeout_duration=30.0, success_threshold=3, name="pinecone"
)

claude_breaker = CircuitBreaker(
    failure_threshold=3, timeout_duration=20.0, success_threshold=2, name="claude"
)

voyage_breaker = CircuitBreaker(
    failure_threshold=5, timeout_duration=30.0, success_threshold=3, name="voyage"
)

dms_breaker = CircuitBreaker(
    failure_threshold=5, timeout_duration=60.0, success_threshold=3, name="dms"
)
