"""Centralized settings module — single source of truth for all config.

All secrets loaded exclusively from env vars. Never committed, never logged.
Redaction enforced everywhere via observability.redaction.
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings

_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # ── Environment ──────────────────────────────────────────────
    ENV: Literal["dev", "staging", "prod"] = Field(default="dev")

    # ── MongoDB ──────────────────────────────────────────────────
    MONGO_URL: str = Field(default="mongodb://localhost:27017")
    DB_NAME: str = Field(default="myndlens_dev")

    # ── Auth / Signing ───────────────────────────────────────────
    JWT_SECRET: str = Field(default="")
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_EXPIRY_SECONDS: int = Field(default=3600)  # 1 hour

    # ── Presence ─────────────────────────────────────────────────
    HEARTBEAT_INTERVAL_S: int = Field(default=5)
    HEARTBEAT_TIMEOUT_S: int = Field(default=15)  # >15s → refuse MIO

    # ── External Services (stubs in early batches) ───────────────
    DEEPGRAM_API_KEY: str = Field(default="")
    DEEPGRAM_MODEL: str = Field(default="nova-2")
    DEEPGRAM_LANGUAGE: str = Field(default="en-US")
    AUDIO_SAMPLE_RATE: int = Field(default=16000)
    MANDATE_MAX_CLARIFICATION_ROUNDS: int = Field(default=3)
    ELEVENLABS_API_KEY: str = Field(default="")
    GEMINI_API_KEY: str = Field(default="")

    # ── ObeGee SSO ─────────────────────────────────────────────
    # Separate secret from MyndLens JWT — never reuse
    OBEGEE_SSO_HS_SECRET: str = Field(default="")
    OBEGEE_TOKEN_VALIDATION_MODE: str = Field(default="HS256")  # HS256 | JWKS
    OBEGEE_JWKS_URL: str = Field(default="https://obegee.co.uk/.well-known/jwks.json")  # Production JWKS
    OBEGEE_S2S_TOKEN: str = Field(default="obegee-s2s-dev-token-CHANGE-IN-PROD")
    ENABLE_OBEGEE_MOCK_IDP: bool = Field(default=True)  # MUST be false in prod

    # ── ObeGee Shared Infrastructure ──────────────────────────
    OBEGEE_MONGO_URL: str = Field(default="")  # ObeGee's MongoDB (read-only shared collections)
    OBEGEE_DB_NAME: str = Field(default="obegee_production")
    CHANNEL_ADAPTER_IP: str = Field(default="")  # 138.68.179.111 in prod
    MYNDLENS_DISPATCH_TOKEN: str = Field(default="")
    OBEGEE_API_URL: str = Field(default="")  # https://obegee.co.uk/api in prod

    # Service-to-service token for ObeGee API calls (NOT the user session token).
    # Must be an RS256 JWT or API key issued by ObeGee to MyndLens as a service.
    # Obtain from ObeGee team. Leave empty in dev — dispatch will fail gracefully.
    OBEGEE_API_TOKEN: str = Field(default="")

    # Fixed dev tenant for mock IDP (avoids random tenant_id that ObeGee can't find).
    # Set to the tenant_id provisioned in ObeGee for dev/staging testing.
    OBEGEE_DEV_TENANT_ID: str = Field(default="")

    # ── MIO Key Encryption ───────────────────────────────────
    # 32-byte hex key used to AES-256-GCM encrypt the ED25519 private key at rest.
    # Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
    MIO_KEY_ENCRYPTION_KEY: str = Field(default="")

    # ── Self-referential URL (used in pairing response) ──────
    MYNDLENS_BASE_URL: str = Field(default="https://app.myndlens.com")

    # ── Observability ────────────────────────────────────────────
    LOG_LEVEL: str = Field(default="INFO")
    LOG_REDACTION_ENABLED: bool = Field(default=True)

    # ── Feature Flags ────────────────────────────────────────────
    MOCK_STT: bool = Field(default=True)
    MOCK_TTS: bool = Field(default=True)
    MOCK_LLM: bool = Field(default=True)

    # ── Emergent LLM Key (universal key for Gemini/OpenAI/Anthropic) ──
    EMERGENT_LLM_KEY: str = Field(default="")

    model_config = {
        "env_file": str(_ROOT / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
