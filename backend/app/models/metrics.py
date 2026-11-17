from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class TurnMetric(SQLModel, table=True):
    """One row per chat turn: what the user felt (latency) and what it cost (tokens)."""

    __tablename__ = "turn_metric"

    id: UUID = Field(default_factory=uuid4, sa_column=Column(PGUUID(as_uuid=True), primary_key=True))
    turn_id: UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False, unique=True, index=True))
    user_id: UUID = Field(sa_column=Column(PGUUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True))
    conversation_id: UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False, index=True))
    message_id: Optional[UUID] = Field(default=None, sa_column=Column(PGUUID(as_uuid=True), nullable=True))
    agent_name: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    mode: str = Field(sa_column=Column(String, nullable=False))  # routed | explicit
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime, nullable=False, index=True))

    total_ms: int = Field(sa_column=Column(Integer, nullable=False))
    ttft_ms: Optional[int] = Field(default=None, sa_column=Column(Integer, nullable=True))  # first streamed text
    context_ms: int = Field(default=0, sa_column=Column(Integer, nullable=False))  # memory + RAG assembly
    agent_ms: int = Field(default=0, sa_column=Column(Integer, nullable=False))  # router + agent + tools
    tool_calls: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    tool_ms: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    tools: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    input_tokens: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    output_tokens: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    fallback_used: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    error: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))


class LlmCall(SQLModel, table=True):
    """One row per LLM call (agents and background jobs), for token accounting."""

    __tablename__ = "llm_call"

    id: UUID = Field(default_factory=uuid4, sa_column=Column(PGUUID(as_uuid=True), primary_key=True))
    turn_id: Optional[UUID] = Field(default=None, sa_column=Column(PGUUID(as_uuid=True), nullable=True, index=True))
    user_id: Optional[UUID] = Field(default=None, sa_column=Column(PGUUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=True, index=True))
    purpose: str = Field(sa_column=Column(String, nullable=False))  # e.g. agent:code, router, memory_extraction
    model: str = Field(sa_column=Column(String, nullable=False))
    input_tokens: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    output_tokens: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    duration_ms: Optional[int] = Field(default=None, sa_column=Column(Integer, nullable=True))
    ok: bool = Field(default=True, sa_column=Column(Boolean, nullable=False))
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime, nullable=False, index=True))
