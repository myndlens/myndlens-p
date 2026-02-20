"""
Pre-defined Agent Registry — Named, purpose-built agents with assigned skills + tools.

Agent = Name + Purpose + Skills + Tools.

Each agent is defined by WHAT IT DOES, not by technical names.
Selection is by PURPOSE MATCH — the agent whose job description best fits
the incoming mandate is selected.

These agents are provisioned into MongoDB on first run for each tenant.
"""
from typing import Any

# ── Pre-defined agent definitions ─────────────────────────────────────────────
# Each agent:
#   name        : human-readable purpose name
#   description : what this agent does (used for mandate matching)
#   skills      : ClawHub skill slugs it uses
#   tools       : OpenClaw tool profile + allow list
#   action_class: primary action classes it handles
#   triggers    : keywords that activate this agent
#   profile     : OpenClaw tool profile

PREDEFINED_AGENTS: list[dict[str, Any]] = [

    {
        "name": "Morning Briefing Agent",
        "description": (
            "Delivers a personalised morning briefing: top news, AI updates, "
            "market summary, weather at user's location. Runs daily on cron."
        ),
        "skills": ["news-aggregator", "daily-ai-news", "finance-news", "weather", "summarize"],
        "tools": {"profile": "web", "allow": ["group:web", "web_fetch", "web_search"]},
        "action_class": ["INFO_RETRIEVE"],
        "triggers": ["morning", "briefing", "news", "today", "daily", "summary", "digest",
                     "ai news", "market", "weather"],
    },

    {
        "name": "Email Synopsis Agent",
        "description": (
            "Reads, searches, summarises and drafts email. "
            "Handles Gmail, Outlook, IMAP. Condenses long threads."
        ),
        "skills": ["gmail", "outlook-api", "imap-smtp-email", "himalaya", "summarize", "humanizer"],
        "tools": {"profile": "messaging", "allow": ["group:messaging", "web_fetch"]},
        "action_class": ["COMM_SEND", "INFO_RETRIEVE"],
        "triggers": ["email", "gmail", "outlook", "inbox", "reply", "forward", "draft",
                     "send email", "mail", "thread", "unread"],
    },

    {
        "name": "WhatsApp Agent",
        "description": (
            "Sends and manages WhatsApp Business messages. "
            "Ensures messages sound human, not AI-generated."
        ),
        "skills": ["whatsapp-business", "humanizer"],
        "tools": {"profile": "messaging", "allow": ["group:messaging"]},
        "action_class": ["COMM_SEND"],
        "triggers": ["whatsapp", "wa", "message", "text", "ping", "drop a message",
                     "send a whatsapp", "whatsapp message"],
    },

    {
        "name": "Slack Agent",
        "description": (
            "Posts messages, reacts, manages threads and pins in Slack. "
            "Handles channel notifications and DMs."
        ),
        "skills": ["slack", "humanizer"],
        "tools": {"profile": "messaging", "allow": ["group:messaging"]},
        "action_class": ["COMM_SEND"],
        "triggers": ["slack", "channel", "post to slack", "notify slack", "slack message",
                     "dm on slack", "ping on slack"],
    },

    {
        "name": "Calendar & Meetings Agent",
        "description": (
            "Creates, modifies, cancels calendar events. "
            "Schedules Google Meet links. Sets reminders and recurring events."
        ),
        "skills": ["gog", "google-meet", "outlook-api", "proactive-agent"],
        "tools": {"profile": "messaging", "allow": ["group:messaging", "cron"]},
        "action_class": ["SCHED_MODIFY"],
        "triggers": ["schedule", "meeting", "calendar", "book", "appointment", "reschedule",
                     "cancel meeting", "block time", "remind", "recurring", "standup",
                     "google meet", "invite", "add to calendar"],
    },

    {
        "name": "Research Agent",
        "description": (
            "Researches topics, searches the web, extracts content from URLs, "
            "summarises PDFs and YouTube videos. Provides cited answers."
        ),
        "skills": ["tavily-search", "brave-search", "summarize", "agent-browser",
                   "youtube-watcher"],
        "tools": {"profile": "web", "allow": ["group:web", "web_fetch", "web_search"]},
        "action_class": ["INFO_RETRIEVE"],
        "triggers": ["search", "find", "research", "look up", "what is", "summarise",
                     "summarize", "latest on", "check", "get info", "find out",
                     "youtube", "pdf", "article"],
    },

    {
        "name": "Marketing Agent",
        "description": (
            "Creates marketing content: copywriting, SEO articles, social posts, "
            "email sequences, campaign strategy. Removes AI writing patterns."
        ),
        "skills": ["marketing-mode", "ai-social-media", "humanizer", "humanize-ai-text",
                   "afrexai-email-marketing-engine"],
        "tools": {"profile": "messaging", "allow": ["group:messaging", "group:fs"]},
        "action_class": ["DOC_EDIT", "COMM_SEND"],
        "triggers": ["marketing", "campaign", "copy", "copywriting", "seo", "landing page",
                     "email sequence", "newsletter", "social media post", "ad", "launch",
                     "content", "write for", "blog"],
    },

    {
        "name": "Social Media Publisher",
        "description": (
            "Posts and schedules content across TikTok, Instagram, YouTube Shorts, "
            "LinkedIn, Twitter, Facebook, Threads simultaneously."
        ),
        "skills": ["post-bridge", "upload-post", "ai-social-media", "humanizer"],
        "tools": {"profile": "messaging", "allow": ["group:messaging", "exec"]},
        "action_class": ["COMM_SEND", "DOC_EDIT"],
        "triggers": ["post to", "publish", "tiktok", "instagram", "reels", "youtube shorts",
                     "linkedin post", "social media", "upload video", "schedule post",
                     "cross-post"],
    },

    {
        "name": "Finance & Payments Agent",
        "description": (
            "Handles Stripe payments, invoices, subscriptions, refunds. "
            "Checks stock prices, market analysis, prediction markets."
        ),
        "skills": ["stripe-api", "stock-analysis", "finance", "finance-news", "foreseekai"],
        "tools": {"profile": "coding", "allow": ["group:messaging", "group:web", "exec"]},
        "action_class": ["FIN_TRANS", "INFO_RETRIEVE"],
        "triggers": ["invoice", "payment", "stripe", "subscription", "refund", "charge",
                     "stock", "market", "finance", "nvda", "aapl", "bitcoin", "price",
                     "bet", "predict", "kalshi"],
    },

    {
        "name": "Code Agent",
        "description": (
            "Writes code, fixes bugs, creates SQL queries, manages GitHub repos, "
            "creates PRs and checks CI status."
        ),
        "skills": ["github", "self-improving-agent"],
        "tools": {"profile": "coding", "allow": ["group:fs", "group:runtime", "exec",
                                                   "group:sessions"]},
        "action_class": ["CODE_GEN"],
        "triggers": ["code", "script", "python", "javascript", "sql", "query", "function",
                     "bug", "fix", "github", "pr", "pull request", "repo", "algorithm",
                     "implement", "build", "write a"],
    },

    {
        "name": "Document Agent",
        "description": (
            "Creates, edits and formats documents, reports, proposals. "
            "Exports to Google Docs, Drive. Makes AI drafts sound human."
        ),
        "skills": ["gog", "humanizer", "humanize-ai-text", "summarize"],
        "tools": {"profile": "coding", "allow": ["group:fs", "group:messaging"]},
        "action_class": ["DOC_EDIT"],
        "triggers": ["document", "report", "proposal", "draft", "write up", "meeting notes",
                     "update the", "edit", "format", "google doc", "summary", "create a"],
    },

    {
        "name": "Smart Home Agent",
        "description": (
            "Controls Home Assistant devices: lights, thermostat, switches, scenes. "
            "Responds to home automation mandates."
        ),
        "skills": ["home-assistant"],
        "tools": {"profile": "coding", "allow": ["group:runtime", "web_fetch"]},
        "action_class": ["SYS_CONFIG"],
        "triggers": ["lights", "thermostat", "home", "turn on", "turn off", "switch",
                     "scene", "automation", "home assistant", "temperature", "blinds",
                     "heating", "lock", "alarm"],
    },

    {
        "name": "Phone & SMS Agent",
        "description": (
            "Makes calls and sends SMS from user's own Android phone via Aster. "
            "Sends business SMS via Twilio. Reads incoming SMS."
        ),
        "skills": ["aster", "twilio-api"],
        "tools": {"profile": "messaging", "allow": ["group:messaging"]},
        "action_class": ["COMM_SEND"],
        "triggers": ["call", "phone call", "sms", "text message", "ring", "dial",
                     "make a call", "send sms", "text bob", "call bob"],
    },

    {
        "name": "General Assistant",
        "description": (
            "Handles mixed or unclear mandates. Uses the ontology skill "
            "for structured knowledge and the assistant skill for behaviour."
        ),
        "skills": ["assistant", "ontology", "summarize"],
        "tools": {"profile": "full", "allow": ["group:messaging", "group:web"]},
        "action_class": ["DRAFT_ONLY"],
        "triggers": [],   # catch-all — used when no other agent matches
    },
]


# ── Trigger matching ──────────────────────────────────────────────────────────

def score_agent_for_mandate(
    agent_def: dict,
    intent: str,
    action_class: str,
) -> float:
    """Score an agent definition against a mandate intent.

    Returns 0.0–1.0. Higher = better fit.
    """
    intent_lower = intent.lower()
    score = 0.0

    # Action class match (most important signal)
    if action_class in agent_def.get("action_class", []):
        score += 5.0

    # Trigger keyword match
    triggers = agent_def.get("triggers", [])
    trigger_hits = sum(1 for t in triggers if t in intent_lower)
    score += trigger_hits * 2.0

    # Description word overlap (weak signal)
    desc_words = set(agent_def.get("description", "").lower().split())
    intent_words = set(intent_lower.split())
    overlap = len(desc_words & intent_words)
    score += overlap * 0.3

    return round(score, 2)


async def provision_predefined_agents(tenant_id: str) -> int:
    """Insert pre-defined agents into MongoDB for a tenant.

    Idempotent — skips agents that already exist by name.
    Returns number of newly inserted agents.
    """
    from core.database import get_db
    import uuid
    from datetime import datetime, timezone

    db = get_db()
    inserted = 0

    for agent_def in PREDEFINED_AGENTS:
        existing = await db.agents.find_one(
            {"tenant_id": tenant_id, "name": agent_def["name"]},
        )
        if existing:
            continue

        agent_id = f"agent_{agent_def['name'].lower().replace(' ', '_')[:20]}_{uuid.uuid4().hex[:6]}"
        doc = {
            "agent_id": agent_id,
            "tenant_id": tenant_id,
            "name": agent_def["name"],
            "description": agent_def["description"],
            "skills": agent_def["skills"],
            "tools": agent_def["tools"],
            "action_class": agent_def["action_class"],
            "triggers": agent_def.get("triggers", []),
            "status": "ACTIVE",
            "created_at": datetime.now(timezone.utc),
            "source": "predefined",
        }
        await db.agents.insert_one(doc)
        inserted += 1

    return inserted
