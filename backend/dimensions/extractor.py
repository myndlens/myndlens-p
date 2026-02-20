"""Mandate-Ready Dimension Extraction — Execution-level granularity.

Each sub-intent has a SPECIFIC set of dimensions needed for execution.
  Flight: dep_date, ret_date, time_pref, airline, class, seat, meals
  Hotel: checkin, checkout, brand, room_type, amenities
  Car: pickup, dropoff, company, car_type
  Meeting: date, time, attendees, location, agenda
  Restaurant: date, time, party_size, cuisine, restaurant_name

The Digital Self fills preferences. The transcript fills stated values.
What's left = MISSING = micro-question targets.
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
    """Extract execution-ready dimensions for each sub-intent.

    Intent drives WHAT dimensions to extract.
    Digital Self fills preferences and patterns.
    MISSING dimensions become micro-question targets.
    """
    settings = get_settings()
    start = time.monotonic()

    if is_mock_llm() or not settings.EMERGENT_LLM_KEY:
        return _build_mock(transcript, intent, l1_dimensions)

    from memory.retriever import recall
    memory_snippets = await recall(user_id=user_id, query_text=transcript, n_results=5)

    task = (
        f"Intent: {intent}\n"
        f"Sub-intents: {', '.join(sub_intents) if sub_intents else 'to be determined'}\n"
        f"User said: \"{transcript}\"\n\n"
        "Extract EXECUTION-READY dimensions for each sub-intent.\n"
        "Each sub-intent becomes an ACTION with granular dimensions needed to execute it.\n\n"
        "For EACH action, extract every specific dimension required:\n"
        "  Flight: dep_date, ret_date, dep_time_pref (morning/afternoon/evening/red-eye), "
        "airline_pref, class (economy/premium_economy/business/first), seat_pref (window/aisle/any), "
        "meal_pref, baggage, loyalty_number\n"
        "  Hotel: checkin_date, checkout_date, nights, brand_pref, room_type (single/double/suite), "
        "amenities, loyalty_number, breakfast_included\n"
        "  Car Rental: pickup_date, pickup_location, dropoff_date, dropoff_location, "
        "company_pref, car_type (compact/sedan/SUV/luxury), insurance\n"
        "  Meeting: date, time, duration, attendees (names+contacts), location, agenda, "
        "video_link, recurring\n"
        "  Restaurant: date, time, party_size, cuisine, restaurant_name, special_requests\n"
        "  Payment: amount, currency, from_account, to_account, method, reference\n"
        "  Communication: recipients (name+contact), channel (email/whatsapp/slack), subject, body_summary\n"
        "  Document: doc_type, title, audience, format, deadline\n"
        "  Task: description, assignee, due_date, priority, project\n\n"
        "Use Digital Self memories to FILL dimensions from user preferences and past patterns.\n"
        "Mark each dimension's source: 'stated' (user said it), 'digital_self' (from memory), "
        "'inferred' (reasonable default), 'missing' (user must provide).\n\n"
        "Output JSON:\n"
        "{\n"
        "  \"intent\": str,\n"
        "  \"mandate_summary\": str,\n"
        "  \"actions\": [{\n"
        "    \"action\": str,\n"
        "    \"priority\": \"high|medium|low\",\n"
        "    \"dimensions\": {\"<dim_name>\": {\"value\": str, \"source\": \"stated|digital_self|inferred|missing\"}},\n"
        "  }],\n"
        "  \"people\": [{\"name\": str, \"role\": str, \"contact\": str, \"source\": str}],\n"
        "  \"constraints\": [str],\n"
        "  \"missing_critical\": [str],\n"
        "  \"confidence\": 0-1\n"
        "}"
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

    # Count dimension stats
    total_dims = 0
    filled_dims = 0
    missing_dims = 0
    for action in mandate.get("actions", []):
        for dim_name, dim_val in action.get("dimensions", {}).items():
            total_dims += 1
            src = dim_val.get("source", "") if isinstance(dim_val, dict) else ""
            if src == "missing":
                missing_dims += 1
            else:
                filled_dims += 1

    logger.info(
        "[MandateDim] session=%s intent=%s actions=%d dims=%d/%d filled missing=%d %.0fms",
        session_id, intent, len(mandate.get("actions", [])),
        filled_dims, total_dims, missing_dims, latency_ms,
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
        return {"intent": intent, "mandate_summary": "", "actions": [],
                "people": [], "constraints": [], "missing_critical": ["parse_error"],
                "confidence": 0.0}


def _build_mock(transcript: str, intent: str, l1_dims: Optional[Dict] = None) -> Dict[str, Any]:
    return {"intent": intent, "mandate_summary": transcript[:80],
            "actions": [], "people": [], "constraints": [],
            "missing_critical": ["mock_mode"], "confidence": 0.3,
            "_meta": {"source": "mock"}}
