"""Guardrails Engine — B8.

Continuous evaluation of intents against safety constraints.
Checked as thought capture progresses, not just at execution.

Gates:
  - Ambiguity >30%      → Silence/Clarify (deterministic — dimension score)
  - Emotional load high → Cooldown (deterministic — dimension score)
  - Harm / policy       → SAFETY_GATE LLM (dynamic — context-aware, not keyword)
  - Low confidence      → Clarify (deterministic — L1 score)
"""
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from dimensions.engine import DimensionState
from l1.scout import L1DraftObject

logger = logging.getLogger(__name__)


class GuardrailResult(str, Enum):
    PASS = "PASS"
    SILENCE = "SILENCE"       # Ambiguity too high
    CLARIFY = "CLARIFY"       # Need more info
    REFUSE = "REFUSE"         # Policy violation / harm
    COOLDOWN = "COOLDOWN"     # Emotional load too high
    INFEASIBLE = "INFEASIBLE" # Physically impossible or beyond system capabilities


@dataclass
class GuardrailCheck:
    result: GuardrailResult
    reason: str
    nudge: Optional[str] = None
    block_execution: bool = False


async def _assess_harm_llm(
    transcript: str,
    ds_context: str,
    session_id: str,
    user_id: str,
) -> GuardrailCheck:
    """Use SAFETY_GATE LLM call to assess harm — no hardcoded patterns.

    Uses the existing PromptPurpose.SAFETY_GATE + GUARDRAILS_CLASSIFIER call site.
    Output schema: {risk_tier: 0-3, harmful: bool, policy_violation: bool,
                    escalation_needed: bool, reason: str}
    """
    from config.settings import get_settings
    from config.feature_flags import is_mock_llm
    settings = get_settings()

    # Fast path: mock mode or no LLM key
    if is_mock_llm() or not settings.EMERGENT_LLM_KEY:
        return _mock_harm_check(transcript)

    try:
        from prompting.orchestrator import PromptOrchestrator
        from prompting.llm_gateway import call_llm
        from prompting.types import PromptContext, PromptPurpose, PromptMode

        ctx = PromptContext(
            purpose=PromptPurpose.SAFETY_GATE,
            mode=PromptMode.SILENT,
            session_id=session_id,
            user_id=user_id,
            transcript=transcript,
            task_description=(
                f"Assess this request for: 1) harm/policy violations, 2) feasibility.\n"
                f"User context: {ds_context or 'No Digital Self context available.'}\n\n"
                f"HARM: Normal business requests (email, schedule, code, research) are NOT harmful. "
                f"Only flag: unauthorized access, fraud, harassment, illegal activity, direct harm.\n\n"
                f"FEASIBILITY: Can a software AI agent actually do this?\n"
                f"- FEASIBLE: send email, write code, search web, book travel, play music, make calls, schedule\n"
                f"- INFEASIBLE: physical actions (scratch, hug, cook, clean, drive), "
                f"things requiring a physical body or real-world actuation the agent cannot perform\n"
                f"- ALTERNATIVE: if infeasible, suggest what the agent CAN do instead "
                f"(e.g. 'drive home' → 'book a ride', 'cook dinner' → 'find a recipe')\n\n"
                f"Output JSON: {{\"harmful\": bool, \"policy_violation\": bool, \"risk_tier\": 0-3, "
                f"\"feasible\": bool, \"alternative\": str|null, \"reason\": str}}"
            ),
        )
        orchestrator = PromptOrchestrator()
        artifact, _ = orchestrator.build(ctx)

        start = time.monotonic()
        response = await call_llm(
            artifact=artifact,
            call_site_id="GUARDRAILS_CLASSIFIER",
            model_provider="gemini",
            model_name="gemini-2.0-flash",
            session_id=f"guardrails-{session_id}",
        )
        latency_ms = (time.monotonic() - start) * 1000

        # Parse response
        raw = response.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)

        harmful = data.get("harmful", False)
        policy_violation = data.get("policy_violation", False)
        risk_tier = int(data.get("risk_tier", 0))
        feasible = data.get("feasible", True)
        alternative = data.get("alternative") or None
        reason = data.get("reason", "")

        logger.info(
            "[SAFETY_GATE] session=%s harmful=%s policy=%s risk=%d feasible=%s latency=%.0fms",
            session_id, harmful, policy_violation, risk_tier, feasible, latency_ms,
        )

        if harmful or policy_violation or risk_tier >= 3:
            return GuardrailCheck(
                result=GuardrailResult.REFUSE,
                reason=reason,
                nudge="I can't assist with that. Is there something else I can help with?",
                block_execution=True,
            )

        if not feasible:
            nudge = "I can't do that physically."
            if alternative:
                nudge += f" But I can {alternative}. Would you like me to?"
            else:
                nudge += " Is there something else I can help with?"
            return GuardrailCheck(
                result=GuardrailResult.INFEASIBLE,
                reason=reason or "Request requires physical action beyond agent capabilities",
                nudge=nudge,
                block_execution=True,
            )

        return GuardrailCheck(
            result=GuardrailResult.PASS,
            reason=reason or "SAFETY_GATE: no harm detected",
            block_execution=False,
        )

    except Exception as e:
        logger.error("[SAFETY_GATE] LLM assessment failed: %s — defaulting PASS", str(e))
        # Fail open for system errors (not for harm): the QC sentry is another layer
        return GuardrailCheck(
            result=GuardrailResult.PASS,
            reason=f"SAFETY_GATE unavailable ({type(e).__name__}) — passed to QC",
            block_execution=False,
        )


def _mock_harm_check(transcript: str) -> GuardrailCheck:
    """Mock mode — pass everything. Real harm detection is LLM-only."""
    return GuardrailCheck(result=GuardrailResult.PASS, reason="Mock: LLM unavailable", block_execution=False)


def check_guardrails(
    transcript: str,
    dimensions: Optional[DimensionState] = None,
    l1_draft: Optional[L1DraftObject] = None,
    session_id: str = "",
    user_id: str = "",
    ds_context: str = "",
) -> GuardrailCheck:
    """Run deterministic guardrail gates synchronously.

    NOTE: This function is used by test files only. The live pipeline
    calls _assess_harm_llm() (async, LLM-based) directly.

    Deterministic gates (fast, no LLM):
      1. Ambiguity > 30% → SILENCE
      2. Emotional load > 70% → COOLDOWN
      3. L1 confidence < 40% → CLARIFY

    Harm assessment via LLM is called separately (async) in the live pipeline.
    """
    # 1. Ambiguity gate
    if dimensions and dimensions.b_set.ambiguity > 0.30:
        return GuardrailCheck(
            result=GuardrailResult.SILENCE,
            reason=f"Ambiguity {dimensions.b_set.ambiguity:.0%} > 30%",
            nudge="I want to make sure I understand correctly. Could you tell me a bit more?",
            block_execution=True,
        )

    # 2. Emotional load cooldown
    if dimensions and dimensions.b_set.emotional_load > 0.7:
        return GuardrailCheck(
            result=GuardrailResult.COOLDOWN,
            reason=f"Emotional load {dimensions.b_set.emotional_load:.0%} > 70%",
            nudge="Let's take a moment. Would you like to review this before proceeding?",
            block_execution=True,
        )

    # 3. Low confidence gate
    if l1_draft and l1_draft.hypotheses:
        top = l1_draft.hypotheses[0]
        if top.confidence < 0.4:
            return GuardrailCheck(
                result=GuardrailResult.CLARIFY,
                reason=f"L1 confidence {top.confidence:.2f} < 0.40",
                nudge="I'm not quite sure what you'd like to do. Could you rephrase that?",
                block_execution=True,
            )

    return GuardrailCheck(
        result=GuardrailResult.PASS,
        reason="Deterministic gates passed — LLM harm check runs async",
        block_execution=False,
    )

