"""MEMORY_RECALL_SNIPPETS section — volatile.

Formats Digital Self memory recall results for inclusion in LLM prompts.
Enables context-aware intent extraction using user history and preferences.
"""
from prompting.types import PromptContext, SectionOutput, SectionID, CacheClass


def generate(ctx: PromptContext) -> SectionOutput:
    snippets = ctx.memory_snippets
    if not snippets:
        return SectionOutput(
            section_id=SectionID.MEMORY_RECALL_SNIPPETS,
            content="No relevant memories found for this context.",
            priority=8,
            cache_class=CacheClass.VOLATILE,
            tokens_est=10,
            included=True,
        )

    parts = ["Relevant memories from user's Digital Self:"]
    for i, s in enumerate(snippets, 1):
        text = s.get("text", "")
        prov = s.get("provenance", "UNKNOWN")
        gtype = s.get("graph_type", "")
        dist = s.get("distance")
        neighbors = s.get("neighbors", 0)

        entry = f"  [{i}] {text}"
        meta = []
        if prov:
            meta.append(f"source={prov}")
        if gtype:
            meta.append(f"type={gtype}")
        if dist is not None:
            meta.append(f"relevance={1.0 - float(dist):.2f}")
        if neighbors > 0:
            meta.append(f"connections={neighbors}")
        if meta:
            entry += f"  ({', '.join(meta)})"
        parts.append(entry)

    parts.append(
        "\nUse these memories to resolve ambiguity, personalize responses, "
        "and avoid wrong-entity execution."
    )
    content = "\n".join(parts)

    return SectionOutput(
        section_id=SectionID.MEMORY_RECALL_SNIPPETS,
        content=content,
        priority=8,
        cache_class=CacheClass.VOLATILE,
        tokens_est=len(content) // 4,
        included=True,
    )
