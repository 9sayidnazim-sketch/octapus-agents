import os
import sys
from pathlib import Path
import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import crypto


def test_encryption_roundtrip(monkeypatch):
    """Test encrypting and decrypting with MASTER_KEY."""
    test_key = "super-secret-master-key-passphrase-2026"
    monkeypatch.setenv("MASTER_KEY", test_key)

    plain = "sk-ant-api03-abcdef1234567890xyz"
    encrypted = crypto.encrypt_api_key(plain)

    assert encrypted != plain
    assert "sk-ant" not in encrypted

    decrypted = crypto.decrypt_api_key(encrypted)
    assert decrypted == plain


def test_missing_master_key_raises(monkeypatch):
    """Test that missing MASTER_KEY refuses encryption."""
    monkeypatch.delenv("MASTER_KEY", raising=False)

    with pytest.raises(crypto.MasterKeyMissingError):
        crypto.encrypt_api_key("sk-test-123")

    with pytest.raises(crypto.MasterKeyMissingError):
        crypto.decrypt_api_key("some-encrypted-string")


def test_mask_api_key():
    """Test masking API keys."""
    assert crypto.mask_api_key("sk-abcdefgh1234") == "••••••••1234"
    assert crypto.mask_api_key("short") == "••••••••rt"
    assert crypto.mask_api_key("") == "••••••••"


def test_password_hashing():
    """Test bcrypt hashing and verification."""
    pw = "octapus-staff-pass-2026"
    hashed = crypto.hash_password(pw)

    assert hashed != pw
    assert crypto.verify_password(pw, hashed) is True
    assert crypto.verify_password("wrong-password", hashed) is False
