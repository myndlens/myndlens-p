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
        "Extract EVERY dimension needed to EXECUTE each action. Nothing can be left ambiguous.\n"
        "If a city has multiple airports (London: Heathrow/Gatwick/Stansted/Luton/City), "
        "the specific airport MUST be determined.\n\n"
        "DIMENSION SCHEMAS PER ACTION TYPE:\n\n"
        "  Flight:\n"
        "    dep_city, dep_airport (specific airport code e.g. LHR/LGW/JFK/SYD), "
        "dep_date, dep_time_pref (morning 6-10/midday 10-14/afternoon 14-18/evening 18-22/red-eye 22-6),\n"
        "    arr_city, arr_airport (specific code), "
        "ret_date, ret_time_pref,\n"
        "    airline_pref, class (economy/premium_economy/business/first), "
        "seat_pref (window/aisle/middle/any), meal_pref (standard/vegetarian/vegan/halal/kosher/none),\n"
        "    baggage (carry-on only/1 checked/2 checked), loyalty_program, loyalty_number,\n"
        "    travelers_count, companion_names, direct_only (yes/no)\n\n"
        "  Hotel:\n"
        "    city, area_pref (near airport/city center/near venue/specific area), "
        "checkin_date, checkout_date, nights,\n"
        "    brand_pref, hotel_name (specific if known), star_rating (3/4/5),\n"
        "    room_type (single/double/twin/suite/family), bed_type (king/queen/twin),\n"
        "    amenities (wifi/gym/pool/parking/breakfast/lounge), "
        "loyalty_program, loyalty_number,\n"
        "    rooms_count, guests_per_room, breakfast_included, late_checkout\n\n"
        "  Car Rental:\n"
        "    pickup_city, pickup_location (airport/hotel/city office), pickup_date, pickup_time,\n"
        "    dropoff_city, dropoff_location, dropoff_date, dropoff_time,\n"
        "    company_pref, car_type (compact/sedan/SUV/luxury/minivan), "
        "transmission (automatic/manual),\n"
        "    insurance (basic/full/none), gps (yes/no), child_seat (yes/no), additional_driver\n\n"
        "  Meeting:\n"
        "    date, time, duration, timezone,\n"
        "    attendees [{name, email, role}], organizer,\n"
        "    location (in-person address / video call), video_platform (zoom/teams/meet),\n"
        "    agenda, pre_read_docs, recurring (one-time/weekly/biweekly/monthly)\n\n"
        "  Restaurant:\n"
        "    date, time, party_size, cuisine_type, restaurant_name,\n"
        "    area_pref, price_range (budget/mid/fine-dining), "
        "dietary_restrictions, reservation_name, special_occasion\n\n"
        "  Payment:\n"
        "    amount, currency, from_account, to_recipient, method (bank/card/crypto),\n"
        "    reference, due_date, recurring\n\n"
        "  Communication:\n"
        "    recipients [{name, contact_method, address}], "
        "channel (email/whatsapp/slack/sms/call),\n"
        "    subject, body_summary, attachments, urgency (immediate/today/this_week),\n"
        "    tone (formal/casual), reply_to\n\n"
        "  Document:\n"
        "    doc_type (report/proposal/letter/presentation/blog), title, audience,\n"
        "    format (pdf/docx/slides/html), length (short/medium/detailed),\n"
        "    deadline, reviewer, template\n\n"
        "  Hiring:\n"
        "    role_title, seniority (junior/mid/senior/lead/principal), count,\n"
        "    salary_range, location (remote/hybrid/office), department,\n"
        "    posting_channels, screener, interview_panel, start_date, skills_required\n\n"
        "RULES:\n"
        "- Use Digital Self to fill from preferences and past patterns\n"
        "- If user is in London and says 'fly to Sydney', dep_city=London but dep_airport=MISSING (which one?)\n"
        "- Mark source: 'stated' | 'digital_self' | 'inferred' | 'missing'\n"
        "- EVERY dimension must have a value or be explicitly 'missing'\n"
        "- A mandate with ANY 'missing' dimension is NOT executable\n\n"
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


async def extract_dimensions_via_llm(
    session_id: str,
    user_id: str,
    transcript: str,
    l1_suggestions: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Diagnostic wrapper: extract dimensions from transcript without requiring intent.

    Used by the /api/dimensions/extract diagnostic endpoint.
    Infers intent from the transcript itself before extracting dimensions.
    """
    return await extract_mandate_dimensions(
        session_id=session_id,
        user_id=user_id,
        transcript=transcript,
        intent="",  # LLM infers from transcript
        sub_intents=[],
        l1_dimensions=l1_suggestions,
    )
