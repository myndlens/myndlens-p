"""Digital Self Ingest — stores extraction results into RAG vector store.

Takes the distilled contact intelligence (from WhatsApp/Gmail extraction)
and stores it as vector documents so that L1 Scout, Dimension Extractor,
and Micro Questions can recall them during mandate processing.

Each contact produces multiple vector documents:
  - Identity doc: "Jacob is CMO at Acme, close colleague, inner circle #2"
  - Per active thread: "Planning Sydney conference trip with Jacob, flights undecided"
  - Pending actions: "User owes Jacob: send budget spreadsheet by Friday"
  - Aspirations: "User wants to launch APAC expansion Q2"

Confidential contacts are stored with confidential=true in metadata.
RAG queries filter them out unless biometric-unlocked.
"""
import logging
from typing import Any, Dict, List

from memory.client.vector import add_document

logger = logging.getLogger(__name__)


def ingest_contact(user_id: str, contact: Dict[str, Any]) -> int:
    """Ingest a single distilled contact into the vector store.
    Returns number of documents added.
    """
    identity = contact.get("identity", {})
    name = identity.get("name", "unknown")
    phone = identity.get("phone", identity.get("email", ""))
    relationship = identity.get("relationship", "unknown")
    confidential = identity.get("confidential", False)
    source = contact.get("source", "unknown")
    rank = contact.get("inner_circle_rank", 99)

    base_meta = {
        "user_id": user_id,
        "contact_name": name,
        "contact_id": phone,
        "source": source,
        "confidential": confidential,
        "inner_circle_rank": rank,
    }

    docs_added = 0
    slug = name.lower().replace(" ", "_").replace("@", "_at_")[:30]

    # 1. Identity document
    identity_text = f"{name} is {relationship}."
    nicknames = identity.get("nicknames", [])
    if nicknames:
        identity_text += f" Also known as: {', '.join(nicknames)}."
    pattern = contact.get("pattern", {})
    if pattern.get("frequency"):
        identity_text += f" Communication: {pattern['frequency']}."
    if pattern.get("style") and pattern["style"] != "unknown":
        identity_text += f" Style: {pattern['style']}."
    sentiment = contact.get("sentiment", "")
    if sentiment and sentiment != "unknown":
        identity_text += f" Relationship sentiment: {sentiment}."

    add_document(
        doc_id=f"ds_{source}_{slug}_identity",
        text=identity_text,
        metadata={**base_meta, "doc_type": "identity"},
    )
    docs_added += 1

    # 2. Active threads — each thread is a separate document (high recall priority)
    for i, thread in enumerate(contact.get("active_threads", [])[:5]):
        topic = thread.get("topic", "")
        thread_type = thread.get("type", "")
        status = thread.get("status", "")
        tension = thread.get("tension_level", "none")

        thread_text = f"Active {thread_type.lower()} with {name}: {topic}."
        if status:
            thread_text += f" Status: {status}."
        decided = thread.get("decided", [])
        if decided:
            thread_text += f" Decided: {', '.join(decided)}."
        undecided = thread.get("undecided", [])
        if undecided:
            thread_text += f" Still open: {', '.join(undecided)}."
        user_action = thread.get("user_action", "")
        if user_action:
            thread_text += f" User needs to: {user_action}."
        their_action = thread.get("their_action", "")
        if their_action:
            thread_text += f" {name} needs to: {their_action}."
        deadline = thread.get("deadline")
        if deadline:
            thread_text += f" Deadline: {deadline}."
        if tension and tension != "none":
            thread_text += f" Tension level: {tension}."

        add_document(
            doc_id=f"ds_{source}_{slug}_thread_{i}",
            text=thread_text,
            metadata={**base_meta, "doc_type": "active_thread", "thread_type": thread_type, "tension": tension},
        )
        docs_added += 1

    # 3. Pending actions — user owes and they owe
    pending = contact.get("pending_actions", {})
    user_owes = pending.get("user_owes", [])
    they_owe = pending.get("they_owe", [])

    if user_owes:
        text = f"User owes {name}: {'; '.join(user_owes)}."
        add_document(
            doc_id=f"ds_{source}_{slug}_user_owes",
            text=text,
            metadata={**base_meta, "doc_type": "pending_action", "direction": "user_owes"},
        )
        docs_added += 1

    if they_owe:
        text = f"{name} owes user: {'; '.join(they_owe)}."
        add_document(
            doc_id=f"ds_{source}_{slug}_they_owe",
            text=text,
            metadata={**base_meta, "doc_type": "pending_action", "direction": "they_owe"},
        )
        docs_added += 1

    # 4. Aspirations
    aspirations = contact.get("aspirations_mentioned", [])
    if aspirations:
        text = f"Aspirations mentioned with {name}: {'; '.join(aspirations)}."
        add_document(
            doc_id=f"ds_{source}_{slug}_aspirations",
            text=text,
            metadata={**base_meta, "doc_type": "aspiration"},
        )
        docs_added += 1

    # 5. Emotional context
    emo = contact.get("emotional_context", {})
    mood = emo.get("current_mood", "")
    events = emo.get("recent_events", [])
    if mood and mood != "unknown":
        text = f"Relationship with {name}: {mood}."
        if events:
            text += f" Recent: {'; '.join(events)}."
        add_document(
            doc_id=f"ds_{source}_{slug}_emotional",
            text=text,
            metadata={**base_meta, "doc_type": "emotional_context"},
        )
        docs_added += 1

    logger.info("[DS_INGEST] user=%s contact=%s docs=%d confidential=%s",
                user_id, name, docs_added, confidential)
    return docs_added


def ingest_extraction_results(user_id: str, contacts: List[Dict[str, Any]], source: str = "unknown") -> Dict[str, int]:
    """Ingest all contacts from a DS extraction into the vector store.
    Returns stats: { contacts_ingested, documents_added }
    """
    total_docs = 0
    total_contacts = 0

    for contact in contacts:
        if not contact.get("identity", {}).get("name"):
            continue
        # Set source if not already set
        if "source" not in contact:
            contact["source"] = source
        docs = ingest_contact(user_id, contact)
        total_docs += docs
        total_contacts += 1

    logger.info("[DS_INGEST] user=%s source=%s contacts=%d docs=%d",
                user_id, source, total_contacts, total_docs)
    return {"contacts_ingested": total_contacts, "documents_added": total_docs}
