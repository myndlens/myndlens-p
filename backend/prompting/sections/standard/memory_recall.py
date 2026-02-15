"""MEMORY_RECALL_SNIPPETS section — compact, token-optimized.

Formats Digital Self memory recall results for LLM prompts.
Uses abbreviated provenance and relevance percentage for minimal tokens.
"""
from prompting.types import PromptContext, SectionOutput, SectionID, CacheClass

_PROV_ABBREV = {
    "ONBOARDING": "ONBOARD",
    "ONBOARDING_AUTO": "AUTO",
    "EXPLICIT": "USER",
    "OBSERVED": "OBS",
    "INFERRED": "INF",
    "UNKNOWN": "UNK",
}


def generate(ctx: PromptContext) -> SectionOutput:
    snippets = ctx.memory_snippets
    if not snippets:
        return SectionOutput(
            section_id=SectionID.MEMORY_RECALL_SNIPPETS,
            content="No relevant memories.",
            priority=8,
            cache_class=CacheClass.VOLATILE,
            tokens_est=5,
            included=True,
        )

    parts = ["Memories:"]
    for i, s in enumerate(snippets, 1):
        text = s.get("text", "")
        prov = s.get("provenance", "UNKNOWN")
        dist = s.get("distance")

        prov_short = _PROV_ABBREV.get(prov, prov[:4].upper())
        relevance_pct = f"{(1.0 - float(dist)) * 100:.0f}%" if dist is not None else ""
        meta = f"[{prov_short}|{relevance_pct}]" if relevance_pct else f"[{prov_short}]"

        parts.append(f"{i}. {text} {meta}")

    parts.append("Use for ambiguity resolution and personalization.")
    content = "\n".join(parts)

    return SectionOutput(
        section_id=SectionID.MEMORY_RECALL_SNIPPETS,
        content=content,
        priority=8,
        cache_class=CacheClass.VOLATILE,
        tokens_est=len(content) // 4,
        included=True,
    )
