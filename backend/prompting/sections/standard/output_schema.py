"""OUTPUT_SCHEMA section — stable per purpose.

Defines the expected output structure.
"""
import json
from prompting.types import (
    PromptContext, PromptPurpose, SectionOutput, SectionID, CacheClass,
)

_SCHEMAS = {
    PromptPurpose.THOUGHT_TO_INTENT: json.dumps({
        "hypotheses": [
            {
                "hypothesis": "string",
                "action_class": "COMM_SEND|SCHED_MODIFY|...",
                "confidence": 0.0,
                "evidence_spans": [{"text": "string", "start": 0, "end": 0}],
                "dimension_suggestions": {},
            }
        ],
        "max_hypotheses": 3,
    }, indent=2),
    PromptPurpose.DIMENSIONS_EXTRACT: json.dumps({
        "a_set": {
            "what": "string|null",
            "who": "string|null",
            "when": "string|null",
            "where": "string|null",
            "how": "string|null",
            "constraints": "string|null",
        },
        "b_set": {
            "urgency": 0.0,
            "emotional_load": 0.0,
            "ambiguity": 0.0,
            "reversibility": 0.0,
            "user_confidence": 0.0,
        },
    }, indent=2),
}


def generate(ctx: PromptContext) -> SectionOutput:
    schema = _SCHEMAS.get(ctx.purpose)
    if schema:
        content = f"You MUST respond with this JSON structure:\n```json\n{schema}\n```"
    else:
        content = "Respond in structured JSON appropriate to the task."

    return SectionOutput(
        section_id=SectionID.OUTPUT_SCHEMA,
        content=content,
        priority=3,
        cache_class=CacheClass.STABLE,
        tokens_est=len(content) // 4,
        included=True,
    )
