"""Conversation State Machine — accumulates fragments into a coherent intent.

Tracks the evolving conversation state per session:
  - fragments: raw utterances from the user
  - sub_intents: extracted sub-intents from each fragment
  - checklist: what we know vs what we need
  - questions_asked: total questions asked (hard cap at 3)
  - phase: current conversation phase

Phases:
  LISTENING → ACCUMULATING → PROCESSING → APPROVAL → EXECUTING → DONE
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class ConversationFragment:
    text: str
    timestamp: float
    sub_intents: List[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class ChecklistItem:
    dimension: str      # what/who/when/where/how
    value: Optional[str] = None
    source: str = "unknown"  # "user_said" | "digital_self" | "default"
    filled: bool = False


@dataclass
class ConversationState:
    """Per-session conversation state — lives for one mandate lifecycle."""
    session_id: str
    user_id: str = ""
    user_first_name: str = ""

    # Fragments accumulated across turns
    fragments: List[ConversationFragment] = field(default_factory=list)

    # Combined transcript from all fragments
    combined_transcript: str = ""

    # Checklist of what we know vs what we need
    checklist: List[ChecklistItem] = field(default_factory=list)

    # Question tracking — hard cap at 3
    questions_asked: List[str] = field(default_factory=list)
    questions_remaining: int = 3

    # Phase tracking
    phase: str = "LISTENING"  # LISTENING | ACTIVE_CAPTURE | HELD | RESUMING | PROCESSING | APPROVAL_PENDING | EXECUTING | DONE

    # Timestamps
    created_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    last_fragment_at: float = 0.0

    def add_fragment(self, text: str, sub_intents: List[str] = None, confidence: float = 0.0) -> None:
        """Add a new user utterance fragment."""
        frag = ConversationFragment(
            text=text,
            timestamp=datetime.now(timezone.utc).timestamp(),
            sub_intents=sub_intents or [],
            confidence=confidence,
        )
        self.fragments.append(frag)
        self.last_fragment_at = frag.timestamp

        # Rebuild combined transcript
        self.combined_transcript = " ".join(f.text for f in self.fragments)

        # Update phase
        if self.phase == "LISTENING":
            self.phase = "ACCUMULATING"

        logger.info("[CONV] session=%s fragment=%d text='%s' combined='%s'",
                    self.session_id, len(self.fragments), text[:50], self.combined_transcript[:80])

    def can_ask_question(self) -> bool:
        return self.questions_remaining > 0

    def record_question(self, question: str) -> None:
        self.questions_asked.append(question)
        self.questions_remaining = max(0, 3 - len(self.questions_asked))

    def get_combined_transcript(self) -> str:
        return self.combined_transcript

    def seconds_since_last_fragment(self) -> float:
        if self.last_fragment_at == 0:
            return 0.0
        return datetime.now(timezone.utc).timestamp() - self.last_fragment_at

    def fill_checklist(self, dimension: str, value: str, source: str = "user_said") -> None:
        for item in self.checklist:
            if item.dimension == dimension:
                item.value = value
                item.source = source
                item.filled = True
                return
        self.checklist.append(ChecklistItem(dimension=dimension, value=value, source=source, filled=True))

    def get_unfilled(self) -> List[ChecklistItem]:
        return [item for item in self.checklist if not item.filled]

    def reset(self) -> None:
        """Reset for a new mandate (same session)."""
        self.fragments.clear()
        self.combined_transcript = ""
        self.checklist.clear()
        self.questions_asked.clear()
        self.questions_remaining = 3
        self.phase = "LISTENING"
        self.last_fragment_at = 0.0


# Per-session conversation states
_conversation_states: Dict[str, ConversationState] = {}

# User → session mapping for state migration on reconnect
_user_session_map: Dict[str, str] = {}


def get_or_create_conversation(session_id: str, user_id: str = "", user_first_name: str = "") -> ConversationState:
    if session_id not in _conversation_states:
        _conversation_states[session_id] = ConversationState(
            session_id=session_id,
            user_id=user_id,
            user_first_name=user_first_name,
        )
    # Track user → session for reconnect migration
    if user_id:
        _user_session_map[user_id] = session_id
    return _conversation_states[session_id]


def migrate_conversation_for_user(user_id: str, new_session_id: str) -> bool:
    """Migrate active conversation state from old session to new session on reconnect.
    Returns True if fragments were migrated."""
    old_session_id = _user_session_map.get(user_id)
    if not old_session_id or old_session_id == new_session_id:
        return False
    old_state = _conversation_states.get(old_session_id)
    if not old_state or not old_state.fragments:
        return False

    logger.info("[CONV:MIGRATE] user=%s old_session=%s → new_session=%s fragments=%d",
                user_id, old_session_id, new_session_id, len(old_state.fragments))

    # Create new state with old fragments
    new_state = ConversationState(
        session_id=new_session_id,
        user_id=user_id,
        user_first_name=old_state.user_first_name,
    )
    new_state.fragments = old_state.fragments
    new_state.combined_transcript = old_state.combined_transcript
    new_state.checklist = old_state.checklist
    new_state.questions_remaining = old_state.questions_remaining
    new_state.questions_asked = old_state.questions_asked
    new_state.phase = old_state.phase
    new_state.last_fragment_at = old_state.last_fragment_at
    new_state.created_at = old_state.created_at  # Preserve capture start time for 5-min cap

    _conversation_states[new_session_id] = new_state
    _user_session_map[user_id] = new_session_id

    # Cleanup old session
    _conversation_states.pop(old_session_id, None)
    return True


def reset_conversation(session_id: str) -> None:
    state = _conversation_states.get(session_id)
    if state:
        state.reset()


def cleanup_conversation(session_id: str) -> None:
    _conversation_states.pop(session_id, None)
