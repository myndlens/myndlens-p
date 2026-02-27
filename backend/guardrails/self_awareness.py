"""MyndLens Self-Awareness — answers questions about itself.

Detects meta-questions (about MyndLens, how it works, trust, privacy)
and returns direct answers without running the full mandate pipeline.

Called BEFORE L1 Scout in _send_mock_tts_response.
"""
import re
import logging

logger = logging.getLogger(__name__)

# Pattern → response pairs. Checked in order — first match wins.
_SELF_AWARENESS = [
    {
        "patterns": [
            r"how.*(?:do|does).*(?:myndlens|you).*work",
            r"what.*(?:is|are).*myndlens",
            r"explain.*(?:myndlens|yourself)",
            r"tell.*(?:me|us).*about.*(?:myndlens|yourself)",
        ],
        "response": (
            "I'm MyndLens, your voice-first Personal Cognitive Proxy. "
            "You speak your thoughts — even fragmented ones — and I listen, understand, and build a clear intent. "
            "I check with your Digital Self — your personal intelligence built from your contacts, conversations, and patterns — "
            "to fill in the gaps. Then I create a structured mandate and ask for your approval before executing anything. "
            "I use OpenClaw as my execution engine, and I never act without your permission."
        ),
    },
    {
        "patterns": [
            r"(?:why|what).*(?:unique|different|special).*(?:myndlens|you)",
            r"how.*(?:myndlens|you).*different",
            r"what.*(?:sets|makes).*(?:myndlens|you).*(?:apart|different|unique)",
        ],
        "response": (
            "Three things make me different. "
            "First, I'm Context Aware — you think out loud, and I capture fragmented thoughts into clear intent. No typing, no menus. "
            "Second, I have your Digital Self — I know your relationships, your active conversations, your pending commitments. "
            "I don't ask you to repeat context you've already shared with others. "
            "Third, sovereign execution — your data stays under your control, confidential contacts are biometric-locked, "
            "and I never execute anything without your explicit approval."
        ),
    },
    {
        "patterns": [
            r"(?:can|how).*(?:i|we).*trust.*(?:myndlens|you)",
            r"(?:why|should).*(?:i|we).*trust.*(?:myndlens|you)",
            r"(?:is|are).*(?:myndlens|you).*(?:safe|secure|trustworthy|private)",
            r"(?:what|where).*(?:my|our).*data",
            r"(?:do|does).*(?:myndlens|you).*(?:sell|share|leak).*data",
        ],
        "response": (
            "Trust is built into my architecture. "
            "Your Digital Self is processed on your device by default — raw messages are never stored after processing. "
            "You control what's confidential — those contacts are sealed behind biometric authentication. "
            "I never execute a mandate without your approval — you always see what I'm about to do and say Yes or Change. "
            "Your OpenClaw workspace is isolated — no other user can access your data or your agent. "
            "And you can delete everything at any time from Settings."
        ),
    },
    {
        "patterns": [
            r"what.*(?:can|could).*(?:myndlens|you).*do",
            r"what.*(?:are).*(?:your|myndlens).*(?:capabilities|features|skills)",
            r"help.*(?:me|us).*(?:understand|know).*what.*(?:myndlens|you).*(?:can|do)",
        ],
        "response": (
            "I can help you with a lot. "
            "Code — build, run, and test applications. "
            "Communication — draft emails, manage WhatsApp context, schedule follow-ups. "
            "Research — find information, summarize news, track trends. "
            "Travel — plan trips using your preferences from past conversations. "
            "Tasks — manage your to-dos, track what others owe you, remind you of commitments. "
            "And I'm always learning from your Digital Self to get better at understanding what you need."
        ),
    },
    {
        "patterns": [
            r"who.*(?:made|built|created).*(?:myndlens|you)",
            r"who.*(?:is|are).*(?:behind|developing).*(?:myndlens|you)",
        ],
        "response": (
            "I'm built by ObeGee — a team focused on sovereign AI execution. "
            "The vision is simple: your AI assistant should work for you, know your context, "
            "and never act without your permission. That's me."
        ),
    },
]


def check_self_awareness(transcript: str, user_first_name: str = "") -> str | None:
    """Check if the transcript is a meta-question about MyndLens.

    Returns the response text if matched, None otherwise.
    """
    normalized = transcript.lower().strip()

    # Skip if too short or too long (meta-questions are typically 3-15 words)
    words = normalized.split()
    if len(words) < 2 or len(words) > 25:
        return None

    for entry in _SELF_AWARENESS:
        for pattern in entry["patterns"]:
            if re.search(pattern, normalized):
                name_prefix = f"{user_first_name}, " if user_first_name else ""
                response = name_prefix + entry["response"]
                logger.info("[SELF_AWARENESS] matched pattern='%s' transcript='%s'",
                           pattern[:30], normalized[:40])
                return response

    return None
