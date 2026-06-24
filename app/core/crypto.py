"""
Fernet symmetric encryption for sensitive config values (SMTP passwords).
Uses the ENCRYPTION_KEY from environment — never hardcode this key.

Encrypt before DB insert. Decrypt before using in SMTP connection.
If ENCRYPTION_KEY changes, existing encrypted values break — keep it safe.
"""

import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

log = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        if not settings.ENCRYPTION_KEY:
            raise ValueError(
                "ENCRYPTION_KEY not set in environment. "
                "Generate with: python -c \"from cryptography.fernet "
                "import Fernet; print(Fernet.generate_key().decode())\""
            )
        _fernet = Fernet(settings.ENCRYPTION_KEY.encode())
    return _fernet


def encrypt(value: str) -> str:
    """Encrypt a plaintext string. Returns base64-encoded ciphertext."""
    if not value:
        return ""
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    """Decrypt a Fernet-encrypted string. Returns plaintext."""
    if not value:
        return ""
    try:
        return _get_fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        log.error("[crypto] Failed to decrypt value — wrong key or corrupted data")
        raise ValueError("Failed to decrypt SMTP password. Check ENCRYPTION_KEY.")
