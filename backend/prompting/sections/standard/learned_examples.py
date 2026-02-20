"""LEARNED_EXAMPLES section — few-shot corrections from RL training.

Injects learned intent corrections into the L1 Scout prompt so the LLM
sees examples of previously misclassified intents and their correct labels.

This trains the INTENT ENGINE, not the Digital Self.
"""
import logging
from typing import List, Dict, Any

from prompting.types import (
    PromptContext, PromptPurpose, SectionOutput, SectionID, CacheClass,
)

logger = logging.getLogger(__name__)


async def _get_corrections(n: int = 5) -> List[Dict[str, Any]]:
    """Fetch the most recent/relevant corrections from the RL training store."""
    from core.database import get_db
    db = get_db()
    cursor = db.intent_corrections.find(
        {}, {"_id": 0}
    ).sort("created_at", -1).limit(n)
    return await cursor.to_list(length=n)


def generate(ctx: PromptContext) -> SectionOutput:
    """Generate few-shot examples from RL corrections.

    Only included for THOUGHT_TO_INTENT purpose.
    """
    if ctx.purpose != PromptPurpose.THOUGHT_TO_INTENT:
        return SectionOutput(
            section_id=SectionID.LEARNED_EXAMPLES,
            content="",
            priority=7,
            cache_class=CacheClass.SEMISTABLE,
            tokens_est=0,
            included=False,
            gating_reason="Only for THOUGHT_TO_INTENT",
        )

    # Corrections are loaded synchronously from a cached list
    # (populated by the RL loop, refreshed on each iteration)
    corrections = _CACHED_CORRECTIONS

    if not corrections:
        return SectionOutput(
            section_id=SectionID.LEARNED_EXAMPLES,
            content="",
            priority=7,
            cache_class=CacheClass.SEMISTABLE,
            tokens_est=0,
            included=False,
            gating_reason="No corrections available",
        )

    lines = ["Few-shot examples from training (use these to improve classification):"]
    for c in corrections[:8]:  # Max 8 examples to stay within token budget
        lines.append(
            f"- Input: \"{c['fragment'][:60]}...\" → Correct: {c['correct_intent']} (not {c['wrong_class']})"
        )

    content = "\n".join(lines)
    return SectionOutput(
        section_id=SectionID.LEARNED_EXAMPLES,
        content=content,
        priority=7,  # After task context, before memory
        cache_class=CacheClass.SEMISTABLE,
        tokens_est=len(content) // 4,
        included=True,
    )


# ── Correction Cache (updated by RL loop) ────────────────────────────────────

_CACHED_CORRECTIONS: List[Dict[str, Any]] = []


def update_correction_cache(corrections: List[Dict[str, Any]]) -> None:
    """Update the in-memory correction cache. Called by the RL loop."""
    global _CACHED_CORRECTIONS
    _CACHED_CORRECTIONS = corrections
    logger.info("[LearnedExamples] Cache updated with %d corrections", len(corrections))


async def load_corrections_from_db() -> None:
    """Load corrections from MongoDB into cache (called at startup or after RL run)."""
    corrections = await _get_corrections(n=10)
    update_correction_cache(corrections)
