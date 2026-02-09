"""Mock TTS Provider — returns empty audio for testing."""
import logging
from typing import Optional

from tts.provider.interface import TTSProvider, TTSResult

logger = logging.getLogger(__name__)


class MockTTSProvider(TTSProvider):
    """Mock TTS — returns text-only result (no audio bytes)."""

    async def synthesize(self, text: str, voice_id: Optional[str] = None) -> TTSResult:
        logger.debug("[MockTTS] Synthesize: '%s'", text[:50])
        return TTSResult(
            audio_bytes=b"",
            format="text",
            text=text,
            latency_ms=0,
            is_mock=True,
        )

    async def is_healthy(self) -> bool:
        return True
