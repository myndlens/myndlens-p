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
