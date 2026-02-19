"""ObeGee SSO Token Validator.

Two modes (configurable via OBEGEE_TOKEN_VALIDATION_MODE):
  Mode A (HS256): Shared secret validation — dev/mock
  Mode B (JWKS):  Public key validation — production

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

import jwt

from config.settings import get_settings
from core.exceptions import AuthError

logger = logging.getLogger(__name__)

REQUIRED_ISSUER = "obegee"
REQUIRED_AUDIENCE = "myndlens"

_REQUIRED_CLAIMS = ("obegee_user_id", "myndlens_tenant_id", "subscription_status")
_VALID_STATUSES = ("ACTIVE", "SUSPENDED", "CANCELLED")


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


def _validate_claims(payload: dict) -> SSOClaims:
    """Common claim validation for both modes."""
    for field in _REQUIRED_CLAIMS:
        if field not in payload:
            raise AuthError(f"SSO token missing required claim: {field}")

    status = payload["subscription_status"]
    if status not in _VALID_STATUSES:
        raise AuthError(f"Invalid subscription_status: {status}")

    return SSOClaims(
        obegee_user_id=payload["obegee_user_id"],
        myndlens_tenant_id=payload["myndlens_tenant_id"],
        subscription_status=status,
        iss=payload.get("iss", ""),
        aud=payload.get("aud", "") if isinstance(payload.get("aud"), str) else (payload.get("aud", [""])[0] if payload.get("aud") else ""),
        iat=payload.get("iat", 0),
        exp=payload.get("exp", 0),
    )


class SSOTokenValidator(ABC):
    """Abstract validator interface — supports HS256 and JWKS."""

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

        return _validate_claims(payload)


class JWKSValidator(SSOTokenValidator):
    """Mode B: JWKS / RS256 public key validation (production).
    
    Fetches public keys from ObeGee's JWKS endpoint:
      GET http://178.62.42.175/.well-known/jwks.json
    """

    def __init__(self):
        self._jwks_client = None

    def _get_jwks_client(self):
        if self._jwks_client is None:
            settings = get_settings()
            if not settings.OBEGEE_JWKS_URL:
                raise AuthError("JWKS validation mode configured but OBEGEE_JWKS_URL not set")
            self._jwks_client = jwt.PyJWKClient(
                settings.OBEGEE_JWKS_URL,
                cache_keys=True,
                lifespan=3600,  # Cache keys for 1 hour
            )
            logger.info("[JWKS] Client initialized: %s", settings.OBEGEE_JWKS_URL)
        return self._jwks_client

    def validate(self, token: str) -> SSOClaims:
        try:
            jwks_client = self._get_jwks_client()
            signing_key = jwks_client.get_signing_key_from_jwt(token)

            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256", "EdDSA"],
                audience=REQUIRED_AUDIENCE,
                issuer=REQUIRED_ISSUER,
            )
        except jwt.ExpiredSignatureError:
            raise AuthError("SSO token expired")
        except jwt.InvalidAudienceError:
            raise AuthError(f"SSO token audience must be '{REQUIRED_AUDIENCE}'")
        except jwt.InvalidIssuerError:
            raise AuthError(f"SSO token issuer must be '{REQUIRED_ISSUER}'")
        except jwt.PyJWKClientError as e:
            logger.error("[JWKS] Key fetch failed: %s", str(e))
            raise AuthError(f"JWKS key resolution failed: {e}")
        except jwt.InvalidTokenError as e:
            raise AuthError(f"Invalid SSO token: {e}")

        return _validate_claims(payload)


def get_sso_validator() -> SSOTokenValidator:
    """Get the SSO validator.

    Production rule: ENV=prod always uses JWKS (RS256 from obegee.co.uk).
    Dev rule: uses OBEGEE_TOKEN_VALIDATION_MODE setting (default HS256 for mock IDP).
    This ensures production is never silently downgraded to HS256.
    """
    settings = get_settings()
    if settings.ENV == "prod":
        return JWKSValidator()
    mode = settings.OBEGEE_TOKEN_VALIDATION_MODE.upper()
    if mode == "HS256":
        return HS256Validator()
    elif mode == "JWKS":
        return JWKSValidator()
    else:
        raise ValueError(f"Unknown token validation mode: {mode}")
