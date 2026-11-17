from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class ChatTurn(SQLModel, table=True):
    """
    One submitted chat message and its lifecycle, owned by the TurnRunner.

    status: queued -> running -> done | stopped | failed | interrupted
    The row is what makes turns survive the socket (and the process): a queued
    turn is resumed on startup, a running turn whose heartbeat went stale is
    closed with an "interrupted" reply instead of leaving a dangling question.
    """

    __tablename__ = "chat_turn"

    id: UUID = Field(default_factory=uuid4, sa_column=Column(PGUUID(as_uuid=True), primary_key=True))
    conversation_id: UUID = Field(sa_column=Column(PGUUID(as_uuid=True), ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False, index=True))
    user_id: UUID = Field(sa_column=Column(PGUUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False))
    status: str = Field(default="queued", sa_column=Column(String, nullable=False, index=True))
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    user_message_id: Optional[UUID] = Field(default=None, sa_column=Column(PGUUID(as_uuid=True), nullable=True))
    ai_message_id: Optional[UUID] = Field(default=None, sa_column=Column(PGUUID(as_uuid=True), nullable=True))
    error: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime, nullable=False))
    started_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime, nullable=True))
    heartbeat_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime, nullable=True))
    finished_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime, nullable=True))
