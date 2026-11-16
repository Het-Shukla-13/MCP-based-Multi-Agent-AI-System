"""
Password hashing and access tokens.

Passwords: Argon2id (OWASP's first recommendation). A slow, memory-hard hash makes
stolen-database brute force expensive; every hash embeds its own random salt and
parameters, so identical passwords get different hashes.

Tokens: JWT signed with HS256. The server verifies the signature and expiry
without a DB lookup. Only the user id ("sub") goes inside; a JWT is signed, NOT
encrypted, so anyone holding it can read its contents.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import settings

_hasher = PasswordHasher()  # argon2id with library defaults (OWASP-aligned)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when hashing parameters were strengthened since this hash was made."""
    return _hasher.check_needs_rehash(password_hash)


def create_access_token(user_id: UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES),
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> UUID | None:
    """User id if the token is valid and unexpired, else None."""
    try:
        # algorithms=[...] is pinned: never let the token choose its own algorithm.
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "access":
            return None
        return UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
