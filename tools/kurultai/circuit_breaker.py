"""
Circuit Breaker for Complexity Scoring Operations.

Prevents cascading failures by tracking consecutive errors and
cumulative daily cost. When the failure threshold is exceeded or
the daily cost budget is blown, the breaker opens and rejects
new requests until a recovery timeout elapses.

State machine:
    CLOSED  --[failure_threshold exceeded]--> OPEN
    OPEN    --[recovery_timeout elapsed]----> HALF_OPEN
    HALF_OPEN --[success]-------------------> CLOSED
    HALF_OPEN --[failure]-------------------> OPEN

Usage:
    from tools.kurultai.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker()
    if cb.can_execute():
        try:
            result = do_work()
            cb.record_success(cost=result.cost)
        except Exception:
            cb.record_failure()
"""

import logging
import threading
import time
from enum import Enum

from tools.kurultai.complexity_config import DEFAULT_CONFIG

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Possible states of the circuit breaker."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Thread-safe circuit breaker with cost tracking.

    Args:
        failure_threshold: Consecutive failures before opening the circuit.
        recovery_timeout_seconds: Seconds to wait before transitioning
            from OPEN to HALF_OPEN.
        daily_cost_limit: Maximum cumulative cost per day. Uses the
            ``daily_system_limit`` from ``DEFAULT_CONFIG`` when *None*.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 60.0,
        daily_cost_limit: float | None = None,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.daily_cost_limit = (
            daily_cost_limit
            if daily_cost_limit is not None
            else DEFAULT_CONFIG.daily_system_limit
        )

        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._last_failure_time: float = 0.0
        self._daily_cost: float = 0.0
        self._cost_reset_day: int = self._current_day()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        """Current circuit breaker state (may trigger transition)."""
        with self._lock:
            self._maybe_transition()
            return self._state

    def can_execute(self) -> bool:
        """Return True if a new request should be allowed through.

        In CLOSED state, requests are always allowed (unless cost is
        exceeded). In HALF_OPEN state, a single probe request is
        allowed. In OPEN state, requests are rejected until the
        recovery timeout has elapsed.
        """
        with self._lock:
            self._maybe_reset_daily_cost()
            self._maybe_transition()

            if self._daily_cost >= self.daily_cost_limit:
                logger.warning(
                    "Circuit breaker: daily cost limit reached "
                    f"({self._daily_cost:.2f} >= {self.daily_cost_limit:.2f})"
                )
                return False

            if self._state == CircuitState.CLOSED:
                return True
            elif self._state == CircuitState.HALF_OPEN:
                return True  # Allow a single probe
            else:
                # OPEN
                return False

    def record_success(self, cost: float = 0.0) -> None:
        """Record a successful operation, optionally adding cost."""
        with self._lock:
            self._consecutive_failures = 0
            self._daily_cost += cost
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                logger.info("Circuit breaker: HALF_OPEN -> CLOSED (success)")

    def record_failure(self) -> None:
        """Record a failed operation."""
        with self._lock:
            self._consecutive_failures += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("Circuit breaker: HALF_OPEN -> OPEN (failure)")
            elif (
                self._state == CircuitState.CLOSED
                and self._consecutive_failures >= self.failure_threshold
            ):
                self._state = CircuitState.OPEN
                logger.warning(
                    f"Circuit breaker: CLOSED -> OPEN "
                    f"({self._consecutive_failures} consecutive failures)"
                )

    def reset(self) -> None:
        """Manually reset the breaker to CLOSED with zero failures."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._daily_cost = 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _maybe_transition(self) -> None:
        """Transition OPEN -> HALF_OPEN if recovery timeout has elapsed.

        Must be called while holding ``_lock``.
        """
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout_seconds:
                self._state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker: OPEN -> HALF_OPEN (timeout elapsed)")

    def _maybe_reset_daily_cost(self) -> None:
        """Reset daily cost counter if the calendar day has changed.

        Must be called while holding ``_lock``.
        """
        today = self._current_day()
        if today != self._cost_reset_day:
            self._daily_cost = 0.0
            self._cost_reset_day = today

    @staticmethod
    def _current_day() -> int:
        """Return current day-of-year as an integer (for cost reset)."""
        return int(time.time() // 86400)
