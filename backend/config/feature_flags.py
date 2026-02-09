"""Feature flags — controls batch-gated functionality."""
from config.settings import get_settings


def is_mock_stt() -> bool:
    return get_settings().MOCK_STT


def is_mock_tts() -> bool:
    return get_settings().MOCK_TTS


def is_mock_llm() -> bool:
    return get_settings().MOCK_LLM
