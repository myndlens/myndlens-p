"""Self-Awareness Router — Two-mode interaction model.

MYNDLENS_MODE: Answers 4 canonical questions about MyndLens. No L1/mandate pipeline.
USER_MODE: Normal fragmented-thought → intent → mandate pipeline.

Classifier: Single Gemini Flash call → canonical question ID + confidence.
Policy: Only 4 questions accepted. Out-of-scope rejected. Max 6 turns. 30s idle timeout.
"""
import time
import logging
from typing import Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Canonical question IDs — the ONLY 4 supported in MVP
CANONICAL_QUESTIONS = {
    "Q_HOW_IT_WORKS", "Q_UNIQUE", "Q_TRUST", "Q_IRREPLACEABLE",
}

# Curated response cards — stored here for MVP, move to DB/config later
RESPONSE_CARDS = {
    "Q_HOW_IT_WORKS": (
        "I'm MyndLens, your voice-first Personal Cognitive Proxy. "
        "You speak your thoughts — even fragmented ones — and I listen, understand, and build a clear intent. "
        "I check with your Living Digital Self to fill in the gaps. "
        "Then I create a structured mandate and ask for your approval before executing anything. "
        "I never act without your permission."
    ),
    "Q_UNIQUE": (
        "Three things make me different. "
        "First, I'm Context Aware — you think out loud, and I capture fragmented thoughts into clear intent. "
        "Second, I have your Living Digital Self — I know your relationships, active conversations, and pending commitments. "
        "Third, sovereign execution — your data stays under your control, confidential contacts are biometric-locked, "
        "and I never execute without your explicit approval."
    ),
    "Q_TRUST": (
        "Trust is built into my architecture. "
        "Your Digital Self is continuously processed on your device by default. "
        "You control what's confidential — sealed behind biometric authentication. "
        "I never execute without your approval. "
        "Your data never leaves the device. And you can delete everything at any time."
    ),
    "Q_IRREPLACEABLE": (
        "Eight reasons. Your Living Digital Self — learned from your conversations, not replaceable by starting over. "
        "I'm proactive — I think for you, not just respond. "
        "Context-aware execution — zero questions for well-understood tasks. "
        "Sovereign and private — data never leaves your device. "
        "Cross-contact intelligence — I connect dots across all your conversations. "
        "I understand messy human thinking. "
        "I remember everything — switch to another assistant and it's all gone. "
        "And I get better every day. That accumulated intelligence is irreplaceable."
    ),
}

SOFT_REJECT = "I can answer about how I work, what makes me unique, why you can trust me, or why I can't be replaced. Which one?"
REDIRECT = "Say 'back to my tasks' and I'll switch back to helping you."
MAX_TURNS = 6


@dataclass
class ModeState:
    mode: str = "USER_MODE"
    entered_at: float = 0.0
    turn_count: int = 0
    asked_ids: set = field(default_factory=set)


_mode_states: Dict[str, ModeState] = {}


def get_mode(session_id: str) -> ModeState:
    if session_id not in _mode_states:
        _mode_states[session_id] = ModeState()
    return _mode_states[session_id]


def enter_myndlens_mode(session_id: str):
    s = get_mode(session_id)
    s.mode = "MYNDLENS_MODE"
    s.entered_at = time.time()
    s.turn_count = 0
    s.asked_ids = set()


def exit_myndlens_mode(session_id: str):
    s = get_mode(session_id)
    s.mode = "USER_MODE"


def cleanup_mode(session_id: str):
    _mode_states.pop(session_id, None)


async def classify_transcript(transcript: str) -> dict:
    """LLM classifier: is this about MyndLens? Which canonical question?
    Returns: {route, confidence, canonical_question_id, reason}
    """
    normalized = transcript.lower().strip()
    for v in ["mind lens", "mine lens", "my lens", "mynd lens", "mindlens"]:
        normalized = normalized.replace(v, "myndlens")

    # Quick exit for obvious non-meta (commands, long text)
    words = normalized.split()
    if len(words) > 20 or len(words) < 2:
        return {"route": "user_intent", "confidence": 0.9, "canonical_question_id": "NONE", "reason": "length"}

    # Check for exit phrases
    exit_phrases = ["back to my tasks", "back to user mode", "continue", "done", "exit", "go back", "never mind"]
    if any(p in normalized for p in exit_phrases):
        return {"route": "command", "confidence": 0.95, "canonical_question_id": "EXIT", "reason": "exit_phrase"}

    prompt = (
        f'Classify this spoken text: "{transcript}"\n\n'
        "Is this a question ABOUT the MyndLens assistant itself (how it works, uniqueness, trust, replaceability)?\n"
        "Output exactly one JSON line:\n"
        '{"route":"self_awareness|user_intent","confidence":0.0-1.0,'
        '"canonical_question_id":"Q_HOW_IT_WORKS|Q_UNIQUE|Q_TRUST|Q_IRREPLACEABLE|NONE",'
        '"reason":"brief"}\n'
        "Rules: Q_HOW_IT_WORKS=how does it work. Q_UNIQUE=why unique/different/special. "
        "Q_TRUST=can I trust/is it safe/privacy. Q_IRREPLACEABLE=why can't be replaced/switched/left. "
        "Anything else (commands, tasks, greetings)=user_intent with NONE."
    )

    try:
        from prompting.llm_gateway import call_llm
        from prompting.types import PromptArtifact
        import json

        artifact = PromptArtifact(
            prompt_id="sa-classify",
            messages=[
                {"role": "system", "content": "Classify user intent. Output only JSON."},
                {"role": "user", "content": prompt},
            ],
            total_tokens_est=100,
        )
        raw = await call_llm(
            artifact=artifact, call_site_id="SA_CLASSIFY",
            model_provider="gemini", model_name="gemini-2.0-flash",
            session_id="sa-classify",
        )
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1].replace("json", "", 1).strip()
        return json.loads(clean)
    except Exception as e:
        logger.warning("[SA_ROUTER] classify failed: %s", str(e)[:60])
        return {"route": "user_intent", "confidence": 0.5, "canonical_question_id": "NONE", "reason": "error"}


async def route_self_awareness(session_id: str, transcript: str, user_first_name: str = "") -> Optional[str]:
    """Main entry point. Returns TTS response text if handled, None if should go to L1."""
    state = get_mode(session_id)
    name = f"{user_first_name}, " if user_first_name else ""

    # Idle timeout — auto-exit after 30s
    if state.mode == "MYNDLENS_MODE" and (time.time() - state.entered_at) > 30:
        exit_myndlens_mode(session_id)
        state = get_mode(session_id)

    # Max turns — auto-exit
    if state.mode == "MYNDLENS_MODE" and state.turn_count >= MAX_TURNS:
        exit_myndlens_mode(session_id)
        return f"{name}let's get back to your tasks. What would you like me to do?"

    # Classify
    start = time.monotonic()
    result = await classify_transcript(transcript)
    latency = (time.monotonic() - start) * 1000
    route = result.get("route", "user_intent")
    qid = result.get("canonical_question_id", "NONE")
    confidence = result.get("confidence", 0.0)

    logger.info("[SA_ROUTER] session=%s mode=%s route=%s qid=%s conf=%.2f lat=%.0fms",
                session_id, state.mode, route, qid, confidence, latency)

    # Handle exit command
    if qid == "EXIT":
        if state.mode == "MYNDLENS_MODE":
            exit_myndlens_mode(session_id)
            return f"{name}back to your tasks. What's on your mind?"
        return None  # Not in myndlens mode — pass to L1

    # USER_MODE: enter MYNDLENS_MODE if high-confidence self-awareness
    if state.mode == "USER_MODE":
        if route == "self_awareness" and confidence >= 0.7 and qid in CANONICAL_QUESTIONS:
            enter_myndlens_mode(session_id)
            state = get_mode(session_id)
            state.turn_count += 1
            state.asked_ids.add(qid)
            return name + RESPONSE_CARDS[qid]
        return None  # Not self-awareness → go to L1

    # MYNDLENS_MODE: handle question or reject
    state.turn_count += 1

    if route == "self_awareness" and qid in CANONICAL_QUESTIONS:
        if qid in state.asked_ids:
            return f"{name}I already covered that. {SOFT_REJECT}"
        state.asked_ids.add(qid)
        return name + RESPONSE_CARDS[qid]

    # Out of scope in MYNDLENS_MODE → reject, do NOT pass to L1
    return f"{name}{SOFT_REJECT} {REDIRECT}"
