"""Intent Router — classifies utterances before they enter the intent pipeline.

Routes: intent_fragment | command | noise | interruption | mode_control
Only intent_fragment mutates the conversation checklist and sub-intent graph.
Everything else updates orchestration state without polluting intent.
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RouteDecision:
    route: str  # intent_fragment | command | noise | interruption | mode_control
    confidence: float
    normalized_command: str  # HOLD | RESUME | CANCEL | KILL | NONE
    sub_intents: list = None
    dimensions: dict = None

    def __post_init__(self):
        if self.sub_intents is None:
            self.sub_intents = []
        if self.dimensions is None:
            self.dimensions = {}


# Command phrases — deterministic, no LLM needed
_COMMANDS = {
    "hold": "HOLD", "hold on": "HOLD", "wait": "HOLD", "pause": "HOLD",
    "one moment": "HOLD", "one sec": "HOLD", "hang on": "HOLD",
    "resume": "RESUME", "continue": "RESUME", "go on": "RESUME",
    "i'm back": "RESUME", "im back": "RESUME", "back": "RESUME",
    "cancel": "CANCEL", "stop": "CANCEL", "forget it": "CANCEL", "never mind": "CANCEL",
    "kill": "KILL", "abort": "KILL",
}

# Noise patterns — too short, filler words, non-speech
_NOISE_WORDS = {"um", "uh", "hmm", "ah", "oh", "okay", "ok", "yeah", "yep", "nah", "no", "hey", "hi", "hello"}


async def route_fragment(session_id: str, user_id: str, text: str, context: str = "") -> RouteDecision:
    """Classify an utterance and return routing decision.
    
    Fast path: deterministic command/noise matching (<1ms).
    Slow path: LLM classification only for ambiguous cases.
    """
    normalized = text.lower().strip()
    words = normalized.split()

    # Empty
    if not normalized or len(words) == 0:
        return RouteDecision(route="noise", confidence=1.0, normalized_command="NONE")

    # Single word noise
    if len(words) == 1 and words[0] in _NOISE_WORDS:
        return RouteDecision(route="noise", confidence=0.95, normalized_command="NONE")

    # Two-word noise (filler combos)
    if len(words) <= 2 and all(w in _NOISE_WORDS for w in words):
        return RouteDecision(route="noise", confidence=0.9, normalized_command="NONE")

    # Command matching (deterministic — no LLM)
    for phrase, cmd in _COMMANDS.items():
        if normalized == phrase or normalized.startswith(phrase + " "):
            return RouteDecision(route="command", confidence=0.95, normalized_command=cmd)

    # Interruption patterns
    if normalized in ("excuse me", "sorry", "wait wait", "no no no", "stop stop"):
        return RouteDecision(route="interruption", confidence=0.9, normalized_command="NONE")

    # Default: intent fragment (the common case for actual speech)
    return RouteDecision(route="intent_fragment", confidence=0.8, normalized_command="NONE")
