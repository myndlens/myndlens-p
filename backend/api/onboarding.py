"""Onboarding API — populates Digital Self for new users.

Provides a wizard flow for new users to share preferences, contacts,
and basic info that seeds their Digital Self memory.
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


class OnboardingProfile(BaseModel):
    user_id: str
    display_name: str
    preferences: Dict[str, Any] = Field(default_factory=dict)
    contacts: List[Dict[str, str]] = Field(default_factory=list)
    routines: List[str] = Field(default_factory=list)
    communication_style: str = ""
    timezone: str = "UTC"


class OnboardingStatus(BaseModel):
    user_id: str
    completed: bool
    step: int = 0
    total_steps: int = 5
    items_stored: int = 0


@router.get("/status/{user_id}", response_model=OnboardingStatus)
async def get_onboarding_status(user_id: str):
    db = get_db()
    doc = await db.onboarding.find_one({"user_id": user_id}, {"_id": 0})
    if not doc:
        return OnboardingStatus(user_id=user_id, completed=False)
    return OnboardingStatus(**doc)


@router.post("/profile", response_model=OnboardingStatus)
async def save_onboarding_profile(profile: OnboardingProfile):
    db = get_db()
    items_stored = 0

    # Store display name
    await store_fact(
        user_id=profile.user_id,
        text=f"My name is {profile.display_name}",
        fact_type="IDENTITY",
        provenance="ONBOARDING",
    )
    items_stored += 1

    # Store timezone
    if profile.timezone:
        await store_fact(
            user_id=profile.user_id,
            text=f"My timezone is {profile.timezone}",
            fact_type="PREFERENCE",
            provenance="ONBOARDING",
        )
        items_stored += 1

    # Store communication style
    if profile.communication_style:
        await store_fact(
            user_id=profile.user_id,
            text=f"I prefer {profile.communication_style} communication style",
            fact_type="PREFERENCE",
            provenance="ONBOARDING",
        )
        items_stored += 1

    # Store preferences
    for key, value in profile.preferences.items():
        await store_fact(
            user_id=profile.user_id,
            text=f"Preference: {key} = {value}",
            fact_type="PREFERENCE",
            provenance="ONBOARDING",
        )
        items_stored += 1

    # Register contacts as entities
    for contact in profile.contacts:
        name = contact.get("name", "")
        rel = contact.get("relationship", "contact")
        if name:
            entity_id = await register_entity(
                user_id=profile.user_id,
                entity_type="PERSON",
                name=name,
                aliases=contact.get("aliases", "").split(",") if contact.get("aliases") else [],
                data={"relationship": rel},
                provenance="ONBOARDING",
            )
            await store_fact(
                user_id=profile.user_id,
                text=f"{name} is my {rel}",
                fact_type="RELATIONSHIP",
                provenance="ONBOARDING",
                related_to=entity_id,
            )
            items_stored += 2

    # Store routines
    for routine in profile.routines:
        if routine.strip():
            await store_fact(
                user_id=profile.user_id,
                text=f"Daily routine: {routine}",
                fact_type="ROUTINE",
                provenance="ONBOARDING",
            )
            items_stored += 1

    # Save onboarding status
    status = {
        "user_id": profile.user_id,
        "completed": True,
        "step": 5,
        "total_steps": 5,
        "items_stored": items_stored,
        "completed_at": datetime.now(timezone.utc),
    }
    await db.onboarding.update_one(
        {"user_id": profile.user_id},
        {"$set": status},
        upsert=True,
    )

    logger.info(
        "Onboarding complete: user=%s items_stored=%d",
        profile.user_id, items_stored,
    )

    return OnboardingStatus(**status)


@router.post("/skip/{user_id}", response_model=OnboardingStatus)
async def skip_onboarding(user_id: str):
    db = get_db()
    status = {
        "user_id": user_id,
        "completed": True,
        "step": 0,
        "total_steps": 5,
        "items_stored": 0,
        "skipped": True,
        "completed_at": datetime.now(timezone.utc),
    }
    await db.onboarding.update_one(
        {"user_id": user_id},
        {"$set": status},
        upsert=True,
    )
    return OnboardingStatus(**status)
