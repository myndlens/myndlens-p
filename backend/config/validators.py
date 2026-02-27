"""Startup configuration validation guardrails."""

import logging


logger = logging.getLogger(__name__)


def _require_jwt_secret(settings) -> None:
    """Fail closed if JWT secret is not explicitly configured."""
    if not settings.JWT_SECRET or not settings.JWT_SECRET.strip():
        raise RuntimeError(
            "STARTUP FAILED — JWT_SECRET is required and cannot be empty. "
            "Set JWT_SECRET in backend/.env or container environment and restart the server."
        )


def validate_startup_config(settings) -> None:
    """Centralized startup guardrails for required and warning-level config."""
    _require_jwt_secret(settings)

    required_vars = {
        "MIO_KEY_ENCRYPTION_KEY": settings.MIO_KEY_ENCRYPTION_KEY,
        "MYNDLENS_BASE_URL": settings.MYNDLENS_BASE_URL,
    }
    missing = [k for k, v in required_vars.items() if not v]
    if missing:
        raise RuntimeError(
            f"STARTUP FAILED — missing required env vars in backend/.env: {', '.join(missing)}\n"
            "Set them in .env or container environment and restart the server."
        )

    warned_vars = {
        "OBEGEE_API_URL": settings.OBEGEE_API_URL,
        "CHANNEL_ADAPTER_IP": settings.CHANNEL_ADAPTER_IP,
    }
    for key, value in warned_vars.items():
        if not value:
            logger.warning("CONFIG WARNING: %s is not set — mandate dispatch will fail", key)
