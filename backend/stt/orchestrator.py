"""STT Orchestrator — manages audio stream lifecycle.

Routes audio chunks to the configured STT provider.
Enforces rate limits, chunk validation, and format rules.
"""
import base64
import logging
from typing import Optional

from config.feature_flags import is_mock_stt
from stt.provider.interface import STTProvider
from stt.provider.mock import MockSTTProvider

logger = logging.getLogger(__name__)

# Chunk constraints — raised to accommodate full-recording uploads (real expo-av audio files)
MAX_CHUNK_SIZE_BYTES = 512 * 1024  # 512KB — supports ~2min recording at 32kbps
MAX_CHUNKS_PER_SECOND = 10  # Rate limit


def _get_provider() -> STTProvider:
    """Get the configured STT provider."""
    if is_mock_stt():
        logger.info("[STT:ORCHESTRATOR] Provider=MockSTTProvider (MOCK_STT=true)")
        return MockSTTProvider(latency_ms=30.0)
    try:
        from stt.provider.deepgram import DeepgramSTTProvider
        logger.info("[STT:ORCHESTRATOR] Provider=DeepgramSTTProvider (MOCK_STT=false)")
        return DeepgramSTTProvider()
    except Exception as e:
        logger.error("[STT:ORCHESTRATOR] Deepgram init failed → fallback to mock: %s", str(e))
        return MockSTTProvider(latency_ms=30.0)


# Singleton provider
_provider: Optional[STTProvider] = None


def get_stt_provider() -> STTProvider:
    global _provider
    if _provider is None:
        _provider = _get_provider()
    return _provider


def validate_audio_chunk(data: bytes, seq: int) -> Optional[str]:
    """Validate an audio chunk. Returns error message or None if valid."""
    if not data:
        return "Empty audio chunk"
    if len(data) > MAX_CHUNK_SIZE_BYTES:
        return f"Chunk too large: {len(data)} bytes (max {MAX_CHUNK_SIZE_BYTES})"
    if seq < 0:
        return f"Invalid sequence number: {seq}"
    return None


def decode_audio_payload(payload: dict) -> tuple[bytes, int, Optional[str]]:
    """Decode audio chunk from WS payload.

    Returns (audio_bytes, sequence_number, error_or_none).
    """
    audio_b64 = payload.get("audio")
    seq = payload.get("seq", -1)

    logger.debug("[STT:DECODE] seq=%d b64_len=%s", seq, len(audio_b64) if audio_b64 else 0)

    if not audio_b64:
        logger.warning("[STT:DECODE] seq=%d MISSING audio field", seq)
        return b"", seq, "Missing audio data"

    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception:
        logger.warning("[STT:DECODE] seq=%d INVALID base64", seq)
        return b"", seq, "Invalid base64 audio data"

    error = validate_audio_chunk(audio_bytes, seq)
    if error:
        logger.warning("[STT:DECODE] seq=%d VALIDATION FAIL: %s", seq, error)
    else:
        logger.debug("[STT:DECODE] seq=%d OK bytes=%d", seq, len(audio_bytes))

    return audio_bytes, seq, error
