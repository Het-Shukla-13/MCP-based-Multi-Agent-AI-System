from typing import Optional
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Column, Computed, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

from app.core.config import settings

EMBEDDING_DIM = settings.EMBEDDING_DIM


class ChunkParent(SQLModel, table=True):
    """The larger passage a child chunk belongs to: what the agent reads (see hierarchy.py)."""

    __tablename__ = "chunk_parent"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    file_id: UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("file.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    content: str = Field(sa_column=Column(Text, nullable=False))


class Chunk(SQLModel, table=True):
    __tablename__ = "chunk"
    __table_args__ = (
        # HNSW = approximate nearest-neighbour index. The operator class MUST match
        # the distance used in queries (cosine_distance <=> vector_cosine_ops),
        # otherwise Postgres ignores the index and scans every row.
        Index(
            "chunk_embedding_idx",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # Full-text index for the keyword half of hybrid search.
        Index("chunk_search_vector_idx", "search_vector", postgresql_using="gin"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    # Deleting a file deletes its chunks (no orphaned embeddings).
    file_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("file.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    content: str = Field(sa_column=Column(Text, nullable=False))
    file_metadata: dict = Field(default_factory=dict, sa_column=Column("metadata", JSON))
    embedding: Optional[list[float]] = Field(default=None, sa_column=Column(Vector(EMBEDDING_DIM)))
    # NULL for chunks that are their own context (code, tables from CSV/XLSX, old rows).
    parent_id: Optional[UUID] = Field(
        default=None,
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("chunk_parent.id", ondelete="CASCADE"), nullable=True, index=True),
    )
    # Maintained by Postgres (GENERATED ... STORED), including for rows that existed
    # before this column: never written by the application.
    search_vector: Optional[str] = Field(
        default=None,
        sa_column=Column(TSVECTOR, Computed("to_tsvector('english', content)", persisted=True)),
    )
