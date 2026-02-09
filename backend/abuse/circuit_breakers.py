"""Circuit Breakers — B17.

Protects against:
  - Repeated ambiguity loops (user keeps getting clarify responses)
  - STT failures (provider down)
  - API abuse patterns (hammering endpoints)

States: CLOSED (normal) → OPEN (blocking) → HALF_OPEN (testing)
"""
import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class BreakerState(str, Enum):
    CLOSED = "CLOSED"       # Normal operation
    OPEN = "OPEN"           # Blocking all requests
    HALF_OPEN = "HALF_OPEN" # Testing recovery


class CircuitBreaker:
    """In-memory circuit breaker per service/pattern."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_s: int = 60,
        half_open_max: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self.half_open_max = half_open_max

        self.state = BreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_at: Optional[datetime] = None
        self.half_open_attempts = 0

    def record_success(self) -> None:
        """Record a successful operation."""
        if self.state == BreakerState.HALF_OPEN:
            # Recovery successful
            self.state = BreakerState.CLOSED
            self.failure_count = 0
            self.half_open_attempts = 0
            logger.info("[CircuitBreaker] %s: CLOSED (recovered)", self.name)
        elif self.state == BreakerState.CLOSED:
            self.failure_count = 0

    def record_failure(self) -> None:
        """Record a failed operation."""
        self.failure_count += 1
        self.last_failure_at = datetime.now(timezone.utc)

        if self.state == BreakerState.HALF_OPEN:
            self.state = BreakerState.OPEN
            logger.warning("[CircuitBreaker] %s: OPEN (half-open failed)", self.name)
        elif self.failure_count >= self.failure_threshold:
            self.state = BreakerState.OPEN
            logger.warning(
                "[CircuitBreaker] %s: OPEN (threshold=%d reached)",
                self.name, self.failure_threshold,
            )

    def is_allowed(self) -> tuple[bool, str]:
        """Check if operation is allowed."""
        if self.state == BreakerState.CLOSED:
            return True, "ok"

        if self.state == BreakerState.OPEN:
            # Check if recovery timeout has passed
            if self.last_failure_at:
                elapsed = (datetime.now(timezone.utc) - self.last_failure_at).total_seconds()
                if elapsed >= self.recovery_timeout_s:
                    self.state = BreakerState.HALF_OPEN
                    self.half_open_attempts = 0
                    logger.info("[CircuitBreaker] %s: HALF_OPEN (testing)", self.name)
                    return True, "half_open"
            return False, f"Circuit open: {self.name} (failures={self.failure_count})"

        if self.state == BreakerState.HALF_OPEN:
            if self.half_open_attempts < self.half_open_max:
                self.half_open_attempts += 1
                return True, "half_open"
            return False, f"Circuit half-open limit: {self.name}"

        return True, "ok"

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_s": self.recovery_timeout_s,
        }


# ---- Global breakers ----

_breakers: Dict[str, CircuitBreaker] = {
    "stt": CircuitBreaker("stt", failure_threshold=5, recovery_timeout_s=30),
    "tts": CircuitBreaker("tts", failure_threshold=5, recovery_timeout_s=30),
    "l1_scout": CircuitBreaker("l1_scout", failure_threshold=3, recovery_timeout_s=60),
    "l2_sentry": CircuitBreaker("l2_sentry", failure_threshold=3, recovery_timeout_s=60),
    "ambiguity_loop": CircuitBreaker("ambiguity_loop", failure_threshold=5, recovery_timeout_s=120),
    "dispatch": CircuitBreaker("dispatch", failure_threshold=3, recovery_timeout_s=60),
}


def get_breaker(name: str) -> CircuitBreaker:
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name)
    return _breakers[name]


def get_all_breaker_statuses() -> list:
    return [b.get_status() for b in _breakers.values()]
