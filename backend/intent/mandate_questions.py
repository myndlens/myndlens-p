"""Micro-Question Generator v2 — Driven by mandate dimensions, not vague intent.

Takes the full mandate with source-tagged dimensions.
For EVERY [???] (missing) dimension, generates a targeted whisper-question.
Groups into batches of 2-3 (don't overwhelm).
Each question is max 6 words, Digital Self-powered, secretary tone.

The loop runs until ALL dimensions are filled = Definitive Mandate.
"""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config.settings import get_settings
from config.feature_flags import is_mock_llm
from prompting.orchestrator import PromptOrchestrator
from prompting.types import PromptContext, PromptPurpose, PromptMode
from prompting.storage.mongo import save_prompt_snapshot

logger = logging.getLogger(__name__)


@dataclass
class MicroQuestion:
    question: str          # Max 6 words, secretary whisper
    fills_action: str      # Which action this belongs to (e.g., "book flight")
    fills_dimension: str   # Which dimension (e.g., "seat_pref")
    options: List[str] = field(default_factory=list)


@dataclass
class MicroQuestionBatch:
    questions: List[MicroQuestion]
    total_missing: int     # How many dims still missing across all actions
    batch_number: int      # Which batch this is (1, 2, 3...)
    latency_ms: float = 0.0
    prompt_id: str = ""


def get_all_missing(mandate: Dict[str, Any]) -> List[Dict[str, str]]:
    """Extract ALL missing dimensions from a mandate."""
    missing = []
    for action in mandate.get("actions", []):
        action_name = action.get("action", "unknown")
        priority = action.get("priority", "medium")
        for dim_name, dim_val in action.get("dimensions", {}).items():
            if isinstance(dim_val, dict) and dim_val.get("source") == "missing":
                missing.append({
                    "action": action_name,
                    "dimension": dim_name,
                    "priority": priority,
                })
    return missing


async def generate_mandate_questions(
    session_id: str,
    user_id: str,
    transcript: str,
    mandate: Dict[str, Any],
    batch_size: int = 3,
    batch_number: int = 1,
) -> MicroQuestionBatch:
    """Generate whisper-questions for missing mandate dimensions."""
    settings = get_settings()
    start = time.monotonic()

    all_missing = get_all_missing(mandate)
    if not all_missing:
        return MicroQuestionBatch(questions=[], total_missing=0, batch_number=batch_number)

    # Take next batch (high priority first)
    priority_order = {"high": 0, "medium": 1, "low": 2}
    all_missing.sort(key=lambda x: priority_order.get(x["priority"], 1))
    batch = all_missing[:batch_size]

    if is_mock_llm() or not settings.EMERGENT_LLM_KEY:
        return MicroQuestionBatch(
            questions=[], total_missing=len(all_missing),
            batch_number=batch_number, latency_ms=(time.monotonic() - start) * 1000,
        )

    from memory.retriever import recall
    memory_snippets = await recall(user_id=user_id, query_text=transcript, n_results=5)

    # Build the dimension list for the LLM
    dims_to_ask = "\n".join(
        f"  - action: {d['action']}, dimension: {d['dimension']}"
        for d in batch
    )

    task = (
        f"Intent: {mandate.get('intent', '')}\n"
        f"User said: \"{transcript}\"\n\n"
        f"These dimensions are MISSING and need user input:\n{dims_to_ask}\n\n"
        "Generate ONE whisper-question for EACH missing dimension.\n"
        "Use Digital Self memories to make each question personalized.\n\n"
        "RULES — ABSOLUTE:\n"
        "- Max 6 words per question. COUNT THEM.\n"
        "- Secretary tone. You KNOW this person.\n"
        "- NEVER generic. ALWAYS reference a name, brand, or past pattern.\n"
        "- If Digital Self has a preference for this dimension, CONFIRM it.\n"
        "  e.g., seat_pref + DS says 'prefers window' → 'Window seat again?'\n"
        "- If no DS data, ask with smart default:\n"
        "  e.g., meal_pref → 'Vegetarian like usual?' (if DS says so) or 'Any meal preference?' ONLY if DS is empty\n"
        "- Include options where relevant.\n"
        "- NEVER break user's flow. This is a checklist whisper.\n\n"
        "Output JSON:\n"
        "{\"questions\": [{\"question\": str, \"fills_action\": str, "
        "\"fills_dimension\": str, \"options\": [str]}]}"
    )

    orchestrator = PromptOrchestrator()
    ctx = PromptContext(
        purpose=PromptPurpose.MICRO_QUESTION,
        mode=PromptMode.INTERACTIVE,
        session_id=session_id,
        user_id=user_id,
        transcript=transcript,
        memory_snippets=memory_snippets if memory_snippets else None,
        task_description=task,
    )
    artifact, report = orchestrator.build(ctx)
    await save_prompt_snapshot(report)

    from prompting.llm_gateway import call_llm
    response = await call_llm(
        artifact=artifact,
        call_site_id="MICRO_QUESTION_GEN",
        model_provider="gemini",
        model_name="gemini-2.0-flash",
        session_id=f"mq-mandate-{session_id}",
    )

    latency_ms = (time.monotonic() - start) * 1000
    questions = _parse_questions(response)

    logger.info(
        "[MandateMQ] session=%s batch=%d questions=%d total_missing=%d %.0fms",
        session_id, batch_number, len(questions), len(all_missing), latency_ms,
    )

    return MicroQuestionBatch(
        questions=questions,
        total_missing=len(all_missing),
        batch_number=batch_number,
        latency_ms=latency_ms,
        prompt_id=artifact.prompt_id,
    )


def _parse_questions(response: str) -> List[MicroQuestion]:
    try:
        text = response.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        data = json.loads(text)
        return [
            MicroQuestion(
                question=q.get("question", ""),
                fills_action=q.get("fills_action", ""),
                fills_dimension=q.get("fills_dimension", ""),
                options=q.get("options", []),
            )
            for q in data.get("questions", [])
        ]
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("[MandateMQ] Parse failed: %s", e)
        return []
