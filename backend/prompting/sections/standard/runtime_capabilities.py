"""RUNTIME_CAPABILITIES section — semi-stable."""
from prompting.types import PromptContext, SectionOutput, SectionID, CacheClass
from config.settings import get_settings


def generate(ctx: PromptContext) -> SectionOutput:
    settings = get_settings()
    content = (
        f"Runtime: env={settings.ENV}, "
        f"mock_stt={settings.MOCK_STT}, mock_tts={settings.MOCK_TTS}, mock_llm={settings.MOCK_LLM}. "
        f"Available tools: {', '.join(ctx.available_tools) if ctx.available_tools else 'none'}."
    )
    return SectionOutput(
        section_id=SectionID.RUNTIME_CAPABILITIES,
        content=content,
        priority=7,
        cache_class=CacheClass.SEMISTABLE,
        tokens_est=30,
        included=True,
    )
