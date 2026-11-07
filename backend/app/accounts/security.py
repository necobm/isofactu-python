"""Cryptographic helpers: password hashing, session cookies and activation tokens."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import bcrypt
import jwt

from app.core.config import Settings

# bcrypt only looks at the first 72 bytes of a password; longer ones are rejected upstream
# (schemas) rather than silently truncated.
PASSWORD_MAX_BYTES = 72
PASSWORD_MIN_LENGTH = 8
SESSION_ALGORITHM = "HS256"

# -- passwords ------------------------------------------------------------------------


def hash_password(password: str, rounds: int = 12) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds)).decode()


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        return False
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:  # malformed hash / over-long input
        return False


async def hash_password_async(password: str, rounds: int = 12) -> str:
    """bcrypt is deliberately slow: run it off the event loop."""
    return await asyncio.to_thread(hash_password, password, rounds)


async def verify_password_async(password: str, password_hash: str | None) -> bool:
    return await asyncio.to_thread(verify_password, password, password_hash)


@lru_cache
def dummy_password_hash(rounds: int) -> str:
    """A valid hash of a throw-away password. Verified when the login e-mail is unknown, so
    an attacker cannot tell existing accounts apart from missing ones by timing the
    response."""
    return hash_password(secrets.token_urlsafe(16), rounds)


# -- session cookie -------------------------------------------------------------------


def create_session_token(user_id: int, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(hours=settings.session_ttl_hours),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=SESSION_ALGORITHM)


def read_session_token(token: str, settings: Settings) -> int | None:
    """The user id carried by a session token, or `None` if it is invalid or expired."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[SESSION_ALGORITHM])
        return int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None


# -- activation tokens ----------------------------------------------------------------


def generate_activation_token() -> str:
    """The secret that travels in the activation link (URL-safe, 256 bits of entropy)."""
    return secrets.token_urlsafe(32)


def hash_activation_token(token: str) -> str:
    """What gets stored: a plain SHA-256 is enough for a high-entropy random secret."""
    return hashlib.sha256(token.encode()).hexdigest()
