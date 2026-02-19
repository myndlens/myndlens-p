"""TTS Orchestrator — manages TTS provider selection."""
import logging
from typing import Optional

from config.feature_flags import is_mock_tts
from tts.provider.interface import TTSProvider, TTSResult
from tts.provider.mock import MockTTSProvider

logger = logging.getLogger(__name__)

_provider: Optional[TTSProvider] = None


def _get_provider() -> TTSProvider:
    if is_mock_tts():
        logger.info("[TTS:ORCHESTRATOR] Provider=MockTTSProvider (MOCK_TTS=true)")
        return MockTTSProvider()
    try:
        from tts.provider.elevenlabs import ElevenLabsTTSProvider
        logger.info("[TTS:ORCHESTRATOR] Provider=ElevenLabsTTSProvider (MOCK_TTS=false)")
        return ElevenLabsTTSProvider()
    except Exception as e:
        logger.error("[TTS:ORCHESTRATOR] ElevenLabs init failed → fallback to mock: %s", str(e))
        return MockTTSProvider()


def get_tts_provider() -> TTSProvider:
    global _provider
    if _provider is None:
        _provider = _get_provider()
    return _provider
