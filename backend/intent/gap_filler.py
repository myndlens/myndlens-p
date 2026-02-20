"""Intent Gap Filler — enriches fragmented human speech with Digital Self context.

Core principle:
    Humans speak in fragments. The gap filler converts fragments into
    complete, machine-parseable intents before L1 Scout sees them.

    "Email Bob the thing from yesterday"
    → "Send email to Bob (manager, Acme Corp) about the Q3 budget discussion
       from yesterday (Feb 19). [Context: Bob is your manager | You are in London]"

The gap filler runs AFTER the final transcript arrives, but uses a SessionContext
that was pre-loaded at auth time — so the lookup cost is ZERO per mandate.

It does NOT invent facts. It only fills gaps from what is in the user's Digital Self.
Unresolvable references are left as-is.
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)

# ── Session Context ───────────────────────────────────────────────────────────

@dataclass
class ParsedEntity:
    """A single resolved entity from the Digital Self."""
    name: str                           # Canonical name ("Bob Smith")
    first_name: str                     # First name for lookup ("Bob")
    entity_type: str                    # Person | Place | Trait | Interest | Event
    relationship: str = ""              # manager | colleague | friend
    context: str = ""                   # Free-text annotation for the LLM
    confidence: float = 1.0


@dataclass
class SessionContext:
    """Digital Self context pre-loaded at WS session start.

    Lives for the duration of the WS session.
    Pre-populated from device context_sync or server-side ONNX recall.
    Updated mid-session when device sends a fresher capsule.
    """
    user_id: str
    loaded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    entities: List[ParsedEntity] = field(default_factory=list)
    user_name: str = ""
    places: List[str] = field(default_factory=list)
    traits: List[str] = field(default_factory=list)
    recent_transcripts: List[str] = field(default_factory=list)    # last 5 mandates
    raw_summary: str = ""

    def age_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.loaded_at).total_seconds()

    def is_stale(self, ttl_seconds: int = 3600) -> bool:
        return self.age_seconds() > ttl_seconds


# ── Summary Parser ────────────────────────────────────────────────────────────

def parse_capsule_summary(summary: str, user_id: str) -> SessionContext:
    """Parse a context capsule summary string into a structured SessionContext.

    Summary format from buildContextCapsule():
      "User: KS Reddy | Contacts: Bob (manager); Alice (colleague) |
       User traits: Night Owl | Known places: London, New York"
    """
    ctx = SessionContext(user_id=user_id, raw_summary=summary)

    for part in summary.split("|"):
        part = part.strip()
        if not part:
            continue

        if part.startswith("User:"):
            ctx.user_name = part[5:].strip()

        elif part.startswith("Contacts:"):
            contacts_raw = part[9:].strip()
            for contact in contacts_raw.split(";"):
                contact = contact.strip()
                if not contact:
                    continue
                # Parse "Bob (manager)" or just "Bob"
                match = re.match(r'^([^(]+)(?:\(([^)]+)\))?', contact)
                if match:
                    name = match.group(1).strip()
                    relationship = match.group(2).strip() if match.group(2) else ""
                    first_name = name.split()[0] if name else ""
                    if first_name:
                        ctx.entities.append(ParsedEntity(
                            name=name,
                            first_name=first_name.lower(),
                            entity_type="Person",
                            relationship=relationship,
                            context=f"{name} ({relationship})" if relationship else name,
                        ))

        elif part.startswith("User traits:"):
            traits_raw = part[12:].strip()
            ctx.traits = [t.strip() for t in traits_raw.split(",") if t.strip()]

        elif part.startswith("Known places:"):
            places_raw = part[13:].strip()
            ctx.places = [p.strip() for p in places_raw.split(",") if p.strip()]

    logger.info(
        "[SessionCtx] Parsed: user=%s entities=%d places=%d traits=%d",
        ctx.user_name or user_id, len(ctx.entities), len(ctx.places), len(ctx.traits),
    )
    return ctx


# ── Gap Filler ────────────────────────────────────────────────────────────────

# Temporal reference patterns
_TEMPORAL_PATTERNS = [
    (re.compile(r'\byesterday\b', re.I), '_YESTERDAY_'),
    (re.compile(r'\blast week\b', re.I), '_LAST_WEEK_'),
    (re.compile(r'\bearlier today\b', re.I), '_TODAY_'),
    (re.compile(r'\bthis morning\b', re.I), '_THIS_MORNING_'),
]

# Vague reference patterns that benefit from context injection
_VAGUE_REFS = re.compile(
    r'\b(the thing|that thing|it|the issue|the matter|the project|'
    r'the report|the proposal|the document|that meeting|that call|'
    r'the discussion|the conversation)\b',
    re.I,
)


def _resolve_entities(transcript: str, entities: List[ParsedEntity]) -> str:
    """Replace bare first names with full annotated references."""
    enriched = transcript
    for entity in entities:
        if not entity.first_name:
            continue
        # Only replace if: first name present AND full context is different
        if entity.context == entity.first_name:
            continue
        pattern = re.compile(r'\b' + re.escape(entity.first_name) + r'\b', re.I)
        if pattern.search(enriched):
            enriched = pattern.sub(entity.context, enriched, count=1)
    return enriched


def _resolve_temporal(transcript: str) -> str:
    """Replace temporal references with dated equivalents."""
    today = datetime.now(timezone.utc)
    replacements = {
        '_YESTERDAY_': f"yesterday ({(today - timedelta(days=1)).strftime('%B %d')})",
        '_LAST_WEEK_': f"last week (week of {(today - timedelta(days=7)).strftime('%B %d')})",
        '_TODAY_': f"today ({today.strftime('%B %d')})",
        '_THIS_MORNING_': f"this morning ({today.strftime('%B %d')})",
    }
    enriched = transcript
    for pattern, placeholder in _TEMPORAL_PATTERNS:
        enriched = pattern.sub(replacements.get(placeholder, placeholder), enriched)
    return enriched


def _build_context_prefix(ctx: SessionContext) -> str:
    """Build a compact context prefix for the LLM."""
    parts = []

    if ctx.user_name:
        parts.append(f"User: {ctx.user_name}")

    if ctx.entities:
        top = [e.context for e in ctx.entities[:5] if e.context]
        if top:
            parts.append(f"Contacts: {'; '.join(top)}")

    if ctx.places:
        parts.append(f"Locations: {', '.join(ctx.places[:3])}")

    if ctx.traits:
        parts.append(f"User traits: {', '.join(ctx.traits[:3])}")

    if ctx.recent_transcripts:
        last = ctx.recent_transcripts[-1][:60]
        parts.append(f"Previous intent: {last}")

    return " | ".join(parts) if parts else ""


async def enrich_transcript(
    transcript: str,
    session_ctx: Optional[SessionContext],
) -> str:
    """Enrich a fragmented transcript using the pre-loaded session Digital Self.

    Returns a context-enriched transcript for L1 Scout. The LLM sees full
    entity annotations and temporal context — not raw human fragments.

    If no session context is available, returns the original transcript unchanged.
    """
    if not transcript.strip():
        return transcript

    if not session_ctx or (not session_ctx.entities and not session_ctx.raw_summary):
        return transcript  # No DS loaded — pass through unchanged

    # Step 1: Resolve entity names to full identities
    enriched = _resolve_entities(transcript, session_ctx.entities)

    # Step 2: Resolve temporal references
    enriched = _resolve_temporal(enriched)

    # Step 3: Inject context prefix for LLM awareness
    prefix = _build_context_prefix(session_ctx)

    if prefix:
        final = f"[{prefix}]\n\nUser mandate: {enriched}"
    else:
        final = enriched

    if final != transcript:
        logger.info(
            "[GapFiller] session_user=%s | '%s' -> '%s'",
            session_ctx.user_name or session_ctx.user_id,
            transcript[:50],
            enriched[:50],
        )

    return final


# ── Lightweight extraction-time coherence check (no LLM call) ────────────────

_ACTION_SIGNAL_MAP: dict = {
    "COMM_SEND": {"send", "email", "message", "tell", "notify", "text", "whatsapp", "slack", "reply", "forward"},
    "SCHED_MODIFY": {"schedule", "meeting", "book", "appointment", "calendar", "reschedule", "cancel", "remind", "block"},
    "INFO_RETRIEVE": {"find", "search", "look", "check", "what", "who", "when", "where", "show", "get", "fetch"},
    "DOC_EDIT": {"write", "draft", "create", "edit", "update", "change", "document", "report", "proposal"},
    "CODE_GEN": {"code", "script", "program", "function", "python", "javascript", "sql", "implement", "hello world"},
    "FIN_TRANS": {"pay", "transfer", "invoice", "expense", "purchase", "buy", "payment", "refund"},
}


def check_extraction_coherence(transcript: str, action_class: str, confidence: float) -> tuple[bool, float]:
    """Lightweight rule-based coherence check: does the action_class match transcript signals?

    No LLM call. Runs at extraction time before TTS response is generated.
    If incoherent, confidence is downgraded to flag for L1 review.
    Returns (is_coherent: bool, adjusted_confidence: float).
    """
    if action_class in ("DRAFT_ONLY", "SYS_CONFIG"):
        return True, confidence  # Too generic to check with signals

    lower = transcript.lower()
    signals = _ACTION_SIGNAL_MAP.get(action_class, set())
    if not signals:
        return True, confidence  # Unknown action class -- no check

    if not any(signal in lower for signal in signals) and confidence > 0.5:
        logger.info(
            "[ExtractionCoherence] No signal words for action=%s in '%s' -- downgrading %.2f->0.45",
            action_class, transcript[:50], confidence,
        )
        return False, 0.45

    return True, confidence


