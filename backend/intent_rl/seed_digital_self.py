"""Digital Self Mock Data for RL Test User.

Seeds the rl_test_user's Digital Self with realistic entities, facts,
preferences, and routines so that:
  1. Memory recall returns relevant context during intent extraction
  2. The LLM can resolve ambiguous references ("Sarah" → Sarah Johnson, manager)
  3. Fragments like "send Bob the thing" get enriched with real context

This data covers all 100 test cases — every person/entity referenced
in the fragments has a corresponding Digital Self entry.
"""
import logging

logger = logging.getLogger(__name__)

RL_USER_ID = "rl_test_user"

# ── Entities (people, places) ────────────────────────────────────────────────

MOCK_ENTITIES = [
    # Work contacts
    {"name": "Sarah Johnson", "aliases": ["Sarah", "SJ"], "entity_type": "PERSON",
     "data": {"relationship": "manager", "email": "sarah.j@company.com", "phone": "+1-555-0101", "company": "Acme Corp", "role": "Engineering Manager"}},
    {"name": "Bob Chen", "aliases": ["Bob", "Bobby"], "entity_type": "PERSON",
     "data": {"relationship": "colleague", "email": "bob.chen@company.com", "phone": "+1-555-0102", "department": "Finance"}},
    {"name": "Mike Wilson", "aliases": ["Mike", "Mikey"], "entity_type": "PERSON",
     "data": {"relationship": "colleague", "email": "mike.w@company.com", "phone": "+1-555-0103", "department": "Engineering"}},
    {"name": "Lisa Anderson", "aliases": ["Lisa"], "entity_type": "PERSON",
     "data": {"relationship": "direct_report", "email": "lisa.a@company.com", "phone": "+1-555-0104", "role": "Senior Developer"}},
    {"name": "John Park", "aliases": ["John", "JP"], "entity_type": "PERSON",
     "data": {"relationship": "colleague", "email": "john.park@company.com", "phone": "+1-555-0105", "department": "Sales"}},
    {"name": "Alex Kim", "aliases": ["Alex"], "entity_type": "PERSON",
     "data": {"relationship": "friend", "email": "alex.kim@gmail.com", "phone": "+1-555-0201", "context": "college friend"}},
    {"name": "Jess Thompson", "aliases": ["Jess", "Jessica"], "entity_type": "PERSON",
     "data": {"relationship": "colleague", "email": "jess.t@company.com", "department": "Product"}},
    {"name": "Emma Davis", "aliases": ["Emma", "Mom"], "entity_type": "PERSON",
     "data": {"relationship": "family", "phone": "+1-555-0301", "context": "mother"}},
    # Business contacts
    {"name": "Johnson & Co", "aliases": ["Johnson"], "entity_type": "ORGANIZATION",
     "data": {"relationship": "client", "contact": "proposal@johnson.co", "context": "pending proposal"}},
    {"name": "Acme Corp", "aliases": ["Acme", "the company"], "entity_type": "ORGANIZATION",
     "data": {"relationship": "employer", "industry": "Technology"}},
    {"name": "Design Agency", "aliases": ["the design agency"], "entity_type": "ORGANIZATION",
     "data": {"relationship": "vendor", "contact": "info@designagency.com", "project": "rebranding"}},
]

# ── Facts & Preferences ──────────────────────────────────────────────────────

MOCK_FACTS = [
    # Identity
    {"text": "My name is Chris. I work as a Product Manager at Acme Corp.", "fact_type": "IDENTITY", "provenance": "ONBOARDING"},
    {"text": "My timezone is America/New_York (EST/EDT).", "fact_type": "PREFERENCE", "provenance": "ONBOARDING"},
    {"text": "I prefer concise and direct communication style.", "fact_type": "PREFERENCE", "provenance": "ONBOARDING"},
    # Work patterns
    {"text": "I send weekly status reports every Friday afternoon to Sarah Johnson.", "fact_type": "PATTERN", "provenance": "OBSERVED"},
    {"text": "I have a daily standup with the engineering team at 10am.", "fact_type": "ROUTINE", "provenance": "ONBOARDING"},
    {"text": "I have a recurring 1-on-1 with Lisa every Monday at 10am.", "fact_type": "ROUTINE", "provenance": "ONBOARDING"},
    {"text": "I have a weekly team sync every Wednesday at 2pm.", "fact_type": "ROUTINE", "provenance": "ONBOARDING"},
    {"text": "I have a sprint review every other Friday at 11am.", "fact_type": "ROUTINE", "provenance": "OBSERVED"},
    {"text": "I usually block Friday afternoons for deep work.", "fact_type": "PATTERN", "provenance": "OBSERVED"},
    # Financial
    {"text": "I use autopay for rent on the 1st of each month.", "fact_type": "PATTERN", "provenance": "EXPLICIT"},
    {"text": "My Netflix subscription costs $15.99/month.", "fact_type": "FACT", "provenance": "OBSERVED"},
    {"text": "I track business expenses for reimbursement.", "fact_type": "PREFERENCE", "provenance": "EXPLICIT"},
    # Technical
    {"text": "I work mainly with Python, TypeScript, and SQL.", "fact_type": "PREFERENCE", "provenance": "OBSERVED"},
    {"text": "Our main product uses a FastAPI backend and React frontend.", "fact_type": "FACT", "provenance": "OBSERVED"},
    {"text": "We use Stripe for payment processing.", "fact_type": "FACT", "provenance": "OBSERVED"},
    # Projects
    {"text": "I'm working on the Q3 budget proposal with Bob from Finance.", "fact_type": "FACT", "provenance": "OBSERVED"},
    {"text": "The Johnson proposal is due next Wednesday.", "fact_type": "FACT", "provenance": "OBSERVED"},
    {"text": "Our lease at the current office expires in September 2026.", "fact_type": "FACT", "provenance": "EXPLICIT"},
    {"text": "We recently launched a new product and need to announce it on social media.", "fact_type": "FACT", "provenance": "OBSERVED"},
    # Personal
    {"text": "I have a gym membership at FitLife Gym. They close at 10pm on weekdays.", "fact_type": "FACT", "provenance": "EXPLICIT"},
    {"text": "Sarah Johnson's birthday is next Tuesday.", "fact_type": "FACT", "provenance": "EXPLICIT"},
    {"text": "I owe Lisa $50 from dinner last week.", "fact_type": "FACT", "provenance": "EXPLICIT"},
    {"text": "My doctor is Dr. Williams at City Medical Center, phone +1-555-9000.", "fact_type": "FACT", "provenance": "ONBOARDING"},
    {"text": "I'm interested in Bitcoin and track cryptocurrency prices.", "fact_type": "INTEREST", "provenance": "OBSERVED"},
    # Tasks
    {"text": "I need to renew the company domain name before March.", "fact_type": "FACT", "provenance": "OBSERVED"},
    {"text": "The new hire starts next Monday and needs onboarding.", "fact_type": "FACT", "provenance": "OBSERVED"},
    {"text": "I attended a tech conference last week and got several business cards.", "fact_type": "FACT", "provenance": "OBSERVED"},
]


async def seed_digital_self() -> dict:
    """Seed the RL test user's Digital Self with mock data.

    Returns stats about what was stored.
    """
    from memory.retriever import store_fact, register_entity

    stats = {"entities": 0, "facts": 0, "errors": 0}

    # 1. Register entities
    for entity in MOCK_ENTITIES:
        try:
            await register_entity(
                user_id=RL_USER_ID,
                entity_type=entity["entity_type"],
                name=entity["name"],
                aliases=entity.get("aliases", []),
                data=entity.get("data", {}),
                provenance="ONBOARDING",
            )
            stats["entities"] += 1
        except Exception as e:
            logger.warning("Failed to register entity %s: %s", entity["name"], e)
            stats["errors"] += 1

    # 2. Store facts
    for fact in MOCK_FACTS:
        try:
            await store_fact(
                user_id=RL_USER_ID,
                text=fact["text"],
                fact_type=fact["fact_type"],
                provenance=fact["provenance"],
            )
            stats["facts"] += 1
        except Exception as e:
            logger.warning("Failed to store fact: %s", e)
            stats["errors"] += 1

    logger.info(
        "[RL Seed] Digital Self seeded: entities=%d facts=%d errors=%d",
        stats["entities"], stats["facts"], stats["errors"],
    )
    return stats


async def clear_digital_self() -> dict:
    """Clear the RL test user's Digital Self (for clean re-runs)."""
    from memory.client import vector, graph, kv
    from core.database import get_db

    db = get_db()

    # Clear vector store entries for this user
    try:
        all_docs = vector._collection.get(where={"user_id": RL_USER_ID})
        if all_docs and all_docs["ids"]:
            vector._collection.delete(ids=all_docs["ids"])
            deleted_vectors = len(all_docs["ids"])
        else:
            deleted_vectors = 0
    except Exception:
        deleted_vectors = 0

    # Clear graph
    if RL_USER_ID in graph._graphs:
        del graph._graphs[RL_USER_ID]

    # Clear from MongoDB
    del_graph = await db.graphs.delete_many({"user_id": RL_USER_ID})
    del_entities = await db.entity_registry.delete_many({"user_id": RL_USER_ID})

    stats = {
        "vectors_deleted": deleted_vectors,
        "graph_docs_deleted": del_graph.deleted_count,
        "entities_deleted": del_entities.deleted_count,
    }
    logger.info("[RL Seed] Digital Self cleared: %s", stats)
    return stats
