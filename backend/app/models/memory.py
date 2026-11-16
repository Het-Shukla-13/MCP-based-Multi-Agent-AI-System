from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, Float, Index, JSON, String, Text
from sqlmodel import Field, SQLModel

from app.core.config import settings


class Memory(SQLModel, table=True):
    __tablename__ = "memory"
    __table_args__ = (
        # Memory search uses l2_distance (ltm_service), so the index uses vector_l2_ops.
        Index(
            "memory_embedding_idx",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_l2_ops"},
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    user_id: UUID = Field(nullable=False)
    conversation_id: Optional[UUID] = Field(default=None, nullable=True)

    content: str = Field(sa_column=Column(Text, nullable=False))
    memory_type: str = Field(
        sa_column=Column(String, nullable=False, index=True)
    )

    memory_metadata: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )

    importance_score: float = Field(
        default=0.5,
        sa_column=Column(Float, nullable=False, default=0.5),
    )

    source: str = Field(
        default="conversation",
        sa_column=Column(String, nullable=False, default="conversation"),
    )

    is_active: bool = Field(default=True, nullable=False)

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, nullable=False),
    )

    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, nullable=False),
    )

    embedding: Optional[list[float]] = Field(
        default=None,
        sa_column=Column(Vector(settings.EMBEDDING_DIM), nullable=True),
    )
