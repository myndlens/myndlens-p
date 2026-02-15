"""L1 Scout — high-speed intent hypothesis generator.

Spec §5.1: Gemini Flash, max 3 hypotheses, non-authoritative.
Uses PromptOrchestrator with THOUGHT_TO_INTENT purpose.
Outputs L1_Draft_Object with hypothesis, evidence spans, dimension suggestions.
"""
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config.settings import get_settings
from config.feature_flags import is_mock_llm
from prompting.orchestrator import PromptOrchestrator
from prompting.types import PromptContext, PromptPurpose, PromptMode
from prompting.storage.mongo import save_prompt_snapshot

logger = logging.getLogger(__name__)


@dataclass
class Hypothesis:
    hypothesis: str
    action_class: str  # COMM_SEND, SCHED_MODIFY, etc.
    confidence: float
    evidence_spans: List[Dict[str, Any]] = field(default_factory=list)
    dimension_suggestions: Dict[str, Any] = field(default_factory=dict)


@dataclass
class L1DraftObject:
    """L1 output — NON-AUTHORITATIVE (suggestions only)."""
    draft_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    hypotheses: List[Hypothesis] = field(default_factory=list)
    transcript: str = ""
    latency_ms: float = 0.0
    prompt_id: str = ""
    is_mock: bool = False


async def run_l1_scout(
    session_id: str,
    user_id: str,
    transcript: str,
) -> L1DraftObject:
    """Run L1 Scout on a transcript. Returns max 3 hypotheses."""
    settings = get_settings()
    start = time.monotonic()

    if is_mock_llm() or not settings.EMERGENT_LLM_KEY:
        return _mock_l1(transcript, start)

    try:
        # Recall relevant memories from Digital Self
        from memory.retriever import recall
        memory_snippets = await recall(user_id=user_id, query_text=transcript, n_results=3)
        logger.info("L1 Scout: recalled %d memories for user=%s", len(memory_snippets), user_id)

        # Fetch per-user optimization adjustments
        from prompting.user_profiles import get_prompt_adjustments
        user_adjustments = await get_prompt_adjustments(user_id)

        # Build prompt via orchestrator
        orchestrator = PromptOrchestrator()
        ctx = PromptContext(
            purpose=PromptPurpose.THOUGHT_TO_INTENT,
            mode=PromptMode.INTERACTIVE,
            session_id=session_id,
            user_id=user_id,
            transcript=transcript,
            memory_snippets=memory_snippets if memory_snippets else None,
            user_adjustments=user_adjustments,
        )
        artifact, report = orchestrator.build(ctx)
        await save_prompt_snapshot(report)

        # Call Gemini via LLM Gateway (the ONLY allowed path)
        from prompting.llm_gateway import call_llm

        response = await call_llm(
            artifact=artifact,
            call_site_id="L1_SCOUT",
            model_provider="gemini",
            model_name="gemini-2.0-flash",
            session_id=f"l1-{session_id}",
        )

        latency_ms = (time.monotonic() - start) * 1000

        # Parse response
        draft = _parse_l1_response(response, transcript, latency_ms, artifact.prompt_id)

        logger.info(
            "L1 Scout: session=%s hypotheses=%d latency=%.0fms",
            session_id, len(draft.hypotheses), latency_ms,
        )
        return draft

    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        logger.error("L1 Scout failed: session=%s error=%s latency=%.0fms", session_id, str(e), latency_ms)
        return _mock_l1(transcript, start)


def _parse_l1_response(response: str, transcript: str, latency_ms: float, prompt_id: str) -> L1DraftObject:
    """Parse LLM response into L1DraftObject."""
    hypotheses = []

    # Try to parse JSON from response
    try:
        # Extract JSON block if wrapped in markdown
        text = response.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        data = json.loads(text)
        raw_hypotheses = data.get("hypotheses", [])

        for h in raw_hypotheses[:3]:  # Max 3
            hypotheses.append(Hypothesis(
                hypothesis=h.get("hypothesis", ""),
                action_class=h.get("action_class", "DRAFT_ONLY"),
                confidence=float(h.get("confidence", 0.5)),
                evidence_spans=h.get("evidence_spans", []),
                dimension_suggestions=h.get("dimension_suggestions", {}),
            ))
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("L1 parse failed, creating single hypothesis from text: %s", str(e))
        # Fallback: create a single hypothesis from the raw response
        hypotheses.append(Hypothesis(
            hypothesis=response[:200] if response else "Unable to interpret",
            action_class="DRAFT_ONLY",
            confidence=0.3,
        ))

    return L1DraftObject(
        hypotheses=hypotheses,
        transcript=transcript,
        latency_ms=latency_ms,
        prompt_id=prompt_id,
    )


def _mock_l1(transcript: str, start_time: float) -> L1DraftObject:
    """Mock L1 for testing without LLM."""
    lower = transcript.lower()
    hypotheses = []

    if "send" in lower and "message" in lower:
        hypotheses.append(Hypothesis(
            hypothesis="User wants to send a message",
            action_class="COMM_SEND",
            confidence=0.85,
            evidence_spans=[{"text": "send a message", "start": 0, "end": len(transcript)}],
            dimension_suggestions={"what": "send message", "who": _extract_name(transcript)},
        ))
    elif "schedule" in lower or "meeting" in lower:
        hypotheses.append(Hypothesis(
            hypothesis="User wants to schedule something",
            action_class="SCHED_MODIFY",
            confidence=0.80,
            evidence_spans=[{"text": transcript, "start": 0, "end": len(transcript)}],
            dimension_suggestions={"what": "schedule meeting"},
        ))
    else:
        hypotheses.append(Hypothesis(
            hypothesis="User is expressing a general request",
            action_class="DRAFT_ONLY",
            confidence=0.5,
            dimension_suggestions={"what": transcript[:50]},
        ))

    return L1DraftObject(
        hypotheses=hypotheses,
        transcript=transcript,
        latency_ms=(time.monotonic() - start_time) * 1000,
        is_mock=True,
    )


def _extract_name(text: str) -> str:
    """Simple name extraction from transcript."""
    for word in ["to ", "from ", "with "]:
        if word in text.lower():
            after = text.lower().split(word, 1)[1].split()[0] if word in text.lower() else ""
            return after.capitalize()
    return ""
