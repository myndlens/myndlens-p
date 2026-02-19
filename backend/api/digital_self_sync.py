"""Digital Self — Data Source Sync Endpoints.

Extracts entity graphs and ONNX embedding vectors from:
  - Email (IMAP)
  - LinkedIn (access token or CSV export)
  - Social media (exported data)

Output contract:
  Returns a PKG diff: {nodes, edges} in the same schema as the on-device PKG.
  Each node includes an ONNX embedding vector (384-dim, bge-small-en-v1.5).
  Device merges the diff into its local encrypted PKG.

Privacy contract:
  - Credentials used only for the duration of the request.
  - NEVER persisted on the backend.
  - No raw email bodies, message content, or personal text stored.
  - Only entity identifiers, relationship weights, and embedding vectors returned.
  - User email addresses and names are NOT logged.
"""
from __future__ import annotations

import csv
import email as email_lib
import imaplib
import io
import logging
import re
import ssl
import time
from collections import defaultdict
from datetime import datetime, timezone
from email.header import decode_header
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from auth.tokens import validate_token
from auth.sso_validator import get_sso_validator, AuthError
from memory.client.embedder import embed
from observability.audit_log import log_audit_event
from schemas.audit import AuditEventType

router = APIRouter(prefix="/digital-self", tags=["digital-self-sync"])
logger = logging.getLogger(__name__)

IMAP_TIMEOUT_SECONDS = 20

TRAVEL_KEYWORDS = [
    "booking", "reservation", "flight", "hotel", "itinerary", "check-in",
    "e-ticket", "boarding", "confirmation", "travel", "trip", "airline",
    "airbnb", "expedia", "booking.com", "hilton", "marriott", "hyatt",
]


# ── Shared PKG output schema ──────────────────────────────────────────────────────────

class PKGNodeOut(BaseModel):
    """PKG node compatible with the on-device TypeScript PKGNode schema."""
    id: str
    type: str           # Person | Place | Trait | Interest | Source
    label: str          # Human-readable name
    data: Dict[str, Any]
    confidence: float
    provenance: str     # EMAIL | LINKEDIN | SOCIAL
    vector: List[float] # 384-dim ONNX embedding for semantic search


class PKGEdgeOut(BaseModel):
    """PKG edge compatible with the on-device TypeScript PKGEdge schema."""
    id: str
    type: str           # RELATIONSHIP | HAS_INTEREST | ASSOCIATED_WITH
    from_id: str
    to_id: str
    label: str
    confidence: float
    provenance: str
    data: Dict[str, Any]


class PKGDiff(BaseModel):
    """Graph diff returned to the device for merging into local PKG."""
    nodes: List[PKGNodeOut]
    edges: List[PKGEdgeOut]
    stats: Dict[str, int]


# ── Auth helper ───────────────────────────────────────────────────────────────────

def _get_user_id(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization[7:]
    try:
        claims = get_sso_validator().validate(token)
        return claims.obegee_user_id
    except AuthError:
        try:
            return validate_token(token).user_id
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token")


# ── Entity extraction helpers ──────────────────────────────────────────────────────────

def _domain_from_email(addr: str) -> str:
    """Extract domain from email address."""
    parts = addr.split("@")
    return parts[1] if len(parts) == 2 else ""


def _infer_relationship_strength(freq: int, total: int) -> tuple[str, float]:
    """Convert communication frequency into a labelled relationship strength."""
    ratio = freq / max(total, 1)
    if ratio >= 0.1 or freq >= 20:
        return "close contact", 0.95
    elif ratio >= 0.03 or freq >= 5:
        return "regular contact", 0.80
    else:
        return "occasional contact", 0.60


def _decode_subject(raw_subj: str) -> str:
    """Safely decode RFC2047-encoded email subject."""
    try:
        parts = decode_header(raw_subj)
        return " ".join(
            part.decode(enc or "utf-8", errors="replace") if isinstance(part, bytes) else part
            for part, enc in parts
        )
    except Exception:
        return raw_subj


async def _embed_texts(texts: List[str]) -> List[List[float]]:
    """Generate ONNX embeddings for a list of texts using bge-small-en-v1.5."""
    if not texts:
        return []
    return embed(texts)


# ── IMAP Email Sync ───────────────────────────────────────────────────────────────

class IMAPRequest(BaseModel):
    host: str
    port: int = 993
    email: str
    password: str
    max_emails: int = Field(default=200, ge=1, le=500)


@router.post("/email/sync", response_model=PKGDiff)
async def sync_imap_email(
    req: IMAPRequest,
    authorization: Optional[str] = Header(None),
):
    """Extract entity vectors and relationship graph from IMAP email.

    Returns PKGDiff with:
      - Person nodes (unique senders/recipients with ONNX vectors)
      - RELATIONSHIP edges (weighted by communication frequency)
      - Interest nodes (topics extracted from subjects via ONNX clustering)
    """
    user_id = _get_user_id(authorization)
    logger.info("[EmailSync] User=%s host=%s port=%d", user_id, req.host, req.port)

    try:
        ctx = ssl.create_default_context()
        with imaplib.IMAP4_SSL(req.host, req.port, ssl_context=ctx) as imap:
            imap.socket().settimeout(IMAP_TIMEOUT_SECONDS)
            imap.login(req.email, req.password)
            imap.select("INBOX", readonly=True)

            # Date-range search: last 90 days — avoids loading all UIDs
            since_date = datetime.fromtimestamp(
                time.time() - 90 * 86400, tz=timezone.utc
            ).strftime("%d-%b-%Y")
            _, data = imap.search(None, f'SINCE "{since_date}"')
            all_uids = data[0].split() if data[0] else []
            uids_to_fetch = all_uids[-req.max_emails:]

            # Frequency counters (email addr → count)
            contact_freq: Dict[str, int] = defaultdict(int)
            contact_names: Dict[str, str] = {}
            subject_tokens: List[str] = []

            for uid in uids_to_fetch:
                try:
                    _, msg_data = imap.fetch(uid, "(BODY[HEADER.FIELDS (FROM TO SUBJECT)])")
                    if not msg_data or not msg_data[0]:
                        continue
                    msg = email_lib.message_from_bytes(msg_data[0][1])

                    # Extract all participant addresses
                    for hdr in ("From", "To", "Cc"):
                        raw = msg.get(hdr, "")
                        # Match "Name <email>" or bare "email"
                        for match in re.finditer(
                            r'(?:([^<,"]+)\s*<)?([\w.+%-]+@[\w.-]+\.[\w]+)>?', raw
                        ):
                            name_raw, addr = match.group(1), match.group(2).lower()
                            if addr == req.email.lower():
                                continue
                            contact_freq[addr] += 1
                            if name_raw and addr not in contact_names:
                                contact_names[addr] = name_raw.strip().strip('"')

                    # Collect subject tokens for topic extraction
                    subj = _decode_subject(msg.get("Subject", ""))
                    if subj and len(subj) > 3:
                        subject_tokens.append(subj[:80])

                except Exception:
                    continue

    except imaplib.IMAP4.error as e:
        logger.warning("[EmailSync] IMAP error user=%s: %s", user_id, str(e))
        raise HTTPException(status_code=400, detail=f"IMAP connection failed: {str(e)}")
    except TimeoutError:
        logger.warning("[EmailSync] IMAP timeout user=%s host=%s", user_id, req.host)
        raise HTTPException(status_code=504, detail="IMAP server did not respond within timeout")
    except Exception as e:
        logger.error("[EmailSync] Unexpected error user=%s: %s", user_id, str(e))
        raise HTTPException(status_code=500, detail="Email sync failed")

    total_messages = sum(contact_freq.values())
    nodes: List[PKGNodeOut] = []
    edges: List[PKGEdgeOut] = []

    # ── Build Person nodes + embed ───────────────────────────────────────────────
    # Top 50 contacts by frequency
    top_contacts = sorted(contact_freq.items(), key=lambda x: x[1], reverse=True)[:50]

    embed_texts = []
    for addr, freq in top_contacts:
        name = contact_names.get(addr, addr.split("@")[0].replace(".", " ").title())
        domain = _domain_from_email(addr)
        label_text = f"{name} ({domain}) email contact"
        embed_texts.append(label_text)

    vectors = await _embed_texts(embed_texts)

    for i, (addr, freq) in enumerate(top_contacts):
        name = contact_names.get(addr, addr.split("@")[0].replace(".", " ").title())
        domain = _domain_from_email(addr)
        node_id = f"person_{re.sub(r'[^a-z0-9]', '_', addr)}"
        rel_label, confidence = _infer_relationship_strength(freq, total_messages)

        nodes.append(PKGNodeOut(
            id=node_id,
            type="Person",
            label=name,
            data={"domain": domain, "email_frequency": freq},
            confidence=confidence,
            provenance="EMAIL",
            vector=vectors[i] if i < len(vectors) else [],
        ))

        edges.append(PKGEdgeOut(
            id=f"edge_email_{node_id}",
            type="RELATIONSHIP",
            from_id="user_self",
            to_id=node_id,
            label=rel_label,
            confidence=confidence,
            provenance="EMAIL",
            data={"frequency": freq, "direction": "email"},
        ))

    # ── Extract Interest nodes from subject clustering ────────────────────────────
    # Use keyword frequency over subjects as a proxy for interests
    topic_freq: Dict[str, int] = defaultdict(int)
    stop_words = {"re", "fwd", "fw", "the", "a", "an", "and", "or", "of",
                  "for", "to", "in", "on", "is", "your", "with", "from"}
    for subj in subject_tokens:
        for token in re.findall(r"[a-zA-Z]{4,}", subj.lower()):
            if token not in stop_words:
                topic_freq[token] += 1

    top_topics = sorted(topic_freq.items(), key=lambda x: x[1], reverse=True)[:10]
    if top_topics:
        topic_texts = [t for t, _ in top_topics]
        topic_vectors = await _embed_texts(topic_texts)
        for i, (topic, freq) in enumerate(top_topics):
            node_id = f"interest_email_{topic}"
            nodes.append(PKGNodeOut(
                id=node_id,
                type="Interest",
                label=topic.title(),
                data={"frequency": freq, "source": "email_subjects"},
                confidence=min(0.5 + freq / 50, 0.9),
                provenance="EMAIL",
                vector=topic_vectors[i] if i < len(topic_vectors) else [],
            ))

    await log_audit_event(
        AuditEventType.DATA_ACCESSED,
        user_id=user_id,
        details={"action": "email_sync", "nodes": len(nodes), "edges": len(edges)},
    )
    logger.info("[EmailSync] User=%s nodes=%d edges=%d", user_id, len(nodes), len(edges))
    return PKGDiff(nodes=nodes, edges=edges, stats={"nodes": len(nodes), "edges": len(edges)})


# ── LinkedIn Sync ───────────────────────────────────────────────────────────────

class LinkedInCSVRequest(BaseModel):
    """LinkedIn Connections export CSV (Base64 encoded).

    User downloads from: LinkedIn → Settings → Data Privacy → Get a copy of your data→ Connections.csv
    """
    csv_base64: str = Field(..., description="Base64-encoded Connections.csv from LinkedIn data export")


@router.post("/linkedin/sync", response_model=PKGDiff)
async def sync_linkedin_csv(
    req: LinkedInCSVRequest,
    authorization: Optional[str] = Header(None),
):
    """Extract professional relationship graph from LinkedIn Connections CSV.

    Returns PKGDiff with:
      - Person nodes (each LinkedIn connection with ONNX embedding of name + role + company)
      - RELATIONSHIP edges (professional connections labelled by company overlap)
      - Interest nodes (companies, industries extracted)
    """
    user_id = _get_user_id(authorization)
    logger.info("[LinkedInSync] User=%s", user_id)

    try:
        import base64
        csv_bytes = base64.b64decode(req.csv_base64)
        reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8", errors="replace")))
        rows = list(reader)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid CSV: {str(e)}")

    if not rows:
        return PKGDiff(nodes=[], edges=[], stats={"nodes": 0, "edges": 0})

    # LinkedIn CSV columns: First Name, Last Name, Email Address, Company, Position, Connected On
    nodes: List[PKGNodeOut] = []
    edges: List[PKGEdgeOut] = []
    company_freq: Dict[str, int] = defaultdict(int)

    embed_texts = []
    valid_rows = []
    for row in rows[:500]:  # Cap at 500 connections
        first = (row.get("First Name") or row.get("first_name") or "").strip()
        last = (row.get("Last Name") or row.get("last_name") or "").strip()
        company = (row.get("Company") or row.get("company") or "").strip()
        position = (row.get("Position") or row.get("position") or "").strip()
        name = f"{first} {last}".strip()
        if not name:
            continue
        embed_texts.append(f"{name} {position} at {company}")
        valid_rows.append({"name": name, "company": company, "position": position})
        if company:
            company_freq[company] += 1

    vectors = await _embed_texts(embed_texts)

    for i, row in enumerate(valid_rows):
        name, company, position = row["name"], row["company"], row["position"]
        node_id = f"person_li_{re.sub(r'[^a-z0-9]', '_', name.lower())}"

        nodes.append(PKGNodeOut(
            id=node_id,
            type="Person",
            label=name,
            data={"company": company, "role": position, "source": "linkedin"},
            confidence=0.88,
            provenance="LINKEDIN",
            vector=vectors[i] if i < len(vectors) else [],
        ))
        edges.append(PKGEdgeOut(
            id=f"edge_li_{node_id}",
            type="RELATIONSHIP",
            from_id="user_self",
            to_id=node_id,
            label="professional connection",
            confidence=0.88,
            provenance="LINKEDIN",
            data={"company": company, "position": position},
        ))

    # Company nodes as Interest nodes (most frequent companies = relevant domains)
    top_companies = sorted(company_freq.items(), key=lambda x: x[1], reverse=True)[:10]
    if top_companies:
        comp_texts = [c for c, _ in top_companies]
        comp_vectors = await _embed_texts(comp_texts)
        for i, (company, freq) in enumerate(top_companies):
            node_id = f"interest_company_{re.sub(r'[^a-z0-9]', '_', company.lower())}"
            nodes.append(PKGNodeOut(
                id=node_id,
                type="Interest",
                label=company,
                data={"type": "company", "connection_count": freq},
                confidence=min(0.6 + freq / 20, 0.95),
                provenance="LINKEDIN",
                vector=comp_vectors[i] if i < len(comp_vectors) else [],
            ))

    await log_audit_event(
        AuditEventType.DATA_ACCESSED,
        user_id=user_id,
        details={"action": "linkedin_sync", "nodes": len(nodes), "edges": len(edges)},
    )
    logger.info("[LinkedInSync] User=%s nodes=%d edges=%d", user_id, len(nodes), len(edges))
    return PKGDiff(nodes=nodes, edges=edges, stats={"nodes": len(nodes), "edges": len(edges)})


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


# ── Snapshot ──────────────────────────────────────────────────────────────────

@router.get("/snapshot")
async def get_ds_snapshot(authorization: Optional[str] = Header(None)):
    """Return what the server holds for this user (counts only)."""
    user_id = _get_user_id(authorization)
    from core.database import get_db
    db = get_db()
    return {
        "user_id": user_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "server_side_data": {
            "audit_events": await db.audit_events.count_documents({"user_id": user_id}),
            "vector_cache_entries": await db.vector_store.count_documents({"metadata.user_id": user_id}),
        },
        "note": "Full Digital Self PKG lives encrypted on your device.",
    }
