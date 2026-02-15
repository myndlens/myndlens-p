"""Dedicated Dimension Extraction — uses DIMENSIONS_EXTRACT purpose.

Instead of piggybacking on L1 suggestions, performs a dedicated LLM call
to extract A-set dimensions (who, what, when, where, how) from transcript
enriched with Digital Self context.
"""
import json
import logging
import time
from typing import Any, Dict, Optional

from config.settings import get_settings
from config.feature_flags import is_mock_llm
from prompting.orchestrator import PromptOrchestrator
from prompting.types import PromptContext, PromptPurpose, PromptMode
from prompting.storage.mongo import save_prompt_snapshot

logger = logging.getLogger(__name__)


async def extract_dimensions_via_llm(
    session_id: str,
    user_id: str,
    transcript: str,
    l1_suggestions: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Dedicated dimension extraction using DIMENSIONS_EXTRACT purpose."""
    settings = get_settings()
    start = time.monotonic()

    if is_mock_llm() or not settings.EMERGENT_LLM_KEY:
        return _mock_extract(transcript, l1_suggestions)

    try:
        # Recall memories for entity resolution
        from memory.retriever import recall
        memory_snippets = await recall(user_id=user_id, query_text=transcript, n_results=3)

        orchestrator = PromptOrchestrator()
        ctx = PromptContext(
            purpose=PromptPurpose.DIMENSIONS_EXTRACT,
            mode=PromptMode.INTERACTIVE,
            session_id=session_id,
            user_id=user_id,
            transcript=transcript,
            memory_snippets=memory_snippets if memory_snippets else None,
            task_description=(
                "Extract structured dimensions from the user's transcript. "
                "Use the user's memories to resolve entity references. "
                "Output JSON with A-set fields: "
                "{who: string, what: string, when: string, where: string, how: string, "
                "confidence: float, resolved_entities: [{ref: string, canonical: string}]}"
            ),
        )
        artifact, report = orchestrator.build(ctx)
        await save_prompt_snapshot(report)

        from prompting.llm_gateway import call_llm
        response = await call_llm(
            artifact=artifact,
            call_site_id="DIMENSION_EXTRACTOR",
            model_provider="gemini",
            model_name="gemini-2.0-flash",
            session_id=f"dim-{session_id}",
        )

        latency_ms = (time.monotonic() - start) * 1000
        dimensions = _parse_dimensions(response, l1_suggestions)
        dimensions["_meta"] = {
            "source": "dedicated_llm",
            "latency_ms": round(latency_ms, 1),
            "prompt_id": artifact.prompt_id,
            "memory_used": len(memory_snippets) if memory_snippets else 0,
        }

        logger.info(
            "Dimension extraction: session=%s completeness=%.0f%% latency=%.0fms",
            session_id, _completeness(dimensions) * 100, latency_ms,
        )
        return dimensions

    except Exception as e:
        logger.error("Dimension extraction failed: %s", str(e))
        return _mock_extract(transcript, l1_suggestions)


def _parse_dimensions(response: str, fallback: Optional[Dict] = None) -> Dict[str, Any]:
    try:
        text = response.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        data = json.loads(text)
        return {
            "who": data.get("who", ""),
            "what": data.get("what", ""),
            "when": data.get("when", ""),
            "where": data.get("where", ""),
            "how": data.get("how", ""),
            "confidence": float(data.get("confidence", 0.5)),
            "resolved_entities": data.get("resolved_entities", []),
        }
    except (json.JSONDecodeError, KeyError, TypeError):
        logger.warning("Dimension parse failed, using L1 fallback")
        return fallback or {"who": "", "what": "", "when": "", "where": "", "how": ""}


def _mock_extract(transcript: str, l1_suggestions: Optional[Dict] = None) -> Dict[str, Any]:
    base = l1_suggestions or {}
    return {
        "who": base.get("who", ""),
        "what": base.get("what", transcript[:50] if transcript else ""),
        "when": base.get("when", ""),
        "where": base.get("where", ""),
        "how": base.get("how", ""),
        "confidence": 0.5,
        "resolved_entities": [],
        "_meta": {"source": "mock"},
    }


def _completeness(dims: Dict[str, Any]) -> float:
    fields = ["who", "what", "when", "where", "how"]
    filled = sum(1 for f in fields if dims.get(f))
    return filled / len(fields)
