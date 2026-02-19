"""Digital Self — Category B data sync endpoints.

Handles email sync (IMAP), audit log retrieval, and PKG snapshot export.

Privacy contract:
- Credentials are used only for the duration of the request.
- They are NEVER persisted on the backend.
- Only structured metadata (contact frequencies, travel signals) is returned.
- No email bodies, no message content.
- User email addresses are NOT logged.
"""
import email as email_lib
import imaplib
import logging
import re
import ssl
from datetime import datetime, timezone
from email.header import decode_header
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from auth.tokens import validate_token
from auth.sso_validator import get_sso_validator, AuthError
from observability.audit_log import log_audit_event
from schemas.audit import AuditEventType

router = APIRouter(prefix="/digital-self", tags=["digital-self-sync"])
logger = logging.getLogger(__name__)

TRAVEL_KEYWORDS = [
    "booking", "reservation", "flight", "hotel", "itinerary", "check-in",
    "e-ticket", "boarding", "confirmation", "travel", "trip", "airline",
    "airbnb", "expedia", "booking.com", "hilton", "marriott", "hyatt",
]

IMAP_TIMEOUT_SECONDS = 20  # Hard timeout for IMAP connections


def _get_user_id(authorization: Optional[str]) -> str:
    """Resolve user_id from Bearer token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization[7:]
    try:
        validator = get_sso_validator()
        claims = validator.validate(token)
        return claims.obegee_user_id
    except AuthError:
        try:
            legacy = validate_token(token)
            return legacy.user_id
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token")


# ── IMAP Email Sync ─────────────────────────────────────────────────────────

class IMAPRequest(BaseModel):
    host: str
    port: int = 993
    email: str
    password: str       # App Password recommended. Never persisted. Never logged.
    max_emails: int = Field(default=200, ge=1, le=500)  # Bounded: prevents DoS via memory exhaustion


class EmailSyncResult(BaseModel):
    contacts_found: int
    travel_signals: int
    top_contacts: List[Dict[str, Any]]
    travel_subjects: List[str]
    date_range: Dict[str, str]


@router.post("/email/sync", response_model=EmailSyncResult)
async def sync_imap_email(
    req: IMAPRequest,
    authorization: Optional[str] = Header(None),
):
    """Connect to IMAP, extract contact patterns and travel signals.

    Credentials used only for this request — never stored, never logged.
    Returns structured metadata only — no email bodies.
    """
    user_id = _get_user_id(authorization)
    # Email address NOT logged — it is PII
    logger.info("[EmailSync] User=%s host=%s port=%d", user_id, req.host, req.port)

    try:
        ctx = ssl.create_default_context()
        # Set socket timeout to prevent hanging on unresponsive IMAP servers
        with imaplib.IMAP4_SSL(req.host, req.port, ssl_context=ctx) as imap:
            imap.socket().settimeout(IMAP_TIMEOUT_SECONDS)
            imap.login(req.email, req.password)
            imap.select("INBOX", readonly=True)

            # Fetch only recent emails using IMAP date range — avoids loading all UIDs
            from email.utils import formatdate
            import time as _time
            since_days = 90
            since_date = formatdate(
                _time.mktime(_time.gmtime(_time.time() - since_days * 86400)),
                usegmt=True,
            )[:11].replace(' ', '-')  # "DD-Mon-YYYY" format for IMAP
            _, data = imap.search(None, f'SINCE "{since_date}"')
            all_uids = data[0].split() if data[0] else []
            uids_to_fetch = all_uids[-req.max_emails:]  # Last N from date-filtered results

            contact_freq: Dict[str, int] = {}
            travel_subjects: List[str] = []
            dates: List[str] = []

            for uid in uids_to_fetch:
                try:
                    _, msg_data = imap.fetch(uid, "(BODY[HEADER.FIELDS (FROM TO DATE SUBJECT)])")
                    if not msg_data or not msg_data[0]:
                        continue
                    raw = msg_data[0][1]
                    msg = email_lib.message_from_bytes(raw)

                    from_header = msg.get("From", "")
                    emails_in_from = re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", from_header)
                    for addr in emails_in_from:
                        addr = addr.lower()
                        if addr != req.email.lower():
                            contact_freq[addr] = contact_freq.get(addr, 0) + 1

                    raw_subj = msg.get("Subject", "")
                    subj_parts = decode_header(raw_subj)
                    subj = " ".join(
                        part.decode(enc or "utf-8") if isinstance(part, bytes) else part
                        for part, enc in subj_parts
                    )
                    if any(kw in subj.lower() for kw in TRAVEL_KEYWORDS):
                        travel_subjects.append(subj[:100])

                    date_str = msg.get("Date", "")
                    if date_str:
                        dates.append(date_str[:30])

                except Exception:
                    continue

        top = sorted(contact_freq.items(), key=lambda x: x[1], reverse=True)[:20]
        top_contacts = [{"email": addr, "frequency": freq} for addr, freq in top]

        result = EmailSyncResult(
            contacts_found=len(contact_freq),
            travel_signals=len(travel_subjects),
            top_contacts=top_contacts,
            travel_subjects=list(set(travel_subjects))[:10],
            date_range={
                "oldest": dates[0] if dates else "",
                "newest": dates[-1] if dates else "",
            },
        )

        await log_audit_event(
            AuditEventType.DATA_ACCESSED,
            user_id=user_id,
            details={"action": "email_sync", "contacts_found": result.contacts_found},
        )

        logger.info("[EmailSync] User=%s contacts=%d travel=%d", user_id, result.contacts_found, result.travel_signals)
        return result

    except imaplib.IMAP4.error as e:
        logger.warning("[EmailSync] IMAP error user=%s: %s", user_id, str(e))
        raise HTTPException(status_code=400, detail=f"IMAP connection failed: {str(e)}")
    except TimeoutError:
        logger.warning("[EmailSync] IMAP timeout user=%s host=%s", user_id, req.host)
        raise HTTPException(status_code=504, detail="IMAP server did not respond within timeout")
    except Exception as e:
        logger.error("[EmailSync] Unexpected error user=%s: %s", user_id, str(e))
        raise HTTPException(status_code=500, detail="Email sync failed")


# ── Audit Log ───────────────────────────────────────────────────────────────

@router.get("/audit-log")
async def get_audit_log(
    authorization: Optional[str] = Header(None),
    limit: int = 50,
):
    """Return the user's audit event log."""
    user_id = _get_user_id(authorization)
    from core.database import get_db
    db = get_db()
    events = await db.audit_events.find(
        {"user_id": user_id},
        {"_id": 0},
    ).sort("timestamp", -1).limit(min(limit, 200)).to_list(200)
    return {"events": events, "count": len(events)}


# ── Digital Self Snapshot Export ─────────────────────────────────────────────

@router.get("/snapshot")
async def get_ds_snapshot(
    authorization: Optional[str] = Header(None),
):
    """Export a JSON snapshot of what Digital Self data the backend holds.

    Note: The on-device PKG is richer — this only shows server-side context capsule
    cache and audit history. The full PKG lives on-device and can be exported
    from the app directly.
    """
    user_id = _get_user_id(authorization)
    from core.database import get_db
    db = get_db()

    audit_count = await db.audit_events.count_documents({"user_id": user_id})
    vector_count = await db.vector_store.count_documents({"metadata.user_id": user_id})

    return {
        "user_id": user_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "server_side_data": {
            "audit_events": audit_count,
            "vector_cache_entries": vector_count,
        },
        "note": "Full Digital Self PKG lives encrypted on your device. Use the in-app export to download it.",
    }
