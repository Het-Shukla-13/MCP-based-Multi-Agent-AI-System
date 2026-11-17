from sqlmodel import SQLModel, Field, Relationship
from typing import List, Optional, TYPE_CHECKING
from datetime import datetime
from sqlalchemy import Column, String, Integer, ForeignKey, DateTime
from uuid import uuid4, UUID
from sqlalchemy.dialects.postgresql import UUID as PGUUID

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.user import User
    from app.models.file import File

class Message(SQLModel, table=True):
    __tablename__ = "message"

    id: UUID = Field(default_factory=uuid4, sa_column=Column(PGUUID(as_uuid=True), unique=True, nullable=False, primary_key=True, index=True))
    conversation_id: UUID = Field(sa_column=Column(PGUUID(as_uuid=True), ForeignKey("conversation.id"), nullable=False))
    user_id: UUID = Field(sa_column=Column(PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=False))
    content: str = Field(sa_column=Column(String, nullable=False))
    role: str = Field(sa_column=Column(String, nullable=False))
    token_count: Optional[int] = Field(default=None, sa_column=Column(Integer, nullable=True))
    # Which agent wrote this reply (assistant messages only; NULL for user messages).
    agent_name: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    # complete | stopped (user pressed Stop; content is the partial answer) | interrupted
    status: str = Field(default="complete", sa_column=Column(String, nullable=False, server_default="complete"))
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime, nullable=False))
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime, nullable=False))

    # Relationships
    conversation: "Conversation" = Relationship(back_populates="messages")
    user: "User" = Relationship()  
    files: List["File"] = Relationship(
        back_populates="message",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )