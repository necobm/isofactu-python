"""Encryption of the secrets kept in the database (e.g. the tenants' AI vendor API keys).

Values are encrypted with Fernet (AES-128-CBC + HMAC-SHA256, random IV: the same value
never encrypts to the same text, and tampering is detected). The keys come from
``ENCRYPTION_KEYS``: a comma-separated list of Fernet keys, the first one encrypts and all of
them decrypt, so keys can be rotated -- add the new key first, run
``python -m app.cli secrets rotate`` to re-encrypt what is stored, then drop the old one.

Without ``ENCRYPTION_KEYS`` a key is derived from ``SECRET_KEY`` (HKDF-SHA256). That derived
key is always kept *last* for decryption, so configuring ``ENCRYPTION_KEYS`` later does not
lose the values stored until then (rotate them to stop depending on ``SECRET_KEY``).
"""

from __future__ import annotations

import base64
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_DERIVATION_INFO = b"isofactu:database-secrets:v1"


class SecretDecryptionError(Exception):
    """The stored value cannot be decrypted with any of the configured keys (they
    changed) or it was tampered with."""


def generate_key() -> str:
    """A new random key for ``ENCRYPTION_KEYS``."""
    return Fernet.generate_key().decode("ascii")


def derived_key(secret_key: str) -> bytes:
    """The Fernet key derived from ``SECRET_KEY`` (used when ``ENCRYPTION_KEYS`` is unset)."""
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_DERIVATION_INFO)
    return base64.urlsafe_b64encode(hkdf.derive(secret_key.encode("utf-8")))


class SecretBox:
    """Encrypts / decrypts short secrets as URL-safe text, fit for a ``Text`` column."""

    def __init__(self, keys: list[bytes]) -> None:
        if not keys:
            raise ValueError("at least one key is needed")
        self._fernet = MultiFernet([Fernet(key) for key in keys])

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeError) as exc:
            raise SecretDecryptionError("The value cannot be decrypted") from exc

    def rotate(self, token: str) -> str:
        """The same secret, re-encrypted with the current (first) key."""
        try:
            return self._fernet.rotate(token.encode("ascii")).decode("ascii")
        except (InvalidToken, UnicodeError) as exc:
            raise SecretDecryptionError("The value cannot be decrypted") from exc


def secret_box_for(settings: Settings) -> SecretBox:
    keys = [key.encode("ascii") for key in settings.encryption_key_list]
    if not keys and settings.app_env == "prod":
        logger.warning(
            "ENCRYPTION_KEYS is not set: secrets stored in the database are encrypted with a "
            "key derived from SECRET_KEY (changing SECRET_KEY would make them unreadable)"
        )
    return SecretBox([*keys, derived_key(settings.secret_key)])


@lru_cache
def get_secret_box() -> SecretBox:
    return secret_box_for(get_settings())
