"""Evidence Spans — B4.

Track which transcript fragments ground which intent claims.
"""
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EvidenceSpan:
    """A span of transcript text that grounds an intent dimension."""
    span_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    fragment_id: str = ""
    text: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    confidence: float = 0.0
    is_final: bool = False

    def to_dict(self) -> dict:
        return {
            "span_id": self.span_id,
            "fragment_id": self.fragment_id,
            "text": self.text,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "confidence": self.confidence,
            "is_final": self.is_final,
        }


def create_span(
    fragment_id: str,
    text: str,
    start_time: float,
    end_time: float,
    confidence: float,
    is_final: bool,
) -> EvidenceSpan:
    return EvidenceSpan(
        fragment_id=fragment_id,
        text=text,
        start_time=start_time,
        end_time=end_time,
        confidence=confidence,
        is_final=is_final,
    )
