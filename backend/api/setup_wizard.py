"""Setup Wizard Mock API — dev-only endpoints for the first-time user setup flow.

Mimics ObeGee backend for account creation, workspace provisioning,
plan selection, payment, and pairing. MUST NOT exist in production.
"""
import logging
import uuid
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/setup", tags=["setup-wizard"])

PLANS = [
    {"plan_id": "starter", "name": "Starter", "price": 9, "currency": "GBP", "features": ["1 Agent", "5,000 messages/mo", "Basic tools", "Community support"]},
    {"plan_id": "pro", "name": "Pro", "price": 29, "currency": "GBP", "features": ["5 Agents", "50,000 messages/mo", "All tools", "Priority support", "Custom models (BYOK)"]},
    {"plan_id": "enterprise", "name": "Enterprise", "price": 99, "currency": "GBP", "features": ["Unlimited Agents", "Unlimited messages", "All tools + custom", "Dedicated support", "SSO & audit logs"]},
]


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str


class CreateTenantRequest(BaseModel):
    workspace_slug: str


class CheckoutRequest(BaseModel):
    plan_id: str
    tenant_id: str
    workspace_slug: str = ""


class PreferencesRequest(BaseModel):
    user_id: str = ""
    phone_number: str = ""
    timezone: str = "UTC"
    notifications_enabled: bool = True
    delivery_channels: list = []
    channel_details: dict = {}


@router.post("/register")
async def mock_register(req: RegisterRequest):
    db = get_db()
    existing = await db.setup_users.find_one({"email": req.email})
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    await db.setup_users.insert_one({"user_id": user_id, "email": req.email, "name": req.name, "created_at": datetime.now(timezone.utc)})
    token = f"mock_token_{user_id}"
    logger.info("Setup register: %s (%s)", req.email, user_id)
    return {"access_token": token, "user": {"user_id": user_id, "email": req.email, "name": req.name}}


@router.get("/check-slug/{slug}")
async def mock_check_slug(slug: str):
    if not re.match(r'^[a-z0-9-]{3,30}$', slug):
        return {"available": False, "reason": "invalid_format", "suggestion": slug.lower().replace(" ", "-")[:30]}
    db = get_db()
    existing = await db.setup_tenants.find_one({"workspace_slug": slug})
    if existing:
        return {"available": False, "reason": "taken", "suggestions": [f"{slug}-1", f"{slug}-ai", f"my-{slug}"]}
    return {"available": True}


@router.post("/create-tenant")
async def mock_create_tenant(req: CreateTenantRequest):
    db = get_db()
    tenant_id = f"tenant_{uuid.uuid4().hex[:12]}"
    await db.setup_tenants.insert_one({
        "tenant_id": tenant_id, "workspace_slug": req.workspace_slug,
        "status": "PENDING_PAYMENT", "created_at": datetime.now(timezone.utc),
    })
    logger.info("Setup tenant: %s (%s)", req.workspace_slug, tenant_id)
    return {"tenant_id": tenant_id, "workspace_slug": req.workspace_slug}


@router.get("/plans")
async def mock_plans():
    return PLANS


@router.post("/checkout")
async def mock_checkout(req: CheckoutRequest):
    return {"checkout_url": f"https://obegee.co.uk/checkout/mock?plan={req.plan_id}&tenant={req.tenant_id}", "session_id": str(uuid.uuid4())}


@router.post("/activate/{tenant_id}")
async def mock_activate(tenant_id: str):
    db = get_db()
    await db.setup_tenants.update_one({"tenant_id": tenant_id}, {"$set": {"status": "READY", "activated_at": datetime.now(timezone.utc)}})
    logger.info("Setup activate: %s", tenant_id)
    return {"status": "READY", "tenant_id": tenant_id}


@router.get("/tenant/{tenant_id}")
async def mock_tenant_status(tenant_id: str):
    db = get_db()
    doc = await db.setup_tenants.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if not doc:
        return {"status": "NOT_FOUND", "tenant_id": tenant_id}
    return {"status": doc.get("status", "PENDING"), "tenant_id": tenant_id, "workspace_slug": doc.get("workspace_slug")}


@router.post("/generate-code")
async def mock_generate_code():
    code = f"{uuid.uuid4().int % 900000 + 100000}"
    return {"code": code, "expires_in_seconds": 600}


@router.patch("/preferences")
async def mock_preferences(req: PreferencesRequest):
    db = get_db()
    update_fields = {"phone_number": req.phone_number, "timezone": req.timezone,
                     "notifications_enabled": req.notifications_enabled,
                     "delivery_channels": req.delivery_channels, "channel_details": req.channel_details,
                     "updated_at": datetime.now(timezone.utc)}
    await db.setup_users.update_one(
        {"user_id": req.user_id} if req.user_id else {},
        {"$set": update_fields},
        upsert=True,
    )
    return {"message": "Preferences updated", "delivery_channels": req.delivery_channels}
