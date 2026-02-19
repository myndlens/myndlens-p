"""MIO Signer — ED25519 cryptographic signing.

Spec §9, §17: No execution without valid MIO.
Keys are persisted to MongoDB on first generation and reloaded on restart.
This ensures signed MIOs remain valid across server restarts and deploys.
"""
import base64
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

_private_key: Optional[Ed25519PrivateKey] = None
_public_key: Optional[Ed25519PublicKey] = None

_KEY_DOC_ID = "myndlens_mio_keypair"


async def _load_or_generate_keys() -> Tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    """Load keys from MongoDB, or generate + persist on first run."""
    global _private_key, _public_key

    if _private_key is not None:
        return _private_key, _public_key

    from core.database import get_db
    db = get_db()

    doc = await db.mio_keys.find_one({"_id": _KEY_DOC_ID})
    if doc and doc.get("private_key_pem"):
        # Reload from DB
        pem = doc["private_key_pem"].encode()
        _private_key = serialization.load_pem_private_key(pem, password=None)
        _public_key = _private_key.public_key()
        logger.info("[MIOSigner] ED25519 keypair loaded from DB")
    else:
        # Generate and persist
        _private_key = Ed25519PrivateKey.generate()
        _public_key = _private_key.public_key()
        pem = _private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        await db.mio_keys.update_one(
            {"_id": _KEY_DOC_ID},
            {"$set": {"private_key_pem": pem, "created_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
        logger.info("[MIOSigner] ED25519 keypair generated and persisted to DB")

    return _private_key, _public_key


def _ensure_keys() -> Tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    """Synchronous key access — requires prior async initialisation."""
    global _private_key, _public_key
    if _private_key is None:
        # Fallback: generate in-memory if async init was skipped
        _private_key = Ed25519PrivateKey.generate()
        _public_key = _private_key.public_key()
        logger.warning("[MIOSigner] Keys not pre-loaded — generated in-memory (not persisted)")
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
