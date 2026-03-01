"""ElevenLabs TTS Provider — real voice synthesis.

Batch 3.5: Replace mock TTS with ElevenLabs.
Uses the convert() API to generate MP3 audio from text.
"""
import asyncio
import logging
import time
from typing import Optional

from config.settings import get_settings
from tts.provider.interface import TTSProvider, TTSResult

logger = logging.getLogger(__name__)

# Default voice: configured for MyndLens
DEFAULT_VOICE_ID = "i4CzbCVWoqvD0P1QJCUL"


class ElevenLabsTTSProvider(TTSProvider):
    """Real ElevenLabs TTS provider."""

    def __init__(self):
        self._client = None
        self._init_client()

    def _init_client(self):
        try:
            from elevenlabs import ElevenLabs
            settings = get_settings()
            api_key = settings.ELEVENLABS_API_KEY
            if not api_key:
                logger.error("[ElevenLabsTTS] No API key configured")
                return
            self._client = ElevenLabs(api_key=api_key)
            logger.info("[ElevenLabsTTS] Client initialized")
        except Exception as e:
            logger.error("[ElevenLabsTTS] Failed to initialize: %s", str(e))

    async def synthesize(self, text: str, voice_id: Optional[str] = None) -> TTSResult:
        if not self._client:
            logger.error("[ElevenLabsTTS] Client not initialized")
            return TTSResult(audio_bytes=b"", format="mp3", text=text, is_mock=True)

        vid = voice_id or DEFAULT_VOICE_ID
        start = time.monotonic()

        try:
            # Wrap entire convert + byte collection in timeout
            async def _tts_convert():
                loop = asyncio.get_running_loop()
                audio_iter = await loop.run_in_executor(
                    None,
                    lambda: self._client.text_to_speech.convert(
                        voice_id=vid,
                        text=text,
                        model_id="eleven_turbo_v2_5",
                        output_format="mp3_22050_32",
                        voice_settings={
                            "stability": 0.75,
                            "similarity_boost": 0.85,
                            "style": 0.10,
                            "use_speaker_boost": True,
                        },
                    ),
                )
                return b"".join(audio_iter)

            audio_bytes = await asyncio.wait_for(
                _tts_convert(),
                timeout=15.0,  # 15s covers convert + stream collection
            )

            # Collect all chunks from the iterator
            latency_ms = (time.monotonic() - start) * 1000

            logger.info(
                "[ElevenLabsTTS] Synthesized: %d bytes, %.0fms, text='%s'",
                len(audio_bytes), latency_ms, text[:50],
            )

            return TTSResult(
                audio_bytes=audio_bytes,
                format="mp3",
                text=text,
                latency_ms=latency_ms,
                voice_id=vid,
                is_mock=False,
            )

        except Exception as e:
            latency_ms = (time.monotonic() - start) * 1000
            logger.error(
                "[ElevenLabsTTS] Synthesis failed: %s (%.0fms)", str(e), latency_ms,
            )
            return TTSResult(audio_bytes=b"", format="mp3", text=text, is_mock=True)

    async def is_healthy(self) -> bool:
        return self._client is not None
