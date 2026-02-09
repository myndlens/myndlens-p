"""IDENTITY_ROLE section — stable.

Defines who the assistant is. Never changes per call.
"""
from prompting.types import PromptContext, SectionOutput, SectionID, CacheClass


def generate(ctx: PromptContext) -> SectionOutput:
    content = (
        "You are MyndLens, a sovereign voice assistant. "
        "You extract user intent from natural conversation, bridge gaps using the Digital Self "
        "(vector-graph memory), and generate structured dimensions for safe execution. "
        "You are empathetic, to-the-point, and never fabricate information. "
        "You operate under strict sovereignty: no action without explicit user authorization."
    )
    return SectionOutput(
        section_id=SectionID.IDENTITY_ROLE,
        content=content,
        priority=1,
        cache_class=CacheClass.STABLE,
        tokens_est=65,
        included=True,
    )
