"""Proactive Scheduler — runs periodic nudge generation and briefings.

Runs as a background task inside the MyndLens backend process.
Per-user timezone-aware scheduling for morning briefings.
"""
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict

logger = logging.getLogger(__name__)

# Track which users got their morning briefing today
_briefed_today: Dict[str, str] = {}  # user_id → date string "2026-02-27"

# Active WebSocket sessions for push delivery
_active_sessions: Dict[str, object] = {}  # user_id → ws object


def register_session(user_id: str, ws):
    _active_sessions[user_id] = ws


def unregister_session(user_id: str):
    _active_sessions.pop(user_id, None)


async def scheduler_loop():
    """Main scheduler loop — runs every 60 seconds with auto-restart on failure."""
    logger.info("[SCHEDULER] Proactive scheduler started")
    consecutive_failures = 0
    while True:
        try:
            await _tick()
            consecutive_failures = 0
        except Exception as e:
            consecutive_failures += 1
            logger.error("[SCHEDULER] tick error (%d consecutive): %s", consecutive_failures, str(e)[:80])
            if consecutive_failures >= 5:
                logger.critical("[SCHEDULER] 5 consecutive failures — backing off to 5min interval")
                await asyncio.sleep(300)
                consecutive_failures = 0
                continue
        await asyncio.sleep(60)


async def _tick():
    """One scheduler tick — check all active users for pending briefings/nudges."""
    now = datetime.now(timezone.utc)

    for user_id, ws in list(_active_sessions.items()):
        try:
            # Check if morning briefing is due (8:00 AM user's timezone)
            # For now: use UTC+5:30 for India, UTC+0 for UK
            # TODO: read user timezone from profile
            user_hour = (now.hour + 5) % 24  # approximate IST

            today = now.strftime("%Y-%m-%d")
            already_briefed = _briefed_today.get(user_id) == today

            if user_hour >= 8 and user_hour < 9 and not already_briefed:
                # Morning briefing time
                from proactive.nudge_engine import generate_morning_briefing
                from gateway.ws_server import _session_contexts

                # Find user's first name
                first_name = ""
                for sid, ctx in _session_contexts.items():
                    if ctx.user_name:
                        first_name = ctx.user_name.split()[0]
                        break

                briefing = await generate_morning_briefing(user_id, first_name)
                if briefing:
                    await _deliver_nudge_tts(ws, briefing, user_id)
                    _briefed_today[user_id] = today
                    logger.info("[SCHEDULER] Morning briefing delivered to %s", user_id)

            # Every 4 hours: generate fresh nudges (even if not briefing time)
            if now.hour % 4 == 0 and now.minute < 2:
                from proactive.nudge_engine import generate_nudges
                nudges = await generate_nudges(user_id)
                if nudges:
                    logger.info("[SCHEDULER] %d nudges generated for %s", len(nudges), user_id)

        except Exception as e:
            logger.debug("[SCHEDULER] user %s error: %s", user_id, str(e)[:60])


async def _deliver_nudge_tts(ws, text: str, user_id: str):
    """Deliver a nudge via TTS over WebSocket."""
    try:
        import json
        from schemas.ws_messages import WSMessageType

        # Send as TTS audio
        envelope = json.dumps({
            "type": WSMessageType.TTS_AUDIO.value,
            "payload": {
                "text": text,
                "session_id": f"briefing-{user_id}",
                "format": "text",
                "is_mock": True,
                "is_clarification": False,
                "auto_record": False,
            }
        })
        await ws.send_text(envelope)
    except Exception as e:
        logger.warning("[SCHEDULER] TTS delivery failed: %s", str(e)[:60])


async def deliver_nudges_on_connect(user_id: str, ws, first_name: str = ""):
    """Called when user opens the app — deliver any pending nudges."""
    from proactive.nudge_engine import get_nudges, mark_delivered

    nudges = get_nudges(user_id, max_count=3)
    if not nudges:
        return

    # Build a short summary of pending nudges
    name = first_name or "there"
    items = [n.message for n in nudges[:3]]
    text = f"{name}, a few things need your attention. " + " ".join(items)

    await _deliver_nudge_tts(ws, text, user_id)

    for n in nudges[:3]:
        mark_delivered(user_id, n.nudge_id)

    logger.info("[PROACTIVE] Delivered %d nudges to %s on connect", len(nudges[:3]), user_id)
