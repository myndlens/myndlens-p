"""IDENTITY_ROLE section — now powered by Soul Store.

Retrieves identity from vector memory (soul fragments).
Falls back to hardcoded base if soul store unavailable.
"""
from prompting.types import PromptContext, SectionOutput, SectionID, CacheClass
from soul.store import retrieve_soul


def generate(ctx: PromptContext) -> SectionOutput:
    # Retrieve soul fragments from vector memory
    fragments = retrieve_soul(context_query=ctx.transcript)

    if fragments:
        # Assemble from soul fragments (priority-ordered)
        content = " ".join(f["text"] for f in fragments if f.get("text"))
    else:
        # Fallback: hardcoded base (should never happen after init)
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
        tokens_est=len(content) // 4,
        included=True,
    )
