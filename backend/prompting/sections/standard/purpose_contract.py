"""PURPOSE_CONTRACT section — stable per purpose.

Defines what the LLM is allowed to do for this specific call.
"""
from prompting.types import (
    PromptContext, PromptPurpose, SectionOutput, SectionID, CacheClass,
)

_CONTRACTS = {
    PromptPurpose.THOUGHT_TO_INTENT: (
        "Your task: Interpret the user's spoken input and propose up to 3 candidate intents. "
        "Output structured hypothesis objects with evidence spans referencing the transcript. "
        "Do NOT plan, execute, or use tools. Only interpret."
    ),
    PromptPurpose.DIMENSIONS_EXTRACT: (
        "Your task: Extract structured dimensions (what, who, when, where, how, constraints) "
        "from the provided transcript and context. Output a dimensions object only. "
        "Do NOT plan, execute, or use tools. Do NOT infer beyond what is stated or recalled."
    ),
    PromptPurpose.PLAN: (
        "Your task: Given hardened intent and dimensions, produce an execution plan with "
        "sequencing, dependencies, and fallback paths. Do NOT execute."
    ),
    PromptPurpose.EXECUTE: (
        "Your task: Execute the approved plan using ONLY the tools provided. "
        "Follow constraints strictly. Report results."
    ),
    PromptPurpose.VERIFY: (
        "Your task: Verify the provided output for factual consistency, "
        "policy compliance, and absence of hallucination. Flag conflicts."
    ),
    PromptPurpose.SAFETY_GATE: (
        "Your task: Classify the risk tier of the proposed action. "
        "Check for harmful intent, policy violations, and escalation needs."
    ),
    PromptPurpose.SUMMARIZE: (
        "Your task: Compress the provided content for user display. "
        "Be concise and accurate. Do not add information."
    ),
    PromptPurpose.SUBAGENT_TASK: (
        "Your task: Complete the narrow sub-task described below. "
        "Minimal mode. Do not exceed scope."
    ),
}


def generate(ctx: PromptContext) -> SectionOutput:
    contract = _CONTRACTS.get(ctx.purpose, "Purpose not defined.")
    return SectionOutput(
        section_id=SectionID.PURPOSE_CONTRACT,
        content=contract,
        priority=2,
        cache_class=CacheClass.STABLE,
        tokens_est=50,
        included=True,
    )
