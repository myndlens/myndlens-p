"""MIO Signer — ED25519 cryptographic signing.

Spec §9, §17: No execution without valid MIO.
Keys generated on BE only. Stored encrypted at rest.
"""
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional, Tuple

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)

# Singleton keypair
_private_key: Optional[Ed25519PrivateKey] = None
_public_key: Optional[Ed25519PublicKey] = None


def _ensure_keys() -> Tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    global _private_key, _public_key
    if _private_key is None:
        _private_key = Ed25519PrivateKey.generate()
        _public_key = _private_key.public_key()
        logger.info("[MIOSigner] ED25519 keypair generated")
    return _private_key, _public_key


def sign_mio(mio_dict: dict) -> str:
    """Sign a MIO dict and return base64 signature."""
    import base64
    priv, _ = _ensure_keys()
    # Canonical JSON serialization for signing
    payload = json.dumps(mio_dict, sort_keys=True, default=str).encode("utf-8")
    sig = priv.sign(payload)
    return base64.b64encode(sig).decode("ascii")


def verify_mio(mio_dict: dict, signature_b64: str) -> bool:
    """Verify a MIO signature."""
    import base64
    _, pub = _ensure_keys()
    try:
        payload = json.dumps(mio_dict, sort_keys=True, default=str).encode("utf-8")
        sig = base64.b64decode(signature_b64)
        pub.verify(sig, payload)
        return True
    except Exception as e:
        logger.warning("[MIOSigner] Verification failed: %s", str(e))
        return False


def get_public_key_hex() -> str:
    """Get public key as hex string (for verification by external parties)."""
    _, pub = _ensure_keys()
    raw = pub.public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return raw.hex()
