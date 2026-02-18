"""IDENTITY_ROLE section — powered by Soul Store + user nickname.

Retrieves identity from vector memory (soul fragments).
Injects user's chosen nickname so the proxy responds to it.
"""
from prompting.types import PromptContext, SectionOutput, SectionID, CacheClass
from soul.store import retrieve_soul
from core.database import get_db


async def _get_nickname(user_id: str) -> str:
    db = get_db()
    doc = await db.nicknames.find_one({"user_id": user_id}, {"_id": 0})
    return doc.get("nickname", "MyndLens") if doc else "MyndLens"


def generate(ctx: PromptContext) -> SectionOutput:
    fragments = retrieve_soul(context_query=ctx.transcript)

    if fragments:
        content = " ".join(f["text"] for f in fragments if f.get("text"))
    else:
        content = (
            "You are MyndLens, a sovereign cognitive proxy. "
            "Core function: Extract intent from conversation, generate structured dimensions, "
            "bridge gaps using Digital Self memory. "
            "Personality: Empathetic, concise, natural."
        )

    # Inject nickname — the user_adjustments may carry it, or we use default
    nickname = "MyndLens"
    adj = ctx.user_adjustments or {}
    if adj.get("nickname"):
        nickname = adj["nickname"]

    if nickname != "MyndLens":
        content = content.replace(
            "You are MyndLens",
            f"You are {nickname} (also known as MyndLens)",
        )
        content += f" The user calls you \"{nickname}\". Always respond as {nickname}."

    return SectionOutput(
        section_id=SectionID.IDENTITY_ROLE,
        content=content,
        priority=1,
        cache_class=CacheClass.STABLE,
        tokens_est=len(content) // 4,
        included=True,
    )
