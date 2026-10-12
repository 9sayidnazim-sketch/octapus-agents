"""Cryptography and security utilities for Octapus Staff Assistant.

Provides:
- Symmetric encryption/decryption of provider API keys at rest via Fernet.
- API key masking (never returns raw keys to the client).
- Password hashing and verification via bcrypt.
"""

from __future__ import annotations

import base64
import hashlib
import os
from typing import Optional

import bcrypt
from cryptography.fernet import Fernet, InvalidToken


class MasterKeyMissingError(RuntimeError):
    """Raised when an operation requires MASTER_KEY but none is configured."""
    pass


def get_master_key() -> Optional[str]:
    """Retrieve MASTER_KEY from environment."""
    return os.environ.get("MASTER_KEY")


def is_master_key_configured() -> bool:
    """Return True if MASTER_KEY is present in the environment."""
    key = get_master_key()
    return bool(key and key.strip())


def _derive_fernet_key(master_key: str) -> bytes:
    """Derive a valid 32-byte urlsafe base64 Fernet key from any passphrase or key string."""
    master_key = master_key.strip()
    try:
        decoded = base64.urlsafe_b64decode(master_key.encode("utf-8"))
        if len(decoded) == 32:
            return master_key.encode("utf-8")
    except Exception:
        pass

    # Deterministically derive 32 bytes using SHA-256 for arbitrary passphrases
    sha = hashlib.sha256(master_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(sha)


def get_fernet(master_key: Optional[str] = None) -> Fernet:
    """Return a Fernet instance using MASTER_KEY, or raise MasterKeyMissingError."""
    key_str = master_key or get_master_key()
    if not key_str or not key_str.strip():
        raise MasterKeyMissingError(
            "MASTER_KEY environment variable is missing. "
            "API keys cannot be stored encrypted at rest without a MASTER_KEY."
        )
    fernet_key = _derive_fernet_key(key_str)
    return Fernet(fernet_key)


def encrypt_api_key(plain_key: str, master_key: Optional[str] = None) -> str:
    """Encrypt a plain API key string for storage at rest."""
    if not plain_key:
        return ""
    f = get_fernet(master_key)
    encrypted_bytes = f.encrypt(plain_key.encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_api_key(encrypted_key: str, master_key: Optional[str] = None) -> str:
    """Decrypt an encrypted API key string.

    Returns the decrypted plaintext or empty string if encrypted_key is empty.
    Raises InvalidToken or MasterKeyMissingError if decryption fails.
    """
    if not encrypted_key:
        return ""
    f = get_fernet(master_key)
    decrypted_bytes = f.decrypt(encrypted_key.encode("utf-8"))
    return decrypted_bytes.decode("utf-8")


def mask_api_key(key: str) -> str:
    """Return a safe masked version of an API key (e.g. '••••••••abcd').

    Never reveals more than the trailing characters.
    """
    if not key:
        return "••••••••"
    key = key.strip()
    if len(key) <= 6:
        return "••••••••" + key[-2:]
    return "••••••••" + key[-4:]


def hash_password(plain_password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash or legacy plain string."""
    if not hashed_password or not plain_password:
        return False

    # Check bcrypt hash format ($2a$, $2b$, $2y$)
    if hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except Exception:
            return False

    # Fallback to constant-time comparison for plain string env fallback
    import hmac
    return hmac.compare_digest(plain_password, hashed_password)
