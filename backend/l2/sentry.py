"""L2 Sentry — Authoritative intent validation.

Spec §5.2: Gemini Pro, BE-only, shadow derivation.
Runs ONLY on: 1) Draft finalization  2) Execute attempt
NEVER per transcript fragment.

Uses PromptOrchestrator with VERIFY purpose via LLM Gateway.
Performs Shadow Derivation: ignores L1 initially, derives independently.
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
from prompting.llm_gateway import call_llm

logger = logging.getLogger(__name__)


@dataclass
class L2Verdict:
    """L2 authoritative validation result."""
    verdict_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    intent: str = ""
    canonical_target: str = ""
    primary_outcome: str = ""
    risk_tier: int = 0
    confidence: float = 0.0
    chain_of_logic: str = ""  # CoL trace (required)
    shadow_agrees_with_l1: bool = False
    conflicts: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    prompt_id: str = ""
    is_mock: bool = False


async def run_l2_sentry(
    session_id: str,
    user_id: str,
    transcript: str,
    l1_intent: str = "",
    l1_confidence: float = 0.0,
    dimensions: Optional[Dict[str, Any]] = None,
) -> L2Verdict:
    """Run L2 Sentry shadow derivation. ONLY at draft finalization or execute."""
    settings = get_settings()
    start = time.monotonic()

    if is_mock_llm() or not settings.EMERGENT_LLM_KEY:
        return _mock_l2(transcript, l1_intent, l1_confidence, start)

    try:
        # Skip DS recall if transcript is already gap-filled (contains enriched prefix)
        # to avoid sending the same context twice to the LLM.
        transcript_is_enriched = "\nUser mandate:" in transcript
        memory_snippets = None
        if not transcript_is_enriched and user_id:
            from memory.retriever import recall
            memory_snippets = await recall(user_id=user_id, query_text=transcript, n_results=3)
            logger.info("L2 Sentry: recalled %d memories for user=%s", len(memory_snippets), user_id)
        elif transcript_is_enriched:
            logger.debug("L2 Sentry: transcript pre-enriched — skipping recall to avoid duplication")

        # Fetch per-user optimization adjustments
        from prompting.user_profiles import get_prompt_adjustments
        user_adjustments = await get_prompt_adjustments(user_id)

        orchestrator = PromptOrchestrator()
        ctx = PromptContext(
            purpose=PromptPurpose.VERIFY,
            mode=PromptMode.INTERACTIVE,
            session_id=session_id,
            user_id=user_id,
            transcript=transcript,
            dimensions=dimensions,
            memory_snippets=memory_snippets if memory_snippets else None,
            user_adjustments=user_adjustments,
            task_description=(
                "Shadow derivation: independently verify the user's intent from this transcript. "
                "Ignore any prior hypothesis. Determine the REAL intent (e.g. 'Travel Concierge', "
                "'Event Planning', 'Hiring Pipeline'), the canonical_target, primary_outcome, "
                "risk_tier (0-3), confidence (0-1). "
                "Provide a chain_of_logic trace explaining your reasoning. "
                "Output JSON: {intent, canonical_target, primary_outcome, "
                "risk_tier, confidence, chain_of_logic}"
            ),
        )
        artifact, report = orchestrator.build(ctx)
        await save_prompt_snapshot(report)

        # Call Gemini (using Flash — Pro not confirmed available via emergent key)
        response = await call_llm(
            artifact=artifact,
            call_site_id="L2_SENTRY",
            model_provider="gemini",
            model_name="gemini-2.0-flash",
            session_id=f"l2-{session_id}",
        )

        latency_ms = (time.monotonic() - start) * 1000
        verdict = _parse_l2_response(response, l1_action_class, l1_confidence, latency_ms, artifact.prompt_id)

        logger.info(
            "L2 Sentry: session=%s action=%s conf=%.2f agrees=%s latency=%.0fms",
            session_id, verdict.action_class, verdict.confidence,
            verdict.shadow_agrees_with_l1, latency_ms,
        )
        return verdict

    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        logger.error("L2 Sentry failed: session=%s error=%s", session_id, str(e))
        return _mock_l2(transcript, l1_action_class, l1_confidence, start)


def check_l1_l2_agreement(l1_action: str, l1_conf: float, l2: L2Verdict) -> tuple[bool, str]:
    """Check L1/L2 conflict resolution per spec 5.4.

    Normalizes both action classes before comparison since L2 may
    return variant names (e.g. "Recruiting" for "TASK_CREATE").
    """
    from intent_rl.runner import _normalize_class
    l1_norm = _normalize_class(l1_action)
    l2_norm = _normalize_class(l2.action_class)

    if l1_norm != l2_norm:
        return False, f"Action mismatch: L1={l1_action}({l1_norm}) L2={l2.action_class}({l2_norm})"

    delta = abs(l1_conf - l2.confidence)
    if delta > 0.25:
        return False, f"Confidence delta {delta:.2f} > 0.25 (large disagreement)"

    if l1_conf < 0.55 or l2.confidence < 0.55:
        return False, f"Confidence too low: L1={l1_conf:.2f} L2={l2.confidence:.2f} (both must be > 0.55)"

    return True, "L1/L2 agreement verified"


def _parse_l2_response(
    response: str, l1_action: str, l1_conf: float, latency_ms: float, prompt_id: str
) -> L2Verdict:
    """Parse L2 LLM response into verdict."""
    try:
        text = response.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        data = json.loads(text)
        action = data.get("action_class", "DRAFT_ONLY")
        confidence = float(data.get("confidence", 0.5))

        verdict = L2Verdict(
            action_class=action,
            canonical_target=data.get("canonical_target", ""),
            primary_outcome=data.get("primary_outcome", ""),
            risk_tier=int(data.get("risk_tier", 0)),
            confidence=confidence,
            chain_of_logic=data.get("chain_of_logic", ""),
            shadow_agrees_with_l1=(action == l1_action),
            latency_ms=latency_ms,
            prompt_id=prompt_id,
        )

        # Check agreement
        agrees, reason = check_l1_l2_agreement(l1_action, l1_conf, verdict)
        if not agrees:
            verdict.conflicts.append(reason)

        return verdict

    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("L2 parse failed: %s", str(e))
        return L2Verdict(
            action_class="DRAFT_ONLY",
            confidence=0.3,
            chain_of_logic=f"Parse failed: {response[:100]}",
            latency_ms=latency_ms,
            prompt_id=prompt_id,
        )


def _mock_l2(
    transcript: str, l1_action: str, l1_conf: float, start_time: float
) -> L2Verdict:
    """Mock L2 — returns Unknown when no LLM available."""
    return L2Verdict(
        action_class="Unknown",
        confidence=0.3,
        chain_of_logic="Mock: LLM unavailable",
        shadow_agrees_with_l1=False,
        latency_ms=(time.monotonic() - start_time) * 1000,
        is_mock=True,
    )
