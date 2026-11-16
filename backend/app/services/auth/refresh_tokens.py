"""
Refresh tokens with rotation and reuse detection (OAuth 2.0 Security BCP pattern).

- Opaque random string (not a JWT): its only job is to be looked up and revoked.
- Stored as SHA-256. A fast hash is right here (unlike passwords): the token has
  ~384 bits of randomness, so there is nothing to brute-force.
- Rotation: each use returns a NEW refresh token and revokes the old one.
- Reuse detection: presenting an already-revoked token means two parties hold the
  same token (theft), so the whole family (that login's chain) is revoked.
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import settings
from app.models import RefreshToken, User

INVALID_REFRESH = "Session expired. Please sign in again."


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def issue_refresh_token(db: AsyncSession, user_id: UUID, family_id: UUID | None = None) -> str:
    token = secrets.token_urlsafe(48)
    db.add(RefreshToken(
        user_id=user_id,
        token_hash=_hash(token),
        family_id=family_id or uuid4(),
        expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_DAYS),
    ))
    await db.commit()
    return token


async def _revoke_family(db: AsyncSession, family_id: UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.utcnow())
    )
    await db.commit()


async def rotate_refresh_token(db: AsyncSession, token: str) -> tuple[User, str]:
    """Validate + revoke the presented token; return (user, new refresh token)."""
    record = (await db.execute(select(RefreshToken).where(RefreshToken.token_hash == _hash(token)))).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_REFRESH)

    if record.revoked_at is not None:
        # Reuse of a rotated/revoked token: assume theft, end that whole session chain.
        logger.warning("Refresh token reuse detected | user_id={} | family={}", record.user_id, record.family_id)
        await _revoke_family(db, record.family_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_REFRESH)

    if record.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_REFRESH)

    user = await db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_REFRESH)

    record.revoked_at = datetime.utcnow()
    db.add(record)
    await db.commit()
    new_token = await issue_refresh_token(db, user.id, family_id=record.family_id)
    return user, new_token


async def revoke_refresh_token(db: AsyncSession, token: str) -> None:
    """Logout: end this login's whole chain (idempotent; unknown tokens are ignored)."""
    record = (await db.execute(select(RefreshToken).where(RefreshToken.token_hash == _hash(token)))).scalar_one_or_none()
    if record is not None:
        await _revoke_family(db, record.family_id)
