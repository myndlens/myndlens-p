"""Deepgram STT Provider — Managed API adapter.

Batch 3: Real STT integration behind the provider interface.
Uses Deepgram's pre-recorded REST API with buffered chunks.

Strategy: Accumulate audio chunks in a buffer per session.
Every N chunks (~1s of audio), send buffer to Deepgram REST API.
On stream end, send remaining buffer for final transcription.

STT provides ONLY: transcript fragments + confidence + latency.
STT does NOT provide: intent inference, VAD, emotion inference.
"""
from config.settings import get_settings
from deepgram import DeepgramClient as _DeepgramClient
import asyncio
import io
import wave
import logging
import time
import uuid
from typing import Dict, List, Optional

from stt.provider.interface import STTProvider, TranscriptFragment

logger = logging.getLogger(__name__)

# Transcribe every N chunks (~1 second of audio at 250ms/chunk)
CHUNKS_PER_BATCH = 4
MIN_BUFFER_BYTES = 512  # Don't send tiny buffers


class _DeepgramStreamState:
    """Per-session state for buffered Deepgram transcription."""
    def __init__(self):
        self.audio_buffer: bytearray = bytearray()
        self.chunk_count: int = 0
        self.total_bytes: int = 0
        self.accumulated_text: List[str] = []
        self.last_confidence: float = 0.0


class DeepgramSTTProvider(STTProvider):
    """Real Deepgram STT using pre-recorded REST API with chunk batching."""

    def __init__(self):
        self._streams: Dict[str, _DeepgramStreamState] = {}
        self._client = None
        self._init_client()

    def _init_client(self):
        """Initialize the Deepgram client."""
        try:
            import os
            settings = get_settings()
            api_key = settings.DEEPGRAM_API_KEY
            if not api_key:
                logger.error("[DeepgramSTT] No API key configured")
                return
            # SDK v5.x reads from DEEPGRAM_API_KEY env var
            os.environ["DEEPGRAM_API_KEY"] = api_key
            self._client = _DeepgramClient()
            logger.info("[DeepgramSTT] Client initialized")
        except Exception as e:
            logger.error("[DeepgramSTT] Failed to initialize: %s", str(e))

    async def start_stream(self, session_id: str) -> None:
        self._streams[session_id] = _DeepgramStreamState()
        logger.info("[DeepgramSTT] Stream started: session=%s", session_id)

    async def feed_audio(
        self, session_id: str, chunk: bytes, seq: int
    ) -> Optional[TranscriptFragment]:
        state = self._streams.get(session_id)
        if state is None:
            await self.start_stream(session_id)
            state = self._streams[session_id]

        # Accumulate chunk
        state.audio_buffer.extend(chunk)
        state.chunk_count += 1
        state.total_bytes += len(chunk)

        # Transcribe every CHUNKS_PER_BATCH chunks
        if state.chunk_count % CHUNKS_PER_BATCH == 0 and len(state.audio_buffer) >= MIN_BUFFER_BYTES:
            fragment = await self._transcribe_buffer(session_id, state, is_final=False)
            return fragment

        return None

    async def end_stream(self, session_id: str) -> Optional[TranscriptFragment]:
        state = self._streams.pop(session_id, None)
        if state is None:
            return None

        # Transcribe any remaining audio
        if len(state.audio_buffer) >= MIN_BUFFER_BYTES:
            fragment = await self._transcribe_buffer(session_id, state, is_final=True)
            if fragment:
                return fragment

        # Return accumulated text as final if we have anything
        if state.accumulated_text:
            full_text = " ".join(state.accumulated_text)
            return TranscriptFragment(
                text=full_text,
                confidence=state.last_confidence,
                is_final=True,
                latency_ms=0,
                fragment_id=str(uuid.uuid4()),
            )

        logger.info("[DeepgramSTT] Stream ended: session=%s (no text)", session_id)
        return None

    async def is_healthy(self) -> bool:
        return self._client is not None

    async def _transcribe_buffer(
        self, session_id: str, state: _DeepgramStreamState, is_final: bool
    ) -> Optional[TranscriptFragment]:
        """Send accumulated buffer to Deepgram REST API."""
        if not self._client:
            logger.error("[DeepgramSTT] Client not initialized")
            return None

        buffer_data = bytes(state.audio_buffer)
        state.audio_buffer.clear()

        start_time = time.monotonic()

        try:
            # Deepgram SDK v5.3.2: wrap PCM in WAV, pass raw bytes (not BytesIO)
            wav_buf = io.BytesIO()
            with wave.open(wav_buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(get_settings().AUDIO_SAMPLE_RATE)
                wf.writeframes(buffer_data)
            wav_bytes = wav_buf.getvalue()

            loop = asyncio.get_running_loop()
            _model = get_settings().DEEPGRAM_MODEL
            _lang  = get_settings().DEEPGRAM_LANGUAGE
            response = await loop.run_in_executor(
                None,
                lambda: self._client.listen.v1.media.transcribe_file(
                    request=wav_bytes,
                    model=_model,
                    punctuate=True,
                    smart_format=True,
                    language=_lang,
                ),
            )

            latency_ms = (time.monotonic() - start_time) * 1000

            # SDK v5 returns Pydantic objects — not dicts
            channels = []
            if hasattr(response, "results") and response.results:
                channels = response.results.channels or []

            if not channels:
                logger.debug("[DeepgramSTT] No channels in response: session=%s", session_id)
                return None

            alternatives = channels[0].alternatives or []
            if not alternatives:
                return None

            text = (alternatives[0].transcript or "").strip()
            confidence = getattr(alternatives[0], "confidence", 0.0) or 0.0

            if not text:
                return None

            state.accumulated_text.append(text)
            state.last_confidence = confidence

            fragment = TranscriptFragment(
                text=text if not is_final else " ".join(state.accumulated_text),
                confidence=confidence,
                is_final=is_final,
                latency_ms=latency_ms,
                start_time=state.chunk_count * 0.25 - 1.0,
                end_time=state.chunk_count * 0.25,
                fragment_id=str(uuid.uuid4()),
            )

            logger.info(
                "[DeepgramSTT] Transcribed: session=%s text='%s' conf=%.2f latency=%.0fms final=%s",
                session_id, text[:50], confidence, latency_ms, is_final,
            )
            return fragment

        except Exception as e:
            latency_ms = (time.monotonic() - start_time) * 1000
            logger.error(
                "[DeepgramSTT] Transcription failed: session=%s error=%s latency=%.0fms",
                session_id, str(e), latency_ms,
            )
            # STT fail → don't crash, return None (caller handles fallback)
            return None
