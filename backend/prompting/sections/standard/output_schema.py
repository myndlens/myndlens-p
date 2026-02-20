"""OUTPUT_SCHEMA section — defines what the LLM should output.

THOUGHT_TO_INTENT: The LLM extracts the ACTUAL INTENT as the user means it.
NOT a forced bucket. NOT a forced enum category.

The intent is what the user WANTS: "Travel Concierge", "Event Planning",
"Project Kickoff". The skill/agent layer maps this to executable actions LATER.
"""
from prompting.types import (
    PromptContext, PromptPurpose, SectionOutput, SectionID, CacheClass,
)

_SCHEMAS = {
    PromptPurpose.THOUGHT_TO_INTENT: (
        "{hypotheses: [{"
        "intent: str (the ACTUAL intent in plain language — e.g. 'Travel Concierge', "
        "'Event Planning', 'Project Kickoff', 'Hiring Pipeline', 'Financial Operations', "
        "'Content Creation', 'Customer Outreach', 'Personal Wellness', 'Data Analysis', "
        "'Incident Response', 'Weekly Planning', 'Marketing Campaign', etc. — "
        "use the REAL intent, not a code), "
        "summary: str (one sentence: what the user wants done), "
        "sub_intents: [str] (specific things needed: 'book flight', 'reserve hotel', 'schedule meeting'), "
        "confidence: 0-1, "
        "who: str (people involved, resolved from Digital Self), "
        "what: str (core action or deliverable), "
        "when: str (timing/deadline), "
        "where: str (location if relevant), "
        "ambiguity: 0-1"
        "}]}\n"
        "Max 3 hypotheses. Return JSON only."
    ),
    PromptPurpose.DIMENSIONS_EXTRACT: (
        "{who: str, what: str, when: str, where: str, how: str, "
        "confidence: 0-1, resolved_entities: [{ref: str, canonical: str}]}"
    ),
    PromptPurpose.VERIFY: (
        "{intent: str, canonical_target: str, primary_outcome: str, "
        "risk_tier: 0-3, confidence: 0-1, chain_of_logic: str}"
    ),
    PromptPurpose.SAFETY_GATE: (
        "{risk_tier: 0-3, harmful: bool, policy_violation: bool, "
        "escalation_needed: bool, reason: str}"
    ),
    PromptPurpose.MICRO_QUESTION: (
        "{questions: [{question: str (max 6 words, TTS-friendly), "
        "why: str, options: [str], dimension_filled: str}], max_questions: 3}\n"
        "Only personalized questions from Digital Self. Zero generic questions."
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
