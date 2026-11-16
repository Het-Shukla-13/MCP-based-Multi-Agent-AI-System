from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class RefreshToken(SQLModel, table=True):
    """
    One issued refresh token. Only its SHA-256 hash is stored (a DB leak must not
    leak usable tokens). All tokens produced by rotation from one login share a
    family_id, so reuse of an old token can revoke that whole login session.
    """

    __tablename__ = "refresh_token"

    id: UUID = Field(default_factory=uuid4, sa_column=Column(PGUUID(as_uuid=True), primary_key=True))
    user_id: UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    token_hash: str = Field(sa_column=Column(String(64), nullable=False, unique=True, index=True))
    family_id: UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False, index=True))
    expires_at: datetime = Field(sa_column=Column(DateTime, nullable=False))
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime, nullable=False))
    revoked_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime, nullable=True))
