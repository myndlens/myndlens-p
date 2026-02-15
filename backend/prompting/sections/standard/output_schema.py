"""OUTPUT_SCHEMA section — compact, token-optimized.

Defines the expected output structure using minimal notation.
"""
from prompting.types import (
    PromptContext, PromptPurpose, SectionOutput, SectionID, CacheClass,
)

_SCHEMAS = {
    PromptPurpose.THOUGHT_TO_INTENT: (
        "{hypotheses: [{hypothesis: str, action_class: str, confidence: 0-1, "
        "evidence_spans: [{text, start, end}], dimensions: {}}]}\n"
        "Max 3 hypotheses."
    ),
    PromptPurpose.DIMENSIONS_EXTRACT: (
        "{a_set: {what, who, when, where, how, constraints}, "
        "b_set: {urgency: 0-1, emotional_load: 0-1, ambiguity: 0-1, "
        "reversibility: 0-1, user_confidence: 0-1}}"
    ),
    PromptPurpose.VERIFY: (
        "{action_class: str, canonical_target: str, primary_outcome: str, "
        "risk_tier: 0-3, confidence: 0-1, chain_of_logic: str}"
    ),
    PromptPurpose.SAFETY_GATE: (
        "{risk_tier: 0-3, harmful: bool, policy_violation: bool, "
        "escalation_needed: bool, reason: str}"
    ),
}


def generate(ctx: PromptContext) -> SectionOutput:
    schema = _SCHEMAS.get(ctx.purpose)
    if schema:
        content = f"Output JSON: {schema}"
    else:
        content = "Output structured JSON appropriate to the task."

    return SectionOutput(
        section_id=SectionID.OUTPUT_SCHEMA,
        content=content,
        priority=3,
        cache_class=CacheClass.STABLE,
        tokens_est=len(content) // 4,
        included=True,
    )
