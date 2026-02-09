"""Prompt snapshot persistence — MongoDB.

Stores every PromptReport in `prompt_snapshots` collection.
"""
import logging
from core.database import get_db
from prompting.types import PromptReport

logger = logging.getLogger(__name__)


async def save_prompt_snapshot(report: PromptReport) -> None:
    """Persist a prompt report to MongoDB."""
    db = get_db()
    doc = report.to_doc()
    await db.prompt_snapshots.insert_one(doc)
    logger.info(
        "Prompt snapshot saved: id=%s purpose=%s sections=%d budget=%d",
        report.prompt_id,
        report.purpose.value,
        len(report.sections),
        report.budget_used,
    )


async def get_prompt_snapshot(prompt_id: str) -> dict | None:
    """Retrieve a prompt snapshot by ID."""
    db = get_db()
    doc = await db.prompt_snapshots.find_one({"prompt_id": prompt_id})
    if doc:
        doc.pop("_id", None)
    return doc
