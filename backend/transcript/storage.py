"""Transcript storage — persist transcripts to MongoDB."""
import logging
from core.database import get_db
from transcript.assembler import TranscriptState

logger = logging.getLogger(__name__)


async def save_transcript(state: TranscriptState) -> None:
    """Persist a transcript state to MongoDB."""
    db = get_db()
    doc = state.to_doc()
    await db.transcripts.update_one(
        {"session_id": state.session_id},
        {"$set": doc},
        upsert=True,
    )
    logger.info(
        "Transcript saved: session=%s fragments=%d",
        state.session_id, len(state.fragments),
    )
