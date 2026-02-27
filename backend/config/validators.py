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

    # In production, enforce ALL security-critical secrets
    if settings.ENV == "prod":
        required_vars["EMERGENT_LLM_KEY"] = getattr(settings, "EMERGENT_LLM_KEY", "")
        required_vars["OBEGEE_S2S_TOKEN"] = getattr(settings, "OBEGEE_S2S_TOKEN", "")
        # Mock IDP must be disabled in prod
        if getattr(settings, "ENABLE_OBEGEE_MOCK_IDP", False):
            raise RuntimeError(
                "STARTUP FAILED — ENABLE_OBEGEE_MOCK_IDP must be False in production."
            )
    else:
        # Dev/staging: require SSO secret if mock IDP is enabled (signs tokens locally)
        if getattr(settings, "ENABLE_OBEGEE_MOCK_IDP", False):
            sso_secret = getattr(settings, "OBEGEE_SSO_HS_SECRET", "")
            if not sso_secret:
                required_vars["OBEGEE_SSO_HS_SECRET"] = ""

    missing = [k for k, v in required_vars.items() if not v]
    if missing:
        raise RuntimeError(
            f"STARTUP FAILED — missing required env vars: {', '.join(missing)}\n"
            "Set them in .env or container environment and restart the server."
        )

    warned_vars = {
        "OBEGEE_API_URL": settings.OBEGEE_API_URL,
        "CHANNEL_ADAPTER_IP": settings.CHANNEL_ADAPTER_IP,
    }
    for key, value in warned_vars.items():
        if not value:
            logger.warning("CONFIG WARNING: %s is not set — mandate dispatch will fail", key)
