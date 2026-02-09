"""Hard environment separation — B18 (minimal).

Prod dispatch from non-prod is IMPOSSIBLE.
This module enforces that invariant.
"""
import logging
from config.settings import get_settings
from core.exceptions import EnvGuardError

logger = logging.getLogger(__name__)


def assert_env(required: str) -> None:
    """Raise if current env does not match required."""
    settings = get_settings()
    if settings.ENV != required:
        msg = f"Operation requires env={required}, current env={settings.ENV}"
        logger.error("ENV_GUARD_VIOLATION: %s", msg)
        raise EnvGuardError(msg)


def can_dispatch() -> bool:
    """Returns True only if current env allows dispatch.
    
    In dev/staging, dispatch goes to stub/sandbox.
    Only prod dispatches to real OpenClaw.
    This function validates that the dispatch target matches env.
    """
    settings = get_settings()
    return settings.ENV in ("dev", "staging", "prod")


def assert_dispatch_allowed(target_env: str) -> None:
    """Hard guard: target_env must match current env.
    
    Prevents prod dispatch from dev environment.
    """
    settings = get_settings()
    if target_env == "prod" and settings.ENV != "prod":
        msg = f"BLOCKED: Cannot dispatch to prod from env={settings.ENV}"
        logger.critical("ENV_GUARD_CRITICAL: %s", msg)
        raise EnvGuardError(msg)
    if target_env != settings.ENV:
        msg = f"BLOCKED: target_env={target_env} != current_env={settings.ENV}"
        logger.error("ENV_GUARD_VIOLATION: %s", msg)
        raise EnvGuardError(msg)
