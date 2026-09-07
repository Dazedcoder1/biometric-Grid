"""
Symmetric encryption for secrets we must store and later reuse in plaintext
(GitHub personal access tokens, webhook secrets).

Passwords use one-way hashing instead — see app/core/security.py. This module is
only for values the server itself has to present back to a third party.

Key comes from GITHUB_ENC_KEY in .env. Generate one with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class EncryptionNotConfigured(RuntimeError):
    """Raised when a token operation is attempted without GITHUB_ENC_KEY set."""


def _fernet() -> Fernet:
    key = (settings.GITHUB_ENC_KEY or "").strip()
    if not key:
        raise EncryptionNotConfigured(
            "GITHUB_ENC_KEY is not set in .env — cannot store or read GitHub tokens. "
            "Generate one with: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise EncryptionNotConfigured(
            "GITHUB_ENC_KEY is not a valid Fernet key (expected 32 url-safe "
            "base64-encoded bytes)."
        ) from exc


def is_configured() -> bool:
    """True when encryption is usable, so callers can degrade gracefully."""
    try:
        _fernet()
        return True
    except EncryptionNotConfigured:
        return False


def encrypt(plaintext: str) -> str:
    if plaintext is None:
        return None
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str | None:
    """Returns None if the value can't be decrypted (key rotated, corrupt row)."""
    if not ciphertext:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        return None
