"""Mock TTS Provider — returns empty audio for testing."""
import logging
from typing import Optional

from tts.provider.interface import TTSProvider, TTSResult

logger = logging.getLogger(__name__)


class MockTTSProvider(TTSProvider):
    """Mock TTS — returns text-only result (no audio bytes)."""

    async def synthesize(self, text: str, voice_id: Optional[str] = None) -> TTSResult:
        logger.info("[TTS:MOCK] synthesize text='%s' len=%d", text[:60], len(text))
        result = TTSResult(
            audio_bytes=b"",
            format="text",
            text=text,
            latency_ms=0,
            is_mock=True,
        )
        logger.info("[TTS:MOCK] DONE is_mock=True format=text audio_bytes=0")
        return result

    async def is_healthy(self) -> bool:
        return True
