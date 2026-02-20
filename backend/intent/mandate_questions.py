"""Mandate Question Generator — ONE question per missing dimension.

Takes the mandate, finds EVERY [???], generates a whisper-question for each.
DS-known preferences: confirm with "X again?" 
Unknown: ask with smart options from the dimension schema.
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
    question: str
    fills_action: str
    fills_dimension: str
    options: List[str] = field(default_factory=list)


@dataclass
class MicroQuestionBatch:
    questions: List[MicroQuestion]
    total_missing: int
    batch_number: int
    latency_ms: float = 0.0


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


# Smart default options per dimension type — no LLM needed for these
_DIMENSION_OPTIONS = {
    "dep_time_pref": ["morning", "midday", "afternoon", "evening", "red-eye"],
    "ret_time_pref": ["morning", "midday", "afternoon", "evening"],
    "class": ["economy", "premium economy", "business", "first"],
    "seat_pref": ["window", "aisle", "any"],
    "meal_pref": ["standard", "vegetarian", "vegan", "halal", "kosher"],
    "baggage": ["carry-on only", "1 checked bag", "2 checked bags"],
    "room_type": ["single", "double", "twin", "suite"],
    "bed_type": ["king", "queen", "twin"],
    "star_rating": ["3-star", "4-star", "5-star"],
    "car_type": ["compact", "sedan", "SUV", "luxury", "minivan"],
    "transmission": ["automatic", "manual"],
    "insurance": ["basic", "full coverage", "none"],
    "gps": ["yes", "no"],
    "child_seat": ["yes", "no"],
    "direct_only": ["yes", "no"],
    "breakfast_included": ["yes", "no"],
    "late_checkout": ["yes", "no"],
    "additional_driver": ["yes", "no"],
    "price_range": ["budget", "mid-range", "fine dining"],
    "urgency": ["immediate", "today", "this week"],
    "tone": ["formal", "casual"],
    "format": ["pdf", "docx", "slides", "html"],
    "length": ["short", "medium", "detailed"],
    "recurring": ["one-time", "weekly", "biweekly", "monthly"],
}


async def generate_mandate_questions(
    session_id: str,
    user_id: str,
    transcript: str,
    mandate: Dict[str, Any],
    batch_size: int = 50,
    batch_number: int = 1,
) -> MicroQuestionBatch:
    """Generate whisper-questions for ALL missing mandate dimensions."""
    settings = get_settings()
    start = time.monotonic()

    all_missing = get_all_missing(mandate)
    if not all_missing:
        return MicroQuestionBatch(questions=[], total_missing=0, batch_number=batch_number)

    # Priority order: high actions first
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

    # Build explicit list — ONE line per dimension
    dim_lines = []
    for d in batch:
        opts = _DIMENSION_OPTIONS.get(d["dimension"], [])
        opt_str = f" (options: {'/'.join(opts)})" if opts else ""
        dim_lines.append(f"  {len(dim_lines)+1}. [{d['action']}] {d['dimension']}{opt_str}")

    task = (
        f"Intent: {mandate.get('intent', '')}\n"
        f"User said: \"{transcript}\"\n\n"
        f"Generate EXACTLY {len(batch)} questions — one per missing dimension:\n"
        + "\n".join(dim_lines) + "\n\n"
        "RULES:\n"
        "- EXACTLY one question per dimension listed above. Count must match.\n"
        "- Max 6 words. Secretary whisper tone.\n"
        "- If Digital Self has a pattern, reference it: 'Window again?', 'Hertz like usual?'\n"
        "- If options exist, pick the most likely and confirm: 'Automatic, right?'\n"
        "- If no DS data and no default, ask directly: 'GPS needed?', 'King or queen bed?'\n"
        "- NEVER skip a dimension. NEVER combine two into one question.\n\n"
        "Output JSON:\n"
        "{\"questions\": [\n"
        + ",\n".join(
            f'  {{"question": "...", "fills_action": "{d["action"]}", '
            f'"fills_dimension": "{d["dimension"]}", "options": [...]}}'
            for d in batch
        )
        + "\n]}"
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
        "[MandateMQ] session=%s batch=%d asked=%d/%d total_missing=%d %.0fms",
        session_id, batch_number, len(questions), len(batch), len(all_missing), latency_ms,
    )

    return MicroQuestionBatch(
        questions=questions, total_missing=len(all_missing),
        batch_number=batch_number, latency_ms=latency_ms,
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
