"""MIO Signer — ED25519 cryptographic signing.

Spec §9, §17: No execution without valid MIO.
Keys are persisted to MongoDB encrypted with AES-256-GCM using MIO_KEY_ENCRYPTION_KEY.
This ensures:
  1. Signed MIOs remain valid across server restarts and deploys.
  2. The private key is never stored in plaintext.
"""
import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional, Tuple

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

_private_key: Optional[Ed25519PrivateKey] = None
_public_key: Optional[Ed25519PublicKey] = None

_KEY_DOC_ID = "myndlens_mio_keypair"


def _get_aes_key() -> bytes:
    """Get AES-256 key from settings. Fails loudly if not configured."""
    from config.settings import get_settings
    hex_key = get_settings().MIO_KEY_ENCRYPTION_KEY
    if not hex_key:
        raise RuntimeError(
            "MIO_KEY_ENCRYPTION_KEY is not set in backend/.env. "
            "Generate with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
        )
    key_bytes = bytes.fromhex(hex_key)
    if len(key_bytes) != 32:
        raise RuntimeError("MIO_KEY_ENCRYPTION_KEY must be exactly 32 bytes (64 hex chars)")
    return key_bytes


def _encrypt_pem(pem: str) -> str:
    """Encrypt PEM string with AES-256-GCM. Returns base64(nonce + ciphertext)."""
    key = _get_aes_key()
    nonce = os.urandom(12)  # 96-bit nonce for GCM
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, pem.encode("utf-8"), None)
    # Prepend nonce to ciphertext, base64 encode for storage
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def _decrypt_pem(encrypted_b64: str) -> str:
    """Decrypt AES-256-GCM encrypted PEM. Returns plaintext PEM string."""
    key = _get_aes_key()
    raw = base64.b64decode(encrypted_b64)
    nonce, ciphertext = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")


async def _load_or_generate_keys() -> Tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    """Load encrypted keys from MongoDB, or generate + encrypt + persist on first run."""
    global _private_key, _public_key

    if _private_key is not None:
        return _private_key, _public_key

    from core.database import get_db
    db = get_db()

    doc = await db.mio_keys.find_one({"_id": _KEY_DOC_ID})

    if doc and doc.get("private_key_enc"):
        # Decrypt and reload from DB
        pem = _decrypt_pem(doc["private_key_enc"])
        _private_key = serialization.load_pem_private_key(pem.encode(), password=None)
        _public_key = _private_key.public_key()
        logger.info("[MIOSigner] ED25519 keypair loaded and decrypted from DB")

    elif doc and doc.get("private_key_pem"):
        # Migration: plaintext PEM found — re-encrypt it now
        logger.warning("[MIOSigner] Plaintext key found — migrating to encrypted storage")
        pem = doc["private_key_pem"]
        encrypted = _encrypt_pem(pem)
        await db.mio_keys.update_one(
            {"_id": _KEY_DOC_ID},
            {"$set": {"private_key_enc": encrypted}, "$unset": {"private_key_pem": ""}},
        )
        _private_key = serialization.load_pem_private_key(pem.encode(), password=None)
        _public_key = _private_key.public_key()
        logger.info("[MIOSigner] ED25519 keypair migrated to encrypted storage")

    else:
        # Generate new keypair, encrypt, persist
        _private_key = Ed25519PrivateKey.generate()
        _public_key = _private_key.public_key()
        pem = _private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),  # plaintext in memory only; encrypted below
        ).decode()
        encrypted = _encrypt_pem(pem)
        await db.mio_keys.update_one(
            {"_id": _KEY_DOC_ID},
            {"$set": {"private_key_enc": encrypted, "created_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
        logger.info("[MIOSigner] ED25519 keypair generated and stored encrypted in DB")

    return _private_key, _public_key


def _ensure_keys() -> Tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    """Synchronous key access — requires prior async initialisation."""
    global _private_key, _public_key
    if _private_key is None:
        # Fallback: generate in-memory if async init was skipped (should not happen in prod)
        _private_key = Ed25519PrivateKey.generate()
        _public_key = _private_key.public_key()
        logger.warning("[MIOSigner] Keys not pre-loaded — generated in-memory (not persisted)")
    return _private_key, _public_key


def sign_mio(mio_dict: dict) -> str:
    """Sign a MIO dict and return base64 signature."""
    priv, _ = _ensure_keys()
    payload = json.dumps(mio_dict, sort_keys=True, default=str).encode("utf-8")
    sig = priv.sign(payload)
    return base64.b64encode(sig).decode("ascii")


def verify_mio(mio_dict: dict, signature_b64: str) -> bool:
    """Verify a MIO signature."""
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
