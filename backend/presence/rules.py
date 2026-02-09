"""Presence rules — centralized presence policy."""
from config.settings import get_settings


def get_heartbeat_interval_ms() -> int:
    """Get heartbeat interval in milliseconds (for client config)."""
    return get_settings().HEARTBEAT_INTERVAL_S * 1000


def get_heartbeat_timeout_s() -> int:
    """Get heartbeat timeout in seconds."""
    return get_settings().HEARTBEAT_TIMEOUT_S
