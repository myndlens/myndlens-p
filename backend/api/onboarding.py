"""Enhanced Onboarding API — enriched schemas + bulk auto-import.

Supports both manual entry (original wizard) and auto-import from
device permissions (contacts, calendar). Uses hybrid approach:
on-device algorithmic processing + server-side Gemini fallback.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.database import get_db
from memory.retriever import store_fact, register_entity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


# ---- Schemas ----

class OnboardingStatus(BaseModel):
    user_id: str
    completed: bool
    step: int = 0
    total_steps: int = 7
    items_stored: int = 0
    import_source: str = "manual"


class OnboardingProfile(BaseModel):
    user_id: str
    display_name: str
    preferences: Dict[str, Any] = Field(default_factory=dict)
    contacts: List[Dict[str, str]] = Field(default_factory=list)
    routines: List[str] = Field(default_factory=list)
    communication_style: str = ""
    timezone: str = "UTC"


class EnrichedContact(BaseModel):
    name: str
    relationship: str = "contact"
    role: str = ""
    email: str = ""
    phone: str = ""
    preferred_channel: str = ""
    importance: str = "medium"
    starred: bool = False
    company: str = ""
    aliases: List[str] = Field(default_factory=list)
    import_source: str = "auto"


class StructuredRoutine(BaseModel):
    title: str
    time: str = ""
    frequency: str = "daily"
    days: List[str] = Field(default_factory=list)
    duration_minutes: int = 0
    attendees: int = 0
    routine_type: str = "general"
    import_source: str = "auto"


class CalendarPattern(BaseModel):
    pattern_type: str
    description: str
    time: str = ""
    frequency: str = ""
    days: List[str] = Field(default_factory=list)
    confidence: float = 0.5


class LocationContext(BaseModel):
    city: str = ""
    region: str = ""
    country: str = ""
    timezone: str = ""
    postal_code: str = ""


class BulkImportRequest(BaseModel):
    user_id: str
    contacts: List[EnrichedContact] = Field(default_factory=list)
    routines: List[StructuredRoutine] = Field(default_factory=list)
    patterns: List[CalendarPattern] = Field(default_factory=list)
    location: Optional[LocationContext] = None
    display_name: str = ""
    communication_style: str = ""
    timezone: str = "UTC"
    import_source: str = "auto"


class ServerAnalyzeRequest(BaseModel):
    user_id: str
    contacts: List[Dict[str, Any]] = Field(default_factory=list)
    calendar_events: List[Dict[str, Any]] = Field(default_factory=list)


# ---- Endpoints ----

@router.get("/status/{user_id}", response_model=OnboardingStatus)
async def get_onboarding_status(user_id: str):
    db = get_db()
    doc = await db.onboarding.find_one({"user_id": user_id}, {"_id": 0})
    if not doc:
        return OnboardingStatus(user_id=user_id, completed=False)
    return OnboardingStatus(**{k: doc[k] for k in OnboardingStatus.model_fields if k in doc})


@router.post("/profile", response_model=OnboardingStatus)
async def save_onboarding_profile(profile: OnboardingProfile):
    """Original manual onboarding (backward compatible)."""
    db = get_db()
    items_stored = 0

    await store_fact(user_id=profile.user_id, text=f"My name is {profile.display_name}", fact_type="IDENTITY", provenance="ONBOARDING")
    items_stored += 1

    if profile.timezone:
        await store_fact(user_id=profile.user_id, text=f"My timezone is {profile.timezone}", fact_type="PREFERENCE", provenance="ONBOARDING")
        items_stored += 1

    if profile.communication_style:
        await store_fact(user_id=profile.user_id, text=f"I prefer {profile.communication_style} communication style", fact_type="PREFERENCE", provenance="ONBOARDING")
        items_stored += 1

    for key, value in profile.preferences.items():
        await store_fact(user_id=profile.user_id, text=f"Preference: {key} = {value}", fact_type="PREFERENCE", provenance="ONBOARDING")
        items_stored += 1

    for contact in profile.contacts:
        name = contact.get("name", "")
        rel = contact.get("relationship", "contact")
        if name:
            entity_id = await register_entity(
                user_id=profile.user_id, entity_type="PERSON", name=name,
                aliases=contact.get("aliases", "").split(",") if contact.get("aliases") else [],
                data={"relationship": rel}, provenance="ONBOARDING",
            )
            await store_fact(user_id=profile.user_id, text=f"{name} is my {rel}", fact_type="FACT", provenance="ONBOARDING", related_to=entity_id)
            items_stored += 2

    for routine in profile.routines:
        if routine.strip():
            await store_fact(user_id=profile.user_id, text=f"Daily routine: {routine}", fact_type="ROUTINE", provenance="ONBOARDING")
            items_stored += 1

    status = {
        "user_id": profile.user_id, "completed": True, "step": 7, "total_steps": 7,
        "items_stored": items_stored, "import_source": "manual", "completed_at": datetime.now(timezone.utc),
    }
    await db.onboarding.update_one({"user_id": profile.user_id}, {"$set": status}, upsert=True)
    logger.info("Onboarding (manual): user=%s items=%d", profile.user_id, items_stored)
    return OnboardingStatus(**status)


@router.post("/import", response_model=OnboardingStatus)
async def bulk_import(req: BulkImportRequest):
    """Bulk import from auto-import (enriched contacts, structured routines, patterns)."""
    db = get_db()
    items_stored = 0

    # Identity
    if req.display_name:
        await store_fact(user_id=req.user_id, text=f"My name is {req.display_name}", fact_type="IDENTITY", provenance="ONBOARDING_AUTO")
        items_stored += 1

    if req.timezone:
        await store_fact(user_id=req.user_id, text=f"My timezone is {req.timezone}", fact_type="PREFERENCE", provenance="ONBOARDING_AUTO")
        items_stored += 1

    if req.communication_style:
        await store_fact(user_id=req.user_id, text=f"I prefer {req.communication_style} communication style", fact_type="PREFERENCE", provenance="ONBOARDING_AUTO")
        items_stored += 1

    # Enriched contacts
    for c in req.contacts:
        if not c.name:
            continue
        entity_data = {"relationship": c.relationship, "role": c.role, "email": c.email, "phone": c.phone,
                       "preferred_channel": c.preferred_channel, "importance": c.importance,
                       "starred": c.starred, "company": c.company, "import_source": c.import_source}
        entity_data = {k: v for k, v in entity_data.items() if v}

        entity_id = await register_entity(
            user_id=req.user_id, entity_type="PERSON", name=c.name,
            aliases=c.aliases, data=entity_data, provenance="ONBOARDING_AUTO",
        )

        desc_parts = [f"{c.name} is my {c.relationship}"]
        if c.role:
            desc_parts.append(f"role: {c.role}")
        if c.company:
            desc_parts.append(f"at {c.company}")
        if c.preferred_channel:
            desc_parts.append(f"prefers {c.preferred_channel}")

        await store_fact(
            user_id=req.user_id, text=", ".join(desc_parts),
            fact_type="FACT", provenance="ONBOARDING_AUTO", related_to=entity_id,
            metadata={"email": c.email, "phone": c.phone, "importance": c.importance},
        )
        items_stored += 2

    # Structured routines
    for r in req.routines:
        if not r.title:
            continue
        meta = {"time": r.time, "frequency": r.frequency,
                "duration_minutes": r.duration_minutes, "attendees": r.attendees,
                "routine_type": r.routine_type, "import_source": r.import_source}
        # Only include days if non-empty (ChromaDB rejects empty lists)
        if r.days:
            meta["days"] = r.days
        meta = {k: v for k, v in meta.items() if v}

        text_parts = [r.title]
        if r.time:
            text_parts.append(f"at {r.time}")
        if r.frequency != "daily":
            text_parts.append(f"({r.frequency})")
        if r.days:
            text_parts.append(f"on {', '.join(r.days)}")

        await store_fact(
            user_id=req.user_id, text=" ".join(text_parts),
            fact_type="ROUTINE", provenance="ONBOARDING_AUTO", metadata=meta,
        )
        items_stored += 1

    # Calendar patterns
    for p in req.patterns:
        pattern_meta = {"pattern_type": p.pattern_type, "time": p.time, "frequency": p.frequency,
                        "confidence": p.confidence}
        # Only include days if non-empty (ChromaDB rejects empty lists)
        if p.days:
            pattern_meta["days"] = p.days
        pattern_meta = {k: v for k, v in pattern_meta.items() if v or isinstance(v, (int, float))}
        
        await store_fact(
            user_id=req.user_id, text=f"Pattern: {p.description}",
            fact_type="FACT", provenance="ONBOARDING_AUTO",
            metadata=pattern_meta,
        )
        items_stored += 1

    # Location context
    if req.location and req.location.city:
        loc = req.location
        await store_fact(
            user_id=req.user_id,
            text=f"I am based in {loc.city}, {loc.region}, {loc.country}",
            fact_type="PREFERENCE", provenance="ONBOARDING_AUTO",
            metadata={"city": loc.city, "region": loc.region, "country": loc.country,
                       "timezone": loc.timezone, "postal_code": loc.postal_code},
        )
        items_stored += 1

    status = {
        "user_id": req.user_id, "completed": True, "step": 7, "total_steps": 7,
        "items_stored": items_stored, "import_source": req.import_source,
        "completed_at": datetime.now(timezone.utc),
    }
    await db.onboarding.update_one({"user_id": req.user_id}, {"$set": status}, upsert=True)

    logger.info("Onboarding (auto-import): user=%s items=%d contacts=%d routines=%d patterns=%d",
                req.user_id, items_stored, len(req.contacts), len(req.routines), len(req.patterns))
    return OnboardingStatus(**status)


@router.post("/analyze")
async def server_analyze(req: ServerAnalyzeRequest):
    """Server-side Gemini analysis fallback for complex relationship inference."""
    from config.settings import get_settings
    from config.feature_flags import is_mock_llm
    settings = get_settings()

    analyzed_contacts = []
    for c in req.contacts:
        name = c.get("name", "")
        analysis = {
            "name": name,
            "relationship": _infer_relationship(c),
            "role": c.get("jobTitle", c.get("role", "")),
            "importance": _score_importance(c),
            "preferred_channel": _infer_channel(c),
            "company": c.get("company", ""),
        }
        analyzed_contacts.append(analysis)

    extracted_patterns = []
    for event in req.calendar_events:
        pattern = _extract_event_pattern(event)
        if pattern:
            extracted_patterns.append(pattern)

    return {
        "contacts": analyzed_contacts,
        "patterns": extracted_patterns,
        "analysis_source": "server_heuristic",
    }


@router.post("/skip/{user_id}", response_model=OnboardingStatus)
async def skip_onboarding(user_id: str):
    db = get_db()
    status = {
        "user_id": user_id, "completed": True, "step": 0, "total_steps": 7,
        "items_stored": 0, "skipped": True, "import_source": "skipped",
        "completed_at": datetime.now(timezone.utc),
    }
    await db.onboarding.update_one({"user_id": user_id}, {"$set": status}, upsert=True)
    return OnboardingStatus(**status)


# ---- Smart Algorithms (server-side heuristics) ----

def _infer_relationship(contact: Dict[str, Any]) -> str:
    email = (contact.get("email") or contact.get("emails", [{}])[0].get("email", "") if isinstance(contact.get("emails"), list) else contact.get("email", "")).lower()
    company = (contact.get("company") or "").lower()
    job = (contact.get("jobTitle") or "").lower()

    if any(k in job for k in ["manager", "director", "vp", "chief", "head"]):
        return "work"
    if company:
        return "work"
    if any(d in email for d in ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com"]):
        return "personal"
    if email and "." in email.split("@")[-1]:
        return "work"
    return "other"


def _score_importance(contact: Dict[str, Any]) -> str:
    score = 0
    if contact.get("starred"):
        score += 3
    if contact.get("email") or (isinstance(contact.get("emails"), list) and contact["emails"]):
        score += 1
    if contact.get("phone") or (isinstance(contact.get("phoneNumbers"), list) and contact["phoneNumbers"]):
        score += 1
    if contact.get("email") and contact.get("phone"):
        score += 1
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def _infer_channel(contact: Dict[str, Any]) -> str:
    has_phone = bool(contact.get("phone") or (isinstance(contact.get("phoneNumbers"), list) and contact["phoneNumbers"]))
    has_email = bool(contact.get("email") or (isinstance(contact.get("emails"), list) and contact["emails"]))
    if has_phone and has_email:
        return "whatsapp"
    if has_phone:
        return "call"
    if has_email:
        return "email"
    return ""


def _extract_event_pattern(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title = event.get("title", "")
    if not title:
        return None
    recurrence = event.get("recurrenceRule") or event.get("recurrence_rule")
    start = event.get("startDate") or event.get("start", "")

    time_str = ""
    if start and "T" in str(start):
        time_str = str(start).split("T")[1][:5]

    if recurrence:
        freq = recurrence.get("frequency", "weekly") if isinstance(recurrence, dict) else "weekly"
        return {
            "pattern_type": "recurring_event",
            "description": f"Recurring: {title}",
            "time": time_str,
            "frequency": freq,
            "confidence": 0.9,
        }

    return {
        "pattern_type": "single_event",
        "description": title,
        "time": time_str,
        "frequency": "once",
        "confidence": 0.5,
    }
