"""Micro-Question Generator — Digital Self-powered clarification.

When L1 Scout has low confidence or ambiguity > 30%, this module generates
personalized micro-questions by combining:
  1. The extracted intent + gaps in dimensions
  2. The user's Digital Self (contacts, preferences, patterns)
  3. An LLM call to produce natural, TTS-friendly questions

Example:
  User: "Need to go to Sydney next week for the conference"
  Digital Self knows: Jacob (CMO), Soudha (wife), user prefers business class
  
  Micro-questions:
    "Is Jacob travelling with you? Should I book for him too?"
    "Business class as usual?"
    "Should I book the Hilton near the convention center again?"
"""
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from config.settings import get_settings
from config.feature_flags import is_mock_llm
from prompting.orchestrator import PromptOrchestrator
from prompting.types import PromptContext, PromptPurpose, PromptMode
from prompting.storage.mongo import save_prompt_snapshot

logger = logging.getLogger(__name__)


@dataclass
class MicroQuestion:
    question: str          # TTS-friendly, short
    why: str               # What gap this fills
    options: List[str]     # Suggested answers (if any)
    dimension_filled: str  # who/what/when/where/how


@dataclass
class MicroQuestionResult:
    questions: List[MicroQuestion]
    latency_ms: float
    prompt_id: str
    trigger_reason: str    # "low_confidence" | "high_ambiguity" | "missing_dimensions"


async def generate_micro_questions(
    session_id: str,
    user_id: str,
    transcript: str,
    hypothesis: str,
    confidence: float,
    dimensions: Dict[str, Any],
    memory_snippets: Optional[List[Dict]] = None,
    already_asked: Optional[List[str]] = None,
) -> MicroQuestionResult:
    """Generate personalized micro-questions from Digital Self + intent gaps.

    Called when:
      - confidence < 0.8
      - ambiguity > 0.3
      - key dimensions missing (who/what/when)
    """
    settings = get_settings()
    start = time.monotonic()

    # Determine trigger reason
    ambiguity = dimensions.get("ambiguity", 0.5)
    missing = [d for d in ["who", "what", "when", "where"] if not dimensions.get(d)]
    if confidence < 0.7:
        trigger = "low_confidence"
    elif ambiguity > 0.3:
        trigger = "high_ambiguity"
    elif missing:
        trigger = "missing_dimensions"
    else:
        trigger = "proactive_enrichment"

    if is_mock_llm() or not settings.EMERGENT_LLM_KEY:
        return _mock_questions(transcript, trigger, start)

    # Fetch Digital Self context if not provided
    if memory_snippets is None:
        from memory.retriever import recall
        memory_snippets = await recall(user_id=user_id, query_text=transcript, n_results=5)

    task = (
        f"User said: \"{transcript}\"\n"
        f"Extracted intent: {hypothesis}\n"
        f"Confidence: {confidence}\n"
        f"Current dimensions: {json.dumps(dimensions)}\n"
        f"Missing dimensions: {', '.join(missing) if missing else 'none'}\n"
        f"Trigger: {trigger}\n"
    )

    # Inject internal checklist — already answered vs still pending
    if already_asked:
        task += "\nINTERNAL CHECKLIST (do NOT re-ask these — already answered):\n"
        for q in already_asked:
            task += f"  ✓  {q}\n"
        task += "\nOnly generate questions for what is STILL unanswered.\n"

    task += (
        "\nRULES FOR MICRO-QUESTIONS:\n"
        "1. NEVER ask generic questions like 'Could you tell me more?' or 'What do you need?'\n"
        "2. EVERY question MUST reference a SPECIFIC person, place, preference, or pattern from the Digital Self memories\n"
        "3. If a memory mentions a person (colleague, spouse, CMO), ask if they are involved\n"
        "4. If a memory mentions a preference (hotel brand, flight class, car rental), confirm it\n"
        "5. If a memory mentions a past pattern (last trip, usual routine), reference it\n"
        "6. Questions must be so specific that ONLY this user would understand them\n"
        "7. If you cannot generate a personalized question from the memories, return ZERO questions\n\n"
        "TONE & BREVITY — Critical rules:\n"
        "- You are a trusted secretary who has worked with this person for years\n"
        "- NEVER break the user's chain of thought. They are still thinking.\n"
        "- Be SHORTER than the user. If they said 10 words, you say 5.\n"
        "- Maximum 6 words per question. Not 7. Not 8. SIX.\n"
        "- Use shorthand only: 'Hilton again?', 'Jacob joining?', 'Business class?'\n"
        "- NO full sentences. NO explanations. Just the nudge.\n"
        "- Think of it as a whisper, not a conversation.\n"
        "- Examples of GOOD: 'Hilton again?', 'Jacob too?', 'Usual car?'\n"
        "- Examples of BAD: 'Should I book the Hilton Sydney again like last time?'\n"
        "- The user is in flow. You are a gentle tap on the shoulder, nothing more."
    )

    orchestrator = PromptOrchestrator()
    ctx = PromptContext(
        purpose=PromptPurpose.MICRO_QUESTION,
        mode=PromptMode.INTERACTIVE,
        session_id=session_id,
        user_id=user_id,
        transcript=transcript,
        task_description=task,
        memory_snippets=memory_snippets,
    )
    artifact, report = orchestrator.build(ctx)
    await save_prompt_snapshot(report)

    from prompting.llm_gateway import call_llm
    response = await call_llm(
        artifact=artifact,
        call_site_id="MICRO_QUESTION_GEN",
        model_provider="gemini",
        model_name="gemini-2.0-flash",
        session_id=f"mq-{session_id}",
    )

    latency_ms = (time.monotonic() - start) * 1000
    questions = _parse_questions(response)

    logger.info(
        "[MicroQ] session=%s questions=%d trigger=%s latency=%.0fms",
        session_id, len(questions), trigger, latency_ms,
    )

    return MicroQuestionResult(
        questions=questions,
        latency_ms=latency_ms,
        prompt_id=artifact.prompt_id,
        trigger_reason=trigger,
    )


def should_ask_micro_questions(confidence: float, dimensions: Dict[str, Any]) -> bool:
    """Decide if micro-questions are needed based on L1 Scout output."""
    ambiguity = dimensions.get("ambiguity", 0.5)
    missing_key = not dimensions.get("who") or not dimensions.get("what")
    return confidence < 0.8 or ambiguity > 0.3 or missing_key


def _parse_questions(response: str) -> List[MicroQuestion]:
    """Parse LLM response into MicroQuestion list."""
    try:
        text = response.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        data = json.loads(text)
        raw_questions = data.get("questions", [])

        return [
            MicroQuestion(
                question=q.get("question", ""),
                why=q.get("why", ""),
                options=q.get("options", []),
                dimension_filled=q.get("dimension_filled", ""),
            )
            for q in raw_questions[:3]
        ]
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("[MicroQ] Parse failed: %s", e)
        return []


def _mock_questions(transcript: str, trigger: str, start: float) -> MicroQuestionResult:
    """Mock micro-questions — returns empty (no generic questions ever)."""
    return MicroQuestionResult(
        questions=[],
        latency_ms=(time.monotonic() - start) * 1000,
        prompt_id="mock",
        trigger_reason=trigger,
    )
