"""TTS Provider interface — provider-agnostic contract.

TTS provides ONLY: audio bytes from text.
TTS does NOT provide: intent, emotion analysis, or any reasoning.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TTSResult:
    """Result from TTS generation."""
    audio_bytes: bytes
    format: str  # "mp3" | "wav" | "pcm"
    text: str  # the input text
    latency_ms: float = 0.0
    voice_id: str = ""
    is_mock: bool = False


class TTSProvider(ABC):
    """Abstract TTS provider interface."""

    @abstractmethod
    async def synthesize(self, text: str, voice_id: Optional[str] = None) -> TTSResult:
        """Convert text to speech audio."""
        ...

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Health check."""
        ...
