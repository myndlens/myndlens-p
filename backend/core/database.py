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

    logger.info("MongoDB indexes initialized")


async def close_db() -> None:
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
        logger.info("MongoDB connection closed")
