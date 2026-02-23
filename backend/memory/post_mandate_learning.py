"""Post-Mandate Digital Self Learning — every completed mandate enriches the DS.

When a mandate completes:
  "User booked Hilton Sydney, business class Qantas, Hertz sedan"
  → DS learns: hotel_pref=Hilton, airline=Qantas, car=Hertz sedan

Next time user says "Sydney trip" → all of these are auto-filled.
The DS grows with every interaction. Questions shrink to near-zero.
"""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def learn_from_mandate(user_id: str, mandate: Dict[str, Any]) -> Dict[str, int]:
    """Extract learnable facts from a completed mandate and store in Digital Self.

    Only learns from dimensions with source 'stated' (user explicitly said it)
    — these are new preferences the DS didn't know before.
    Does NOT re-store 'digital_self' sourced dims (already known).
    """
    from memory.retriever import store_fact

    learned = 0
    skipped = 0
    intent = mandate.get("intent", "")

    for action in mandate.get("actions", []):
        action_name = action.get("action", "")
        dims = action.get("dimensions", {})

        for dim_name, dim_val in dims.items():
            if not isinstance(dim_val, dict):
                continue

            source = dim_val.get("source", "")
            value = dim_val.get("value", "")

            if not value or value == "missing":
                continue

            # Only learn NEW info the user stated or confirmed
            # Skip what DS already knew and what was inferred
            if source in ("stated", "confirmed"):
                fact_text = f"For {intent} → {action_name}: user prefers {dim_name} = {value}"

                await store_fact(
                    user_id=user_id,
                    text=fact_text,
                    fact_type="PREFERENCE",
                    provenance="POST_MANDATE",
                    metadata={
                        "intent": intent,
                        "action": action_name,
                        "dimension": dim_name,
                        "value": value,
                    },
                )
                learned += 1
            else:
                skipped += 1

    # Also learn people involved
    for person in mandate.get("people", []):
        name = person.get("name", "")
        role = person.get("role", "")
        contact = person.get("contact", "")
        if name and contact and contact != "missing":
            await store_fact(
                user_id=user_id,
                text=f"{name} ({role}): {contact}",
                fact_type="ENTITY",
                provenance="POST_MANDATE",
                metadata={"name": name, "role": role, "contact": contact},
            )
            learned += 1

    logger.info(
        "[DS Learn] user=%s intent=%s learned=%d skipped=%d",
        user_id, intent, learned, skipped,
    )
    return {"learned": learned, "skipped": skipped}
