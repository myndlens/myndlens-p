"""Proactive Intelligence — Nudge Queue + Scheduler.

Generates proactive nudges by scanning the user's Digital Self for:
  - Overdue pending actions (user owes or others owe)
  - Stalled active threads (no activity 3+ days)
  - Upcoming meetings/travel
  - Cross-contact topic overlaps

Nudges are queued per-user and delivered via:
  1. TTS when app is open (WS push)
  2. Push notification when app is closed (FCM — future)

The scheduler runs periodically (configurable) on the MyndLens backend.
"""
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Nudge:
    """A single proactive nudge to deliver to the user."""
    nudge_id: str
    user_id: str
    priority: int          # 1=urgent, 2=important, 3=informational
    category: str          # overdue | stalled | upcoming | cross_contact | follow_up
    title: str             # short: "Jacob's hotel preferences overdue"
    message: str           # TTS-friendly: "KS, Jacob hasn't sent the hotel preferences..."
    source_contact: str    # who this is about
    created_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    delivered: bool = False
    dismissed: bool = False


# Per-user nudge queues (in-memory, persisted to MongoDB on write)
_nudge_queues: Dict[str, List[Nudge]] = {}


def get_nudges(user_id: str, max_count: int = 5) -> List[Nudge]:
    """Get top undelivered nudges for a user, sorted by priority."""
    queue = _nudge_queues.get(user_id, [])
    pending = [n for n in queue if not n.delivered and not n.dismissed]
    pending.sort(key=lambda n: (n.priority, n.created_at))
    return pending[:max_count]


def mark_delivered(user_id: str, nudge_id: str):
    for n in _nudge_queues.get(user_id, []):
        if n.nudge_id == nudge_id:
            n.delivered = True
            break


def dismiss_nudge(user_id: str, nudge_id: str):
    for n in _nudge_queues.get(user_id, []):
        if n.nudge_id == nudge_id:
            n.dismissed = True
            break


def clear_old_nudges(user_id: str, max_age_hours: int = 24):
    """Remove nudges older than max_age_hours."""
    cutoff = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)
    queue = _nudge_queues.get(user_id, [])
    _nudge_queues[user_id] = [n for n in queue if n.created_at > cutoff]


async def generate_nudges(user_id: str, user_first_name: str = "") -> List[Nudge]:
    """Scan Digital Self and generate proactive nudges.

    Called by the scheduler every 4 hours, or on app open.
    """
    from mcp.ds_server import call_tool
    import uuid

    nudges = []
    name = user_first_name or "there"

    # 1. Overdue pending actions
    try:
        result = await call_tool("get_pending_actions", {"user_id": user_id})
        if isinstance(result, dict):
            for item in result.get("user_owes", []):
                nudges.append(Nudge(
                    nudge_id=f"nud_{uuid.uuid4().hex[:8]}",
                    user_id=user_id,
                    priority=1,
                    category="overdue",
                    title=f"You owe: {item.get('contact', '?')}",
                    message=f"{name}, you still need to: {item.get('text', '')[:80]}",
                    source_contact=item.get("contact", ""),
                ))
            for item in result.get("they_owe", []):
                nudges.append(Nudge(
                    nudge_id=f"nud_{uuid.uuid4().hex[:8]}",
                    user_id=user_id,
                    priority=2,
                    category="overdue",
                    title=f"Waiting on: {item.get('contact', '?')}",
                    message=f"{name}, {item.get('contact', 'someone')} still owes you: {item.get('text', '')[:80]}",
                    source_contact=item.get("contact", ""),
                ))
    except Exception as e:
        logger.warning("[PROACTIVE] pending_actions failed: %s", str(e)[:60])

    # 2. Stalled threads (tension or stalled status)
    try:
        result = await call_tool("get_active_threads", {"user_id": user_id})
        if isinstance(result, dict):
            for thread in result.get("threads", []):
                tension = thread.get("tension", "none")
                if tension in ("medium", "high"):
                    nudges.append(Nudge(
                        nudge_id=f"nud_{uuid.uuid4().hex[:8]}",
                        user_id=user_id,
                        priority=1 if tension == "high" else 2,
                        category="stalled",
                        title=f"Tension with {thread.get('contact', '?')}",
                        message=f"{name}, there's unresolved tension with {thread.get('contact', '?')}: {thread.get('text', '')[:60]}",
                        source_contact=thread.get("contact", ""),
                    ))
    except Exception as e:
        logger.warning("[PROACTIVE] active_threads failed: %s", str(e)[:60])

    # 3. Upcoming events
    try:
        result = await call_tool("get_schedule", {"user_id": user_id})
        if isinstance(result, dict):
            for event in result.get("events", []):
                nudges.append(Nudge(
                    nudge_id=f"nud_{uuid.uuid4().hex[:8]}",
                    user_id=user_id,
                    priority=2,
                    category="upcoming",
                    title=f"Upcoming: {event.get('type', 'event')}",
                    message=f"{name}, upcoming: {event.get('text', '')[:80]}",
                    source_contact=event.get("contact", ""),
                ))
    except Exception as e:
        logger.warning("[PROACTIVE] schedule failed: %s", str(e)[:60])

    # Deduplicate by title
    seen = set()
    unique = []
    for n in nudges:
        if n.title not in seen:
            seen.add(n.title)
            unique.append(n)

    # Store in queue
    _nudge_queues[user_id] = unique
    logger.info("[PROACTIVE] user=%s generated %d nudges", user_id, len(unique))
    return unique


async def generate_morning_briefing(user_id: str, user_first_name: str = "") -> Optional[str]:
    """Generate a TTS-friendly morning briefing from nudges + schedule.

    Returns the briefing text, or None if nothing to report.
    """
    nudges = await generate_nudges(user_id, user_first_name)
    if not nudges:
        return None

    name = user_first_name or "there"
    lines = [f"Good morning {name}. Here's what needs your attention today."]

    urgent = [n for n in nudges if n.priority == 1]
    important = [n for n in nudges if n.priority == 2]
    info = [n for n in nudges if n.priority == 3]

    if urgent:
        for n in urgent[:3]:
            lines.append(n.message)

    if important:
        for n in important[:3]:
            lines.append(n.message)

    if info:
        lines.append(f"And {len(info)} other items when you're ready.")

    briefing = " ".join(lines)
    logger.info("[BRIEFING] user=%s items=%d length=%d", user_id, len(nudges), len(briefing))
    return briefing
