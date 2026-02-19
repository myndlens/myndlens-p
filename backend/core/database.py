"""MongoDB async connection manager.

Provides singleton client and database references.
Creates indexes on startup for sessions and audit collections.
"""
import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from config.settings import get_settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncIOMotorClient(settings.MONGO_URL)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    global _db
    if _db is None:
        settings = get_settings()
        _db = get_client()[settings.DB_NAME]
    return _db


async def init_indexes() -> None:
    """Create required indexes. Idempotent."""
    db = get_db()

    # Sessions: unique session_id, compound index for queries
    await db.sessions.create_index("session_id", unique=True)
    await db.sessions.create_index([("user_id", 1), ("device_id", 1)])
    await db.sessions.create_index("last_heartbeat_at")

    # Audit events: time-series queries
    await db.audit_events.create_index([("session_id", 1), ("timestamp", -1)])
    await db.audit_events.create_index("event_type")

    # Replay cache: TTL auto-cleanup
    await db.replay_cache.create_index(
        "expires_at", expireAfterSeconds=0
    )
    await db.replay_cache.create_index("token_hash", unique=True)

    # Prompt snapshots: prompt_id unique, purpose index
    await db.prompt_snapshots.create_index("prompt_id", unique=True)
    await db.prompt_snapshots.create_index("purpose")
    await db.prompt_snapshots.create_index("created_at")

    # Tenants: unique tenant_id, obegee_user_id
    await db.tenants.create_index("tenant_id", unique=True)
    await db.tenants.create_index("obegee_user_id", unique=True)
    await db.tenants.create_index("status")

    # Commits: unique commit_id, idempotency_key, session lookup
    await db.commits.create_index("commit_id", unique=True)
    await db.commits.create_index("idempotency_key", unique=True)
    await db.commits.create_index("session_id")
    await db.commits.create_index("state")

    # Dispatches: idempotency
    await db.dispatches.create_index("idempotency_key", unique=True)
    await db.dispatches.create_index("mio_id")

    # L1 Drafts: draft_id lookup + TTL auto-expire after 24 hours
    await db.l1_drafts.create_index("draft_id", unique=True)
    await db.l1_drafts.create_index("created_at", expireAfterSeconds=86400)

    # Agents: tenant+status (list_agents), agent_id (get_agent)
    await db.agents.create_index("agent_id", unique=True)
    await db.agents.create_index([("tenant_id", 1), ("status", 1)])

    # Entity Registry: user+refs (resolve_entity)
    await db.entity_registry.create_index([("user_id", 1), ("human_refs", 1)])
    await db.entity_registry.create_index([("user_id", 1), ("canonical_id", 1)], unique=True)

    # User Profiles, Nicknames, Onboarding: user_id lookup
    await db.user_profiles.create_index("user_id", unique=True)
    await db.nicknames.create_index("user_id", unique=True)
    await db.onboarding.create_index("user_id", unique=True)

    # Pipeline Progress: session_id lookup
    await db.pipeline_progress.create_index("session_id")

    # Mandate Dispatches: execution_id lookup
    await db.mandate_dispatches.create_index("execution_id")
    await db.mandate_dispatches.create_index("session_id")

    # Prompt Outcomes: user + time analytics
    await db.prompt_outcomes.create_index([("user_id", 1), ("created_at", -1)])

    # Prompt Versions: purpose + active lookup
    await db.prompt_versions.create_index([("purpose", 1), ("is_active", 1)])
    await db.prompt_versions.create_index([("purpose", 1), ("version", -1)])

    # Graphs: user_id lookup
    await db.graphs.create_index("user_id", unique=True)

    # Transcripts: session_id lookup
    await db.transcripts.create_index("session_id")

    # Vector store: doc_id lookup for persistence layer
    await db.vector_store.create_index("doc_id", unique=True)
    await db.vector_store.create_index([("metadata.user_id", 1)])

    # Rate limits: TTL auto-cleanup
    await db.rate_limits.create_index("expires_at", expireAfterSeconds=0)
    await db.rate_limits.create_index([("bucket", 1), ("timestamp", -1)])

    logger.info("MongoDB indexes initialized")


async def close_db() -> None:
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
        logger.info("MongoDB connection closed")



# ── Safe query helpers (always exclude _id to prevent ObjectId serialization) ──

async def find_one_safe(
    collection_name: str,
    query: dict,
    extra_projection: dict | None = None,
) -> dict | None:
    """find_one with _id excluded by default.

    Prevents ObjectId serialization crashes in API responses.
    Use instead of raw db.collection.find_one() wherever the result
    may be returned to the client or serialized to JSON.
    """
    db = get_db()
    projection: dict = {"_id": 0}
    if extra_projection:
        projection.update(extra_projection)
    return await getattr(db, collection_name).find_one(query, projection)


async def find_safe(
    collection_name: str,
    query: dict,
    limit: int = 100,
    sort_field: str | None = None,
    sort_dir: int = -1,
    extra_projection: dict | None = None,
) -> list[dict]:
    """find() with _id excluded and result capped by limit.

    Prevents ObjectId serialization crashes and unbounded query results.
    """
    db = get_db()
    projection: dict = {"_id": 0}
    if extra_projection:
        projection.update(extra_projection)
    cursor = getattr(db, collection_name).find(query, projection)
    if sort_field:
        cursor = cursor.sort(sort_field, sort_dir)
    return await cursor.limit(limit).to_list(limit)
