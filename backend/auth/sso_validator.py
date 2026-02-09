"""ObeGee SSO Token Validator.

Two modes (configurable via OBEGEE_TOKEN_VALIDATION_MODE):
  Mode A (HS256): Shared secret validation — dev/mock
  Mode B (JWKS):  Public key validation — prod-ready (stub for now)

Hard validation rules:
  - iss == "obegee"
  - aud == "myndlens"
  - exp not expired
  - contains: obegee_user_id, myndlens_tenant_id, subscription_status

Never reuses MyndLens JWT secret.
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import jwt

from config.settings import get_settings
from core.exceptions import AuthError

logger = logging.getLogger(__name__)

REQUIRED_ISSUER = "obegee"
REQUIRED_AUDIENCE = "myndlens"


@dataclass
class SSOClaims:
    """Validated claims from an ObeGee SSO token."""
    obegee_user_id: str
    myndlens_tenant_id: str
    subscription_status: str  # ACTIVE | SUSPENDED | CANCELLED
    iss: str
    aud: str
    iat: float
    exp: float


class SSOTokenValidator(ABC):
    """Abstract validator interface — supports HS256 and future JWKS."""

    @abstractmethod
    def validate(self, token: str) -> SSOClaims:
        ...


class HS256Validator(SSOTokenValidator):
    """Mode A: HS256 shared secret validation (dev/mock)."""

    def validate(self, token: str) -> SSOClaims:
        settings = get_settings()
        try:
            payload = jwt.decode(
                token,
                settings.OBEGEE_SSO_HS_SECRET,
                algorithms=["HS256"],
                audience=REQUIRED_AUDIENCE,
                issuer=REQUIRED_ISSUER,
            )
        except jwt.ExpiredSignatureError:
            raise AuthError("SSO token expired")
        except jwt.InvalidAudienceError:
            raise AuthError(f"SSO token audience must be '{REQUIRED_AUDIENCE}'")
        except jwt.InvalidIssuerError:
            raise AuthError(f"SSO token issuer must be '{REQUIRED_ISSUER}'")
        except jwt.InvalidTokenError as e:
            raise AuthError(f"Invalid SSO token: {e}")

        # Hard-validate required claims
        for field in ("obegee_user_id", "myndlens_tenant_id", "subscription_status"):
            if field not in payload:
                raise AuthError(f"SSO token missing required claim: {field}")

        status = payload["subscription_status"]
        if status not in ("ACTIVE", "SUSPENDED", "CANCELLED"):
            raise AuthError(f"Invalid subscription_status: {status}")

        return SSOClaims(
            obegee_user_id=payload["obegee_user_id"],
            myndlens_tenant_id=payload["myndlens_tenant_id"],
            subscription_status=status,
            iss=payload["iss"],
            aud=payload["aud"],
            iat=payload.get("iat", 0),
            exp=payload.get("exp", 0),
        )


class JWKSValidator(SSOTokenValidator):
    """Mode B: JWKS / RS256 / EdDSA public key validation (prod-ready stub)."""

    def validate(self, token: str) -> SSOClaims:
        settings = get_settings()
        if not settings.OBEGEE_JWKS_URL:
            raise AuthError(
                "JWKS validation mode configured but OBEGEE_JWKS_URL not set. "
                "Set the JWKS endpoint or switch to HS256 mode."
            )
        # Future: fetch JWKS, validate RS256/EdDSA signature
        raise AuthError("JWKS validation not yet implemented")


def get_sso_validator() -> SSOTokenValidator:
    """Get the configured SSO validator based on OBEGEE_TOKEN_VALIDATION_MODE."""
    settings = get_settings()
    mode = settings.OBEGEE_TOKEN_VALIDATION_MODE.upper()
    if mode == "HS256":
        return HS256Validator()
    elif mode == "JWKS":
        return JWKSValidator()
    else:
        raise ValueError(f"Unknown token validation mode: {mode}")
