"""Mock STT provider — deterministic transcript fragments for testing.

Used in Batch 2-3 before real Deepgram integration.
Returns predictable fragments based on chunk sequence numbers.
"""
import asyncio
import logging
import uuid
from typing import Dict, Optional, List

from stt.provider.interface import STTProvider, TranscriptFragment

logger = logging.getLogger(__name__)

# Predefined mock transcript responses keyed by cumulative chunk count
_MOCK_SENTENCES = [
    "Hello",
    "I need to",
    "send a message",
    "to Sarah",
    "about the meeting",
    "tomorrow morning",
    "at nine o'clock",
    "please confirm",
]


class MockSTTProvider(STTProvider):
    """Deterministic mock STT for development and testing."""

    def __init__(self, latency_ms: float = 30.0):
        self._streams: Dict[str, _MockStreamState] = {}
        self._latency_ms = latency_ms

    async def start_stream(self, session_id: str) -> None:
        self._streams[session_id] = _MockStreamState()
        logger.info("[MockSTT] Stream started: session=%s", session_id)

    async def feed_audio(
        self, session_id: str, chunk: bytes, seq: int
    ) -> Optional[TranscriptFragment]:
        state = self._streams.get(session_id)
        if state is None:
            # Auto-start stream if not started
            await self.start_stream(session_id)
            state = self._streams[session_id]

        state.chunk_count += 1
        state.total_bytes += len(chunk)

        # Simulate processing latency
        await asyncio.sleep(self._latency_ms / 1000.0)

        # Emit a partial fragment every 4 chunks (~1 second of audio)
        if state.chunk_count % 4 == 0:
            word_idx = (state.chunk_count // 4 - 1) % len(_MOCK_SENTENCES)
            text = _MOCK_SENTENCES[word_idx]
            state.accumulated_text.append(text)

            fragment = TranscriptFragment(
                text=text,
                confidence=0.92,
                is_final=False,
                latency_ms=self._latency_ms,
                start_time=state.chunk_count * 0.25 - 1.0,
                end_time=state.chunk_count * 0.25,
                fragment_id=str(uuid.uuid4()),
            )
            logger.debug(
                "[MockSTT] Fragment: session=%s seq=%d text='%s'",
                session_id, seq, text,
            )
            return fragment

        return None

    async def end_stream(self, session_id: str) -> Optional[TranscriptFragment]:
        state = self._streams.pop(session_id, None)
        if state is None:
            return None

        if state.accumulated_text:
            full_text = " ".join(state.accumulated_text)
            fragment = TranscriptFragment(
                text=full_text,
                confidence=0.95,
                is_final=True,
                latency_ms=self._latency_ms,
                start_time=0.0,
                end_time=state.chunk_count * 0.25,
                fragment_id=str(uuid.uuid4()),
            )
            logger.info(
                "[MockSTT] Stream ended: session=%s final='%s'",
                session_id, full_text,
            )
            return fragment

        logger.info("[MockSTT] Stream ended: session=%s (no text)", session_id)
        return None

    async def is_healthy(self) -> bool:
        return True


class _MockStreamState:
    """Internal state for a mock STT stream."""
    def __init__(self):
        self.chunk_count: int = 0
        self.total_bytes: int = 0
        self.accumulated_text: List[str] = []
