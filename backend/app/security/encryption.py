"""
hi.myrepo - Encryption Utility

Fernet-based encryption for provider API keys and other secrets.
Keys are encrypted at rest and decrypted only when needed for outbound calls.

Non-negotiable rules:
- Never log decrypted secrets
- Never return decrypted secrets in API responses
- Never expose secrets in audit logs
- Never store plaintext in the database
"""

import base64
import hashlib
import os
from typing import Optional

from app.core.config import get_settings


def _get_or_generate_key() -> bytes:
    """Get encryption key from settings, or derive one from APP_SECRET_KEY."""
    settings = get_settings()
    secret = settings.app_secret_key
    if not secret or secret == "change-me":
        # Fallback: generate a key from environment
        # WARNING: This means data encrypted before APP_SECRET_KEY is set
        # will not be decryptable. In production, always set APP_SECRET_KEY.
        secret = os.environ.get("APP_SECRET_KEY", "default-dev-key-do-not-use-in-production")

    # Derive a consistent 32-byte key from the secret using SHA-256
    return hashlib.sha256(secret.encode()).digest()


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret string using Fernet symmetric encryption.

    Args:
        plaintext: The secret to encrypt (e.g., API key)

    Returns:
        Base64-encoded encrypted string, prefixed with 'enc:' for identification
    """
    if not plaintext:
        return ""

    try:
        from cryptography.fernet import Fernet

        key = _get_or_generate_key()
        # Fernet requires a URL-safe base64-encoded 32-byte key
        fernet_key = base64.urlsafe_b64encode(key)
        f = Fernet(fernet_key)
        encrypted = f.encrypt(plaintext.encode("utf-8"))
        return f"enc:{encrypted.decode('utf-8')}"
    except ImportError:
        # Fallback: simple XOR obfuscation for dev environments
        # NOT cryptographically secure — only for development
        key = _get_or_generate_key()
        encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(plaintext.encode("utf-8")))
        return f"dev:{base64.b64encode(encrypted).decode('utf-8')}"


def decrypt_secret(encrypted: str) -> str:
    """Decrypt an encrypted secret string.

    Args:
        encrypted: The encrypted string (with 'enc:' or 'dev:' prefix)

    Returns:
        Decrypted plaintext string

    Raises:
        ValueError: If the encrypted string is invalid or cannot be decrypted
    """
    if not encrypted:
        return ""

    try:
        from cryptography.fernet import Fernet

        if encrypted.startswith("enc:"):
            token = encrypted[4:]
            key = _get_or_generate_key()
            fernet_key = base64.urlsafe_b64encode(key)
            f = Fernet(fernet_key)
            decrypted = f.decrypt(token.encode("utf-8"))
            return decrypted.decode("utf-8")
        elif encrypted.startswith("dev:"):
            # Dev fallback
            key = _get_or_generate_key()
            raw = base64.b64decode(encrypted[4:])
            decrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
            return decrypted.decode("utf-8")
        else:
            # Legacy unencrypted key — decrypt as-is (for migration)
            return encrypted
    except Exception as e:
        raise ValueError(f"Failed to decrypt secret: {e}")


def mask_secret(plaintext: str, visible_chars: int = 4) -> str:
    """Return a masked version of a secret for display.

    Args:
        plaintext: The decrypted secret
        visible_chars: Number of characters to show at the end

    Returns:
        Masked string like '••••••••••abcd'
    """
    if not plaintext:
        return ""
    if len(plaintext) <= visible_chars:
        return "•" * len(plaintext)
    return "•" * (len(plaintext) - visible_chars) + plaintext[-visible_chars:]


def is_encrypted(value: str) -> bool:
    """Check if a value appears to be encrypted."""
    return value.startswith("enc:") or value.startswith("dev:")
