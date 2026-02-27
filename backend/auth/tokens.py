"""JWT token generation and validation.

Tokens are scoped to: user + device + environment.
Expiry forces re-authentication.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from pydantic import BaseModel

from config.settings import get_settings
from core.exceptions import AuthError

logger = logging.getLogger(__name__)


def _require_jwt_secret() -> str:
    """Read JWT secret and fail closed if configuration is invalid."""
    secret = get_settings().JWT_SECRET
    if not secret:
        raise AuthError("JWT secret is not configured")
    return secret


class TokenClaims(BaseModel):
    """Claims embedded in auth JWT."""
    user_id: str
    device_id: str
    session_id: str
    env: str
    iat: float
    exp: float


def generate_token(
    user_id: str,
    device_id: str,
    session_id: str,
    env: Optional[str] = None,
) -> str:
    """Generate a signed JWT for the given user/device/session."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "device_id": device_id,
        "session_id": session_id,
        "env": env or settings.ENV,
        "iat": now.timestamp(),
        "exp": (now + timedelta(seconds=settings.JWT_EXPIRY_SECONDS)).timestamp(),
    }
    token = jwt.encode(payload, _require_jwt_secret(), algorithm=settings.JWT_ALGORITHM)
    logger.info("Token generated for user=%s device=%s session=%s", user_id, device_id, session_id)
    return token


def validate_token(token: str) -> TokenClaims:
    """Validate and decode a JWT. Raises AuthError on failure."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            _require_jwt_secret(),
            algorithms=[settings.JWT_ALGORITHM],
        )
        claims = TokenClaims(**payload)
        # Env must match
        if claims.env != settings.ENV:
            raise AuthError(f"Token env={claims.env} does not match server env={settings.ENV}")
        return claims
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        raise AuthError("Token expired")
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid token: %s", str(e))
        raise AuthError(f"Invalid token: {str(e)}")
