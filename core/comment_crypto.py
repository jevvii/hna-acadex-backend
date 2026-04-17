import base64
import hashlib
from typing import Optional

from django.conf import settings

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:  # pragma: no cover
    Fernet = None
    InvalidToken = Exception


_PREFIX = "enc:v1:"


def _normalize_key(raw_key: str) -> bytes:
    if not raw_key:
        raise ValueError("Comment encryption key is empty.")
    try:
        key_bytes = raw_key.encode("utf-8")
        Fernet(key_bytes)
        return key_bytes
    except Exception:
        digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)


def _get_fernet():
    if Fernet is None:  # pragma: no cover
        return None
    configured = getattr(settings, "COMMENT_ENCRYPTION_KEY", None) or settings.SECRET_KEY
    key = _normalize_key(configured)
    return Fernet(key)


def encrypt_comment_content(content: Optional[str]) -> Optional[str]:
    if content in (None, ""):
        return content
    if isinstance(content, str) and content.startswith(_PREFIX):
        return content
    fernet = _get_fernet()
    if not fernet:  # pragma: no cover
        return content
    token = fernet.encrypt(str(content).encode("utf-8")).decode("utf-8")
    return f"{_PREFIX}{token}"


def decrypt_comment_content(content: Optional[str]) -> Optional[str]:
    if content in (None, ""):
        return content
    if not isinstance(content, str) or not content.startswith(_PREFIX):
        return content
    encrypted = content[len(_PREFIX):]
    fernet = _get_fernet()
    if not fernet:  # pragma: no cover
        return content
    try:
        return fernet.decrypt(encrypted.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return "[Encrypted message unavailable]"
