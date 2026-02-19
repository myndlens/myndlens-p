"""Dimension Engine — A-set + B-set extraction.

A-set: what, who, when, where, how, constraints
B-set: urgency, emotional_load, ambiguity, reversibility, user_confidence

B-set values are moving averages with stability buffer.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ASet:
    """Action dimensions."""
    what: Optional[str] = None
    who: Optional[str] = None
    when: Optional[str] = None
    where: Optional[str] = None
    how: Optional[str] = None
    constraints: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    def completeness(self) -> float:
        """Fraction of non-null dimensions."""
        fields = [self.what, self.who, self.when, self.where, self.how, self.constraints]
        filled = sum(1 for f in fields if f is not None)
        return filled / len(fields)


@dataclass
class BSet:
    """Cognitive dimensions (moving averages)."""
    urgency: float = 0.0
    emotional_load: float = 0.0
    ambiguity: float = 0.0  # default low — only raised when evidence suggests it
    reversibility: float = 1.0  # default reversible
    user_confidence: float = 0.5

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class StabilityBuffer:
    """Moving average for B-set values."""

    def __init__(self, alpha: float = 0.3):
        self._alpha = alpha  # EMA smoothing factor

    def update(self, current: float, new_value: float) -> float:
        """Exponential moving average update."""
        return self._alpha * new_value + (1 - self._alpha) * current


@dataclass
class DimensionState:
    """Per-session dimension state."""
    a_set: ASet = field(default_factory=ASet)
    b_set: BSet = field(default_factory=BSet)
    turn_count: int = 0
    _buffer: StabilityBuffer = field(default_factory=StabilityBuffer)

    def update_from_suggestions(self, suggestions: Dict[str, Any]) -> None:
        """Update dimensions from L1 hypothesis suggestions."""
        self.turn_count += 1

        # Update A-set
        for key in ("what", "who", "when", "where", "how", "constraints"):
            if key in suggestions and suggestions[key]:
                setattr(self.a_set, key, suggestions[key])

        # Update B-set with moving averages
        if "urgency" in suggestions:
            self.b_set.urgency = self._buffer.update(
                self.b_set.urgency, float(suggestions["urgency"])
            )
        if "emotional_load" in suggestions:
            self.b_set.emotional_load = self._buffer.update(
                self.b_set.emotional_load, float(suggestions["emotional_load"])
            )
        if "ambiguity" in suggestions:
            self.b_set.ambiguity = self._buffer.update(
                self.b_set.ambiguity, float(suggestions["ambiguity"])
            )
        if "user_confidence" in suggestions:
            self.b_set.user_confidence = self._buffer.update(
                self.b_set.user_confidence, float(suggestions["user_confidence"])
            )

        logger.debug(
            "Dimensions updated: turn=%d a_completeness=%.0f%% ambiguity=%.2f",
            self.turn_count, self.a_set.completeness() * 100, self.b_set.ambiguity,
        )

    def is_stable(self) -> bool:
        """Check if B-set is stable enough for risky actions."""
        return (
            self.b_set.urgency < 0.7
            and self.b_set.emotional_load < 0.6
            and self.turn_count >= 2
        )

    def to_dict(self) -> dict:
        return {
            "a_set": self.a_set.to_dict(),
            "b_set": self.b_set.to_dict(),
            "turn_count": self.turn_count,
            "stable": self.is_stable(),
            "a_completeness": self.a_set.completeness(),
        }


# Per-session dimension states
_sessions: Dict[str, DimensionState] = {}


def get_dimension_state(session_id: str) -> DimensionState:
    if session_id not in _sessions:
        _sessions[session_id] = DimensionState()
    return _sessions[session_id]


def cleanup_dimensions(session_id: str) -> None:
    _sessions.pop(session_id, None)
