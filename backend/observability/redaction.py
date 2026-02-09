"""PII / secrets redaction engine.

Batch 0 — B16 (minimal).
Patterns: email, phone, SSN, API keys, JWTs, MongoDB URIs.
"""
import re
from typing import List, Tuple

# (pattern, replacement_label)
_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Email
    (re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"), "[REDACTED_EMAIL]"),
    # Phone (international)
    (re.compile(r"\+?\d[\d\-\s]{8,15}\d"), "[REDACTED_PHONE]"),
    # SSN
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
    # API key patterns (generic long hex/base64)
    (re.compile(r"(?:api[_-]?key|token|secret|password)[\s:=]+[\"']?[A-Za-z0-9_\-\.]{20,}[\"']?", re.IGNORECASE), "[REDACTED_SECRET]"),
    # JWT tokens
    (re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), "[REDACTED_JWT]"),
    # MongoDB URI with credentials
    (re.compile(r"mongodb(?:\+srv)?://[^\s]+"), "[REDACTED_MONGO_URI]"),
    # Generic bearer token
    (re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE), "[REDACTED_BEARER]"),
]


def redact(text: str) -> str:
    """Apply all redaction patterns to text."""
    result = text
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def redact_dict(data: dict, sensitive_keys: set | None = None) -> dict:
    """Redact values of sensitive keys in a dictionary."""
    if sensitive_keys is None:
        sensitive_keys = {
            "token", "password", "secret", "api_key",
            "jwt", "signature", "touch_token", "biometric_proof",
        }
    result = {}
    for k, v in data.items():
        if k.lower() in sensitive_keys:
            result[k] = "[REDACTED]"
        elif isinstance(v, dict):
            result[k] = redact_dict(v, sensitive_keys)
        elif isinstance(v, str):
            result[k] = redact(v)
        else:
            result[k] = v
    return result
