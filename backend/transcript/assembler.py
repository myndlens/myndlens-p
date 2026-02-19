"""Transcript Assembler — B4.

Assembles partial transcript fragments into a coherent transcript.
Tracks evidence spans for grounding.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from stt.provider.interface import TranscriptFragment
from transcript.spans import EvidenceSpan, create_span

logger = logging.getLogger(__name__)


class TranscriptState:
    """Running transcript state for a session."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.fragments: List[TranscriptFragment] = []
        self.spans: List[EvidenceSpan] = []
        self.full_text: str = ""
        self.is_finalized: bool = False
        self.created_at: datetime = datetime.now(timezone.utc)
        self.updated_at: datetime = datetime.now(timezone.utc)

    def add_fragment(self, fragment: TranscriptFragment) -> EvidenceSpan:
        """Add a transcript fragment and create an evidence span."""
        self.fragments.append(fragment)

        span = create_span(
            fragment_id=fragment.fragment_id,
            text=fragment.text,
            start_time=fragment.start_time,
            end_time=fragment.end_time,
            confidence=fragment.confidence,
            is_final=fragment.is_final,
        )
        self.spans.append(span)

        # Update full text
        if fragment.is_final:
            self.full_text = fragment.text
            self.is_finalized = True
        else:
            # Assemble from non-final fragments
            partial_texts = [f.text for f in self.fragments if not f.is_final]
            self.full_text = " ".join(partial_texts)

        self.updated_at = datetime.now(timezone.utc)

        logger.debug(
            "Transcript updated: session=%s fragments=%d text='%s'",
            self.session_id, len(self.fragments), self.full_text[:80],
        )
        return span

    def get_current_text(self) -> str:
        """Get the current assembled text."""
        return self.full_text

    def get_spans(self) -> List[EvidenceSpan]:
        """Get all evidence spans."""
        return self.spans

    def to_doc(self) -> dict:
        """Serialize for MongoDB storage."""
        return {
            "session_id": self.session_id,
            "full_text": self.full_text,
            "fragment_count": len(self.fragments),
            "span_count": len(self.spans),
            "is_finalized": self.is_finalized,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "spans": [s.to_dict() for s in self.spans],
        }


class TranscriptAssembler:
    """Manages transcript state for all active sessions."""

    def __init__(self):
        self._sessions: Dict[str, TranscriptState] = {}

    def get_or_create(self, session_id: str) -> TranscriptState:
        """Get or create transcript state for a session."""
        if session_id not in self._sessions:
            self._sessions[session_id] = TranscriptState(session_id)
            logger.info("Transcript state created: session=%s", session_id)
        return self._sessions[session_id]

    def add_fragment(
        self, session_id: str, fragment: TranscriptFragment
    ) -> tuple[TranscriptState, EvidenceSpan]:
        """Add a fragment to a session's transcript."""
        state = self.get_or_create(session_id)
        span = state.add_fragment(fragment)
        return state, span

    def finalize(self, session_id: str) -> Optional[TranscriptState]:
        """Finalize and remove a session's transcript."""
        state = self._sessions.pop(session_id, None)
        if state:
            state.is_finalized = True
            logger.info(
                "Transcript finalized: session=%s text='%s'",
                session_id, state.full_text[:80],
            )
        return state

    def cleanup(self, session_id: str) -> None:
        """Remove a session's transcript state."""
        self._sessions.pop(session_id, None)


# Singleton
transcript_assembler = TranscriptAssembler()
