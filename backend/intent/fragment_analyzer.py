"""Lightweight Fragment Processor — single LLM call per spoken fragment.

Extracts sub-intents and basic dimensions from a sentence-level fragment.
Runs during the Capture Cycle (Path A) — NOT the full mandate pipeline.

Cost: 1 Gemini Flash call per fragment (~50-100 tokens output).
Latency target: < 500ms.
"""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config.settings import get_settings
from config.feature_flags import is_mock_llm

logger = logging.getLogger(__name__)


@dataclass
class FragmentAnalysis:
    """Result of analyzing a single spoken fragment."""
    sub_intents: List[str] = field(default_factory=list)
    dimensions_found: Dict[str, str] = field(default_factory=dict)  # dim_name → value
    dimensions_missing: List[str] = field(default_factory=list)     # dim_names still unknown
    confidence: float = 0.0
    latency_ms: float = 0.0


async def analyze_fragment(
    session_id: str,
    user_id: str,
    fragment_text: str,
    accumulated_context: str = "",
    ds_summary: str = "",
) -> FragmentAnalysis:
    """Analyze a single fragment — extract sub-intents + dimensions.

    Single Gemini Flash call with a tiny prompt. Designed for speed.
    """
    settings = get_settings()
    start = time.monotonic()

    if is_mock_llm() or not settings.EMERGENT_LLM_KEY:
        return FragmentAnalysis(
            sub_intents=[fragment_text[:40]],
            confidence=0.3,
            latency_ms=(time.monotonic() - start) * 1000,
        )

    task = (
        "Extract sub-intents and dimensions from this spoken fragment.\n"
        f"Fragment: \"{fragment_text[:500]}\"\n"
    )
    if accumulated_context:
        task += f"Previous context: \"{accumulated_context}\"\n"
    if ds_summary:
        task += f"Digital Self: {ds_summary}\n"

    task += (
        "\nOutput JSON only:\n"
        "{\"sub_intents\": [str], \"dimensions\": {\"who\": str, \"what\": str, "
        "\"when\": str, \"where\": str, \"how\": str}, \"confidence\": 0-1}\n"
        "Omit dimensions that aren't mentioned. Be concise."
    )

    try:
        from prompting.llm_gateway import call_llm
        from prompting.orchestrator import PromptOrchestrator, PromptArtifact
        from prompting.types import PromptContext, PromptPurpose, PromptMode

        orchestrator = PromptOrchestrator()
        ctx = PromptContext(
            purpose=PromptPurpose.THOUGHT_TO_INTENT,
            mode=PromptMode.INTERACTIVE,
            session_id=session_id,
            user_id=user_id,
            transcript=fragment_text,
            task_description=task,
        )
        artifact, _ = orchestrator.build(ctx)

        response = await call_llm(
            artifact=artifact,
            call_site_id="FRAGMENT_ANALYZER",
            model_provider="gemini",
            model_name="gemini-2.0-flash",
            session_id=f"frag-{session_id}",
        )

        latency_ms = (time.monotonic() - start) * 1000
        return _parse_fragment_response(response, latency_ms)

    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        logger.error("[FragmentAnalyzer] failed: session=%s error=%s %.0fms",
                     session_id, str(e), latency_ms)
        return FragmentAnalysis(
            sub_intents=[fragment_text[:40]],
            confidence=0.3,
            latency_ms=latency_ms,
        )


def _parse_fragment_response(response: str, latency_ms: float) -> FragmentAnalysis:
    """Parse LLM response into FragmentAnalysis."""
    try:
        text = response.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        data = json.loads(text)

        dims_found = {}
        dims_missing = []
        raw_dims = data.get("dimensions", {})
        for k, v in raw_dims.items():
            if v and str(v).lower() not in ("missing", "unknown", "none", ""):
                dims_found[k] = str(v)
            else:
                dims_missing.append(k)

        return FragmentAnalysis(
            sub_intents=data.get("sub_intents", []),
            dimensions_found=dims_found,
            dimensions_missing=dims_missing,
            confidence=float(data.get("confidence", 0.5)),
            latency_ms=latency_ms,
        )
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("[FragmentAnalyzer] parse failed: %s", e)
        return FragmentAnalysis(confidence=0.3, latency_ms=latency_ms)
