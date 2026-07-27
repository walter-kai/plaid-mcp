"""AES-256-GCM field encryption for Plaid access tokens at rest.

Wire format mirrors spearfresh-ui token-crypto:
  enc:v1:{iv_b64}:{tag_b64}:{ciphertext_b64}
"""

from __future__ import annotations

import base64
import binascii
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIX = "enc:v1:"
IV_LENGTH = 12
KEY_LENGTH = 32
_TAG_LENGTH = 16

_UNSET = object()
_cached_key: bytes | None | object = _UNSET


def _parse_key(raw: str | None) -> bytes | None:
    if not raw or not raw.strip():
        return None
    trimmed = raw.strip()
    try:
        from_b64 = base64.b64decode(trimmed, validate=True)
        if len(from_b64) == KEY_LENGTH:
            return from_b64
    except (binascii.Error, ValueError):
        pass
    try:
        from_hex = bytes.fromhex(trimmed)
        if len(from_hex) == KEY_LENGTH:
            return from_hex
    except ValueError:
        pass
    return None


def get_encryption_key(*, require_in_production: bool = True) -> bytes | None:
    """Return the 32-byte AES key, or None when unset in non-production."""
    global _cached_key
    if _cached_key is not _UNSET:
        return _cached_key  # type: ignore[return-value]

    raw = os.getenv("PLAID_TOKEN_ENCRYPTION_KEY")
    parsed = _parse_key(raw)
    env = (os.getenv("PLAID_ENV") or "production").strip().lower()

    if parsed is None:
        if require_in_production and env == "production":
            raise ValueError(
                "PLAID_TOKEN_ENCRYPTION_KEY must be a 32-byte key encoded as "
                "base64 or hex when PLAID_ENV=production"
            )
        _cached_key = None
        return None

    _cached_key = parsed
    return parsed


def reset_key_cache() -> None:
    """Test helper to clear the cached key."""
    global _cached_key
    _cached_key = _UNSET


def is_encrypted_token(value: str) -> bool:
    return value.startswith(PREFIX)


def encrypt_token(plain: str) -> str:
    """Encrypt a Plaid access token. No-op without a key in non-production."""
    if plain.startswith(PREFIX):
        return plain

    key = get_encryption_key()
    if key is None:
        return plain

    iv = secrets.token_bytes(IV_LENGTH)
    aesgcm = AESGCM(key)
    ciphertext_with_tag = aesgcm.encrypt(iv, plain.encode("utf-8"), None)
    # cryptography appends the 16-byte tag to the ciphertext
    ciphertext = ciphertext_with_tag[:-_TAG_LENGTH]
    tag = ciphertext_with_tag[-_TAG_LENGTH:]
    return (
        f"{PREFIX}"
        f"{base64.b64encode(iv).decode('ascii')}:"
        f"{base64.b64encode(tag).decode('ascii')}:"
        f"{base64.b64encode(ciphertext).decode('ascii')}"
    )


def decrypt_token(value: str) -> str:
    """Decrypt a stored token. Values without enc:v1: are treated as legacy plaintext."""
    if not value.startswith(PREFIX):
        return value

    key = get_encryption_key(require_in_production=False)
    if key is None:
        raise ValueError("Cannot decrypt token: PLAID_TOKEN_ENCRYPTION_KEY is not configured")

    payload = value[len(PREFIX) :]
    parts = payload.split(":")
    if len(parts) != 3:
        raise ValueError("Invalid encrypted token format")
    iv_b64, tag_b64, ciphertext_b64 = parts
    try:
        iv = base64.b64decode(iv_b64)
        tag = base64.b64decode(tag_b64)
        ciphertext = base64.b64decode(ciphertext_b64)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Invalid encrypted token encoding") from exc

    if len(iv) != IV_LENGTH or len(tag) != _TAG_LENGTH:
        raise ValueError("Invalid encrypted token parameters")

    aesgcm = AESGCM(key)
    plain = aesgcm.decrypt(iv, ciphertext + tag, None)
    return plain.decode("utf-8")
