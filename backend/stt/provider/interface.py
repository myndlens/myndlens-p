"""STT Provider interface — provider-agnostic contract.

STT provides ONLY: transcript fragments + confidence + latency.
STT does NOT provide: intent inference, VAD, emotion inference.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class TranscriptFragment:
    """A piece of transcribed text from the STT provider."""
    text: str
    confidence: float  # 0.0 - 1.0
    is_final: bool  # True = final result, False = interim/partial
    latency_ms: float  # Provider processing latency
    start_time: float = 0.0  # relative to session start
    end_time: float = 0.0
    fragment_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class STTProvider(ABC):
    """Abstract STT provider interface."""

    @abstractmethod
    async def start_stream(self, session_id: str) -> None:
        """Initialize a new audio stream session."""
        ...

    @abstractmethod
    async def feed_audio(self, session_id: str, chunk: bytes, seq: int) -> Optional[TranscriptFragment]:
        """Feed an audio chunk. May return a transcript fragment."""
        ...

    @abstractmethod
    async def end_stream(self, session_id: str) -> Optional[TranscriptFragment]:
        """End the audio stream. May return a final fragment."""
        ...

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Health check for the provider."""
        ...
