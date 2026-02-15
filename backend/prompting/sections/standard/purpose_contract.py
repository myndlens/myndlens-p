"""PURPOSE_CONTRACT section — streamlined, token-optimized.

Defines what the LLM is allowed to do for this specific call.
Uses concise arrow notation for clarity.
"""
from prompting.types import (
    PromptContext, PromptPurpose, SectionOutput, SectionID, CacheClass,
)

_CONTRACTS = {
    PromptPurpose.THOUGHT_TO_INTENT: (
        "Task: Interpret input -> max 3 hypotheses with evidence. Interpretation only."
    ),
    PromptPurpose.DIMENSIONS_EXTRACT: (
        "Task: Extract dimensions (what/who/when/where/how/constraints) from transcript. "
        "No inference beyond stated or recalled."
    ),
    PromptPurpose.PLAN: (
        "Task: Produce execution plan with sequencing, dependencies, fallbacks. No execution."
    ),
    PromptPurpose.EXECUTE: (
        "Task: Execute approved plan using provided tools only. Follow constraints. Report results."
    ),
    PromptPurpose.VERIFY: (
        "Task: Verify output for factual consistency, policy compliance, no hallucination. Flag conflicts."
    ),
    PromptPurpose.SAFETY_GATE: (
        "Task: Classify risk tier. Check harmful intent, policy violations, escalation needs."
    ),
    PromptPurpose.SUMMARIZE: (
        "Task: Compress for user display. Concise, accurate, no additions."
    ),
    PromptPurpose.SUBAGENT_TASK: (
        "Task: Complete narrow sub-task below. Minimal mode, no scope excess."
    ),
}


def generate(ctx: PromptContext) -> SectionOutput:
    contract = _CONTRACTS.get(ctx.purpose, "Purpose not defined.")
    return SectionOutput(
        section_id=SectionID.PURPOSE_CONTRACT,
        content=contract,
        priority=2,
        cache_class=CacheClass.STABLE,
        tokens_est=len(contract) // 4,
        included=True,
    )
