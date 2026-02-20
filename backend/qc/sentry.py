"""QC Sentry — Adversarial quality control.

Spec §5.3: Runs AFTER L2 and BEFORE MIO signing.
Three adversarial passes:
  1. Persona Drift: Compare draft tone vs user communication profile
  2. Capability Leak: Ensure minimum necessary OpenClaw skill only
  3. Harm Projection: Map negative interpretation to transcript spans

Grounding Rule: If QC cannot cite transcript spans, it CANNOT block.

Uses PromptOrchestrator with VERIFY purpose via LLM Gateway.
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
class QCPass:
    """Result of a single QC adversarial pass."""
    pass_name: str  # persona_drift | capability_leak | harm_projection
    passed: bool
    severity: str = "none"  # none | nudge | block
    reason: str = ""
    cited_spans: List[Dict[str, Any]] = field(default_factory=list)  # Required for blocking


@dataclass
class QCVerdict:
    """Combined QC result."""
    verdict_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    passes: List[QCPass] = field(default_factory=list)
    overall_pass: bool = True
    block_reason: Optional[str] = None
    latency_ms: float = 0.0
    prompt_id: str = ""
    is_mock: bool = False


async def run_qc_sentry(
    session_id: str,
    user_id: str,
    transcript: str,
    intent: str,
    intent_summary: str,
    persona_summary: str = "",
    skill_risk: str = "low",
    skill_names: Optional[List[str]] = None,
) -> QCVerdict:
    """Adversarial QC Sentry -- 3 passes with full context.

    skill_risk and skill_names come from skills matching (which now runs before QC)
    so capability_leak can check whether granted tool risk matches the intent.
    """
    settings = get_settings()
    start = time.monotonic()

    if is_mock_llm() or not settings.EMERGENT_LLM_KEY:
        return _mock_qc(start)

    try:
        orchestrator = PromptOrchestrator()
        persona_context = (
            f"\nUser's Digital Self (persona baseline): {persona_summary}"
            if persona_summary else ""
        )
        skills_context = (
            f"\nSkills to be granted: {', '.join(skill_names or [])} (aggregate risk: {skill_risk})"
        )
        ctx = PromptContext(
            purpose=PromptPurpose.VERIFY,
            mode=PromptMode.INTERACTIVE,
            session_id=session_id,
            user_id=user_id,
            transcript=transcript,
            task_description=(
                f"QC Adversarial Review: intent='{intent_summary}' action={action_class}.{persona_context}{skills_context}\n"
                f"Run 3 adversarial checks:\n"
                f"1. persona_drift: Does this action match the user's known communication style above? "
                f"Flag if the request contradicts their established patterns.\n"
                f"2. capability_leak: Does granting these skills ({', '.join(skill_names or ['unknown'])}) "
                f"exceed the minimum capability needed? Risk={skill_risk} -- flag if high-risk skills are granted for a simple request.\n"
                f"3. harm_projection: Could this action cause harm? Cite SPECIFIC transcript spans.\n\n"
                f"Output: {{\"passes\": [{{\"pass_name\": \"...\", \"passed\": true/false, "
                f"\"severity\": \"none|nudge|block\", \"reason\": \"...\", "
                f"\"cited_spans\": [{{\"text\": \"...\", \"start\": 0, \"end\": 10}}]}}, ...]}}"
            ),
        )
        artifact, report = orchestrator.build(ctx)
        await save_prompt_snapshot(report)

        response = await call_llm(
            artifact=artifact,
            call_site_id="QC_SENTRY",
            model_provider="gemini",
            model_name="gemini-2.0-flash",
            session_id=f"qc-{session_id}",
        )

        latency_ms = (time.monotonic() - start) * 1000
        verdict = _parse_qc_response(response, latency_ms, artifact.prompt_id)

        logger.info(
            "QC Sentry: session=%s passes=%d overall=%s latency=%.0fms",
            session_id, len(verdict.passes), verdict.overall_pass, latency_ms,
        )
        return verdict

    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        logger.error("QC Sentry failed: session=%s error=%s", session_id, str(e))
        # Fail-safe: block on any unhandled exception — never silently pass
        return QCVerdict(
            passes=[QCPass(
                pass_name="qc_system",
                passed=False,
                severity="block",
                reason=f"QC system error: {type(e).__name__}. Blocking for safety.",
            )],
            overall_pass=False,
            block_reason=f"QC system error: {type(e).__name__}",
            latency_ms=latency_ms,
        )


def _parse_qc_response(response: str, latency_ms: float, prompt_id: str) -> QCVerdict:
    """Parse QC LLM response."""
    passes = []
    try:
        text = response.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        data = json.loads(text)
        for p in data.get("passes", []):
            qc_pass = QCPass(
                pass_name=p.get("pass_name", "unknown"),
                passed=p.get("passed", True),
                severity=p.get("severity", "none"),
                reason=p.get("reason", ""),
                cited_spans=p.get("cited_spans", []),
            )

            # Grounding rule: if blocking but no cited spans, downgrade to nudge
            if not qc_pass.passed and qc_pass.severity == "block" and not qc_pass.cited_spans:
                qc_pass.severity = "nudge"
                qc_pass.reason += " [downgraded: no span evidence]"
                logger.warning("QC grounding rule: %s downgraded (no spans)", qc_pass.pass_name)

            passes.append(qc_pass)

    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("QC parse failed: %s — blocking by default (fail-safe)", str(e))
        # Fail-safe: if QC cannot assess, block execution.
        # Passing on parse failure would allow harmful mandates through when Gemini
        # refuses to answer (e.g., safety filter triggered).
        passes = [QCPass(
            pass_name="qc_verification",
            passed=False,
            severity="block",
            reason=f"QC verification failed: LLM response could not be parsed. Cannot proceed. ({type(e).__name__})",
        )]

    overall = all(p.passed or p.severity != "block" for p in passes)
    block_reason = None
    if not overall:
        blocking = [p for p in passes if not p.passed and p.severity == "block"]
        if blocking:
            block_reason = blocking[0].reason

    return QCVerdict(
        passes=passes,
        overall_pass=overall,
        block_reason=block_reason,
        latency_ms=latency_ms,
        prompt_id=prompt_id,
    )


def _mock_qc(start_time: float) -> QCVerdict:
    """Mock QC for testing."""
    return QCVerdict(
        passes=[
            QCPass(pass_name="persona_drift", passed=True, severity="none", reason="Mock: no drift"),
            QCPass(pass_name="capability_leak", passed=True, severity="none", reason="Mock: minimal capability"),
            QCPass(pass_name="harm_projection", passed=True, severity="none", reason="Mock: no harm"),
        ],
        overall_pass=True,
        latency_ms=(time.monotonic() - start_time) * 1000,
        is_mock=True,
    )
