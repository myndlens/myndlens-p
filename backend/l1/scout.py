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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config.settings import get_settings
from config.feature_flags import is_mock_llm
from prompting.orchestrator import PromptOrchestrator
from prompting.types import PromptContext, PromptPurpose, PromptMode
from prompting.storage.mongo import save_prompt_snapshot

logger = logging.getLogger(__name__)


@dataclass
class Hypothesis:
    hypothesis: str        # summary of what user wants
    intent: str            # the REAL intent: "Travel Concierge", "Event Planning", etc.
    confidence: float
    sub_intents: list = field(default_factory=list)  # ["book flight", "reserve hotel"]
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
    context_capsule: Optional[str] = None,
    original_transcript: Optional[str] = None,  # raw user words (before gap filling)
) -> L1DraftObject:
    """Run L1 Scout on a transcript. Returns max 3 hypotheses.

    context_capsule: JSON string from the device's on-device PKG (Digital Self).
    When provided, used instead of server-side memory recall.
    """
    settings = get_settings()
    start = time.monotonic()

    if is_mock_llm() or not settings.EMERGENT_LLM_KEY:
        raise RuntimeError("L1 Scout requires EMERGENT_LLM_KEY. No LLM fallback per zero-mock policy.")

    try:
        # Use device context capsule if provided (on-device Digital Self)
        # Fall back to server-side recall ONLY if no capsule (legacy / empty PKG)
        # NOTE: if transcript is already gap-filled (enriched), skip memory_snippets
        #       to avoid sending the same Digital Self context twice to the LLM.
        memory_snippets = None
        transcript_is_enriched = "\nUser mandate:" in transcript

        if not transcript_is_enriched:
            if context_capsule:
                try:
                    capsule_data = json.loads(context_capsule)
                    summary = capsule_data.get("summary", "")
                    if summary:
                        memory_snippets = [{"text": summary, "provenance": "DEVICE_PKG", "distance": 0.0}]
                        logger.info("L1 Scout: using on-device context capsule for user=%s", user_id)
                except Exception:
                    logger.warning("L1 Scout: invalid context capsule, falling back to server recall")

            if memory_snippets is None and user_id:
                from mcp.ds_server import call_tool
                result = await call_tool("search_memory", {
                    "user_id": user_id, "query": transcript, "n_results": 3,
                })
                memory_snippets = result.get("results", []) if isinstance(result, dict) else []
                logger.info("L1 Scout: recalled %d memories (MCP) for user=%s", len(memory_snippets), user_id)
        else:
            logger.debug("L1 Scout: transcript is pre-enriched — skipping memory_snippets to avoid duplication")

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
        draft = _parse_l1_response(
            response,
            original_transcript or transcript,  # store original for user-facing display
            latency_ms,
            artifact.prompt_id,
        )

        logger.info(
            "L1 Scout: session=%s hypotheses=%d latency=%.0fms",
            session_id, len(draft.hypotheses), latency_ms,
        )
        await store_draft(draft)
        return draft

    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        logger.error("L1 Scout failed: session=%s error=%s latency=%.0fms", session_id, str(e), latency_ms)
        raise


def _parse_l1_response(response: str, transcript: str, latency_ms: float, prompt_id: str) -> L1DraftObject:
    """Parse LLM response into L1DraftObject — extracts REAL intent."""
    hypotheses = []

    try:
        text = response.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        data = json.loads(text)
        raw_hypotheses = data.get("hypotheses", [])

        for h in raw_hypotheses[:3]:
            # New schema: intent + sub_intents
            intent = h.get("intent", "")
            summary = h.get("summary", h.get("hypothesis", ""))
            sub_intents = h.get("sub_intents", [])

            # Build dimensions from flat fields
            dims = {}
            for dim_key in ("who", "what", "when", "where", "ambiguity"):
                if h.get(dim_key):
                    dims[dim_key] = h[dim_key]
            # Also check nested dimension_suggestions for backwards compat
            if h.get("dimension_suggestions"):
                dims.update(h["dimension_suggestions"])

            hypotheses.append(Hypothesis(
                hypothesis=summary,
                intent=intent,
                confidence=float(h.get("confidence", 0.5)),
                sub_intents=sub_intents,
                evidence_spans=h.get("evidence_spans", []),
                dimension_suggestions=dims,
            ))
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("L1 parse failed (%s) for transcript='%s...' response='%s...'",
                       type(e).__name__, transcript[:40], response[:80] if response else "")
        hypotheses.append(Hypothesis(
            hypothesis=f"User wants to: {transcript[:60]}",
            intent="Unknown",
            confidence=0.3,
        ))

    return L1DraftObject(
        hypotheses=hypotheses,
        transcript=transcript,
        latency_ms=latency_ms,
        prompt_id=prompt_id,
    )


def _mock_l1(transcript: str, start_time: float) -> L1DraftObject:
    """Mock L1 — kept for test compatibility only. Not used in production pipeline."""
    return L1DraftObject(
        hypotheses=[Hypothesis(
            hypothesis=transcript[:80],
            intent="Unknown",
            confidence=0.3,
        )],
        transcript=transcript,
        latency_ms=(time.monotonic() - start_time) * 1000,
        is_mock=True,
    )


async def store_draft(draft: L1DraftObject) -> None:
    """Persist L1 draft to MongoDB."""
    from core.database import get_db
    db = get_db()
    doc = {
        "draft_id": draft.draft_id,
        "transcript": draft.transcript,
        "hypotheses": [
            {
                "hypothesis": h.hypothesis,
                "intent": h.intent,
                "sub_intents": h.sub_intents,
                "confidence": h.confidence,
                "dimension_suggestions": h.dimension_suggestions,
            }
            for h in draft.hypotheses
        ],
        "is_mock": draft.is_mock,
        "latency_ms": draft.latency_ms,
        "created_at": datetime.now(timezone.utc),
    }
    await db.l1_drafts.replace_one({"draft_id": draft.draft_id}, doc, upsert=True)


async def get_draft(draft_id: str) -> Optional[L1DraftObject]:
    """Retrieve a stored L1 draft by ID."""
    from core.database import get_db
    db = get_db()
    doc = await db.l1_drafts.find_one({"draft_id": draft_id}, {"_id": 0})
    if not doc:
        return None
    hypotheses = [
        Hypothesis(
            hypothesis=h["hypothesis"],
            intent=h.get("intent", ""),
            sub_intents=h.get("sub_intents", []),
            confidence=h["confidence"],
            dimension_suggestions=h.get("dimension_suggestions", {}),
        )
        for h in doc.get("hypotheses", [])
    ]
    return L1DraftObject(
        draft_id=doc["draft_id"],
        transcript=doc["transcript"],
        hypotheses=hypotheses,
        is_mock=doc.get("is_mock", True),
        latency_ms=doc.get("latency_ms", 0),
    )
