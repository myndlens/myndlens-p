"""Mandate-Ready Dimension Extraction — Intent drives the dimensions.

A Travel Concierge mandate needs: destination, dates, hotel, transport, companions
A Hiring Pipeline mandate needs: role, count, budget, timeline, team
An Event Planning mandate needs: event type, venue, guests, catering, date

The intent tells us WHAT dimensions to extract.
The Digital Self tells us HOW to resolve them.
Together they form the Mandate.
"""
import json
import logging
import time
from typing import Any, Dict, List, Optional

from config.settings import get_settings
from config.feature_flags import is_mock_llm
from prompting.orchestrator import PromptOrchestrator
from prompting.types import PromptContext, PromptPurpose, PromptMode
from prompting.storage.mongo import save_prompt_snapshot

logger = logging.getLogger(__name__)


async def extract_mandate_dimensions(
    session_id: str,
    user_id: str,
    transcript: str,
    intent: str,
    sub_intents: List[str],
    l1_dimensions: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Extract mandate-ready dimensions driven by the intent.

    The intent determines WHICH dimensions matter.
    The Digital Self resolves ambiguous references.
    The output is a complete mandate dimension set.
    """
    settings = get_settings()
    start = time.monotonic()

    if is_mock_llm() or not settings.EMERGENT_LLM_KEY:
        return _build_mock(transcript, intent, l1_dimensions)

    from memory.retriever import recall
    memory_snippets = await recall(user_id=user_id, query_text=transcript, n_results=5)

    task = (
        f"The user's intent is: {intent}\n"
        f"Sub-intents: {', '.join(sub_intents) if sub_intents else 'none identified'}\n"
        f"User said: \"{transcript}\"\n\n"
        "Extract ALL dimensions needed to create a complete, executable mandate.\n"
        "Use the Digital Self memories to resolve every person, place, and preference.\n\n"
        "Output JSON with:\n"
        "{\n"
        "  \"intent\": \"<the intent name>\",\n"
        "  \"mandate_summary\": \"<one sentence: what will be executed>\",\n"
        "  \"people\": [{\"name\": str, \"role_in_mandate\": str, \"contact\": str}],\n"
        "  \"actions\": [{\"action\": str, \"details\": str, \"priority\": \"high|medium|low\"}],\n"
        "  \"timing\": {\"start\": str, \"end\": str, \"deadline\": str, \"duration\": str},\n"
        "  \"location\": {\"primary\": str, \"details\": str},\n"
        "  \"preferences\": [{\"category\": str, \"value\": str, \"source\": \"Digital Self|stated|inferred\"}],\n"
        "  \"constraints\": [str],\n"
        "  \"missing\": [str],\n"
        "  \"confidence\": 0-1\n"
        "}\n\n"
        "RULES:\n"
        "- Resolve names to full identities from Digital Self (e.g., 'Jacob' → 'Jacob Martinez, CMO')\n"
        "- Include contact info (email, phone) from Digital Self when available\n"
        "- Include preferences from Digital Self (hotel brand, flight class, etc.)\n"
        "- List what's MISSING — dimensions the user didn't specify\n"
        "- Each action maps to a sub-intent that can be executed\n"
        "- Be specific: not 'book hotel' but 'book Hilton Sydney, 10 nights from [date]'"
    )

    orchestrator = PromptOrchestrator()
    ctx = PromptContext(
        purpose=PromptPurpose.DIMENSIONS_EXTRACT,
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
        call_site_id="DIMENSION_EXTRACTOR",
        model_provider="gemini",
        model_name="gemini-2.0-flash",
        session_id=f"mandate-dim-{session_id}",
    )

    latency_ms = (time.monotonic() - start) * 1000
    mandate = _parse_mandate(response, intent)
    mandate["_meta"] = {
        "latency_ms": round(latency_ms, 1),
        "prompt_id": artifact.prompt_id,
        "memory_used": len(memory_snippets) if memory_snippets else 0,
    }

    logger.info(
        "[MandateDim] session=%s intent=%s people=%d actions=%d missing=%d conf=%.2f %.0fms",
        session_id, intent, len(mandate.get("people", [])),
        len(mandate.get("actions", [])), len(mandate.get("missing", [])),
        mandate.get("confidence", 0), latency_ms,
    )
    return mandate


def _parse_mandate(response: str, intent: str) -> Dict[str, Any]:
    try:
        text = response.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        data = json.loads(text)
        data.setdefault("intent", intent)
        return data
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("[MandateDim] Parse failed: %s", e)
        return {"intent": intent, "mandate_summary": "", "people": [], "actions": [],
                "timing": {}, "location": {}, "preferences": [], "constraints": [],
                "missing": ["parse_error"], "confidence": 0.0}


def _build_mock(transcript: str, intent: str, l1_dims: Optional[Dict] = None) -> Dict[str, Any]:
    d = l1_dims or {}
    return {"intent": intent, "mandate_summary": transcript[:80],
            "people": [], "actions": [], "timing": {},
            "location": {"primary": d.get("where", "")},
            "preferences": [], "constraints": [],
            "missing": ["mock_mode"], "confidence": 0.3,
            "_meta": {"source": "mock"}}
