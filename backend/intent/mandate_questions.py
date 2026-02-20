"""Mandate Question Generator — LLM-driven, zero hardcoding.

The LLM receives the mandate with missing dimensions.
The LLM generates the right question with the right options.
No hardcoded option maps. No hardcoded schemas.
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


async def generate_mandate_questions(
    session_id: str,
    user_id: str,
    transcript: str,
    mandate: Dict[str, Any],
    batch_size: int = 50,
    batch_number: int = 1,
) -> MicroQuestionBatch:
    """Generate whisper-questions for ALL missing mandate dimensions. Zero hardcoding."""
    settings = get_settings()
    start = time.monotonic()

    all_missing = get_all_missing(mandate)
    if not all_missing:
        return MicroQuestionBatch(questions=[], total_missing=0, batch_number=batch_number)

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

    # Build the missing list — just action + dimension name
    dim_lines = "\n".join(
        f"  {i+1}. [{d['action']}] {d['dimension']}"
        for i, d in enumerate(batch)
    )

    task = (
        f"Intent: {mandate.get('intent', '')}\n"
        f"User said: \"{transcript}\"\n\n"
        f"There are {len(batch)} missing dimensions across these actions:\n{dim_lines}\n\n"
        "Club ALL missing dimensions into MAXIMUM 3 conversational questions.\n"
        "Each question covers MULTIPLE dimensions naturally.\n"
        "The user should feel like a quick chat, NOT an interrogation.\n\n"
        "EXAMPLE — 15 missing dims clubbed into 2 questions:\n"
        "  Q1: 'JFK morning, window, veggie — usual setup?' → covers dep_airport, dep_time, seat, meal\n"
        "  Q2: 'Hilton double, breakfast, sedan with GPS?' → covers hotel, room, breakfast, car, gps\n\n"
        "RULES:\n"
        "- MAXIMUM 3 questions total. Club related dims into one natural question.\n"
        "- Group by action: flight stuff together, hotel stuff together.\n"
        "- Use Digital Self: confirm known preferences in bulk: 'usual flight setup?'\n"
        "- Secretary tone. Max 10 words per question. Natural, not a form.\n"
        "- For each question, list ALL dimensions it fills.\n\n"
        "Output JSON:\n"
        "{\"questions\": [{\"question\": str, \"fills\": [{\"action\": str, \"dimension\": str}]}]}\n"
        "Maximum 3 questions."
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
        "[MandateMQ] session=%s asked=%d/%d total_missing=%d %.0fms",
        session_id, len(questions), len(batch), len(all_missing), latency_ms,
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
