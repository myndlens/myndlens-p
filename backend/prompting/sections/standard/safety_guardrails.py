"""SAFETY_GUARDRAILS section — stable.

Always-present safety constraints.
"""
from prompting.types import PromptContext, SectionOutput, SectionID, CacheClass


def generate(ctx: PromptContext) -> SectionOutput:
    content = (
        "SAFETY CONSTRAINTS (non-negotiable):\n"
        "- Never fabricate information or invent APIs/fields/flows.\n"
        "- Never execute without explicit user authorization.\n"
        "- If ambiguity > 30%, request clarification instead of guessing.\n"
        "- Refuse harmful, illegal, or policy-violating requests tactfully.\n"
        "- Never expose raw memory, credentials, or internal state.\n"
        "- All tool access is least-privilege; use only what is provided.\n"
        "- If unsure, default to silence/clarification over action."
    )
    return SectionOutput(
        section_id=SectionID.SAFETY_GUARDRAILS,
        content=content,
        priority=8,
        cache_class=CacheClass.STABLE,
        tokens_est=90,
        included=True,
    )
