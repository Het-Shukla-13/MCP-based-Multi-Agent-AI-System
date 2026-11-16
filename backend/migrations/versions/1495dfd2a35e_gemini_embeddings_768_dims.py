"""gemini embeddings 768 dims

Revision ID: 1495dfd2a35e
Revises: 3fbaeef50690
Create Date: 2026-11-16 18:11:13.138701

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy  # noqa: F401  (autogenerate emits pgvector types)


# revision identifiers, used by Alembic.
revision: str = '1495dfd2a35e'
down_revision: Union[str, Sequence[str], None] = '3fbaeef50690'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_DIM = 768
OLD_DIM = 384
INDEXES = {
    # table: (index name, operator class)
    "chunk": ("chunk_embedding_idx", "vector_cosine_ops"),
    "memory": ("memory_embedding_idx", "vector_l2_ops"),
}


def _change_dim(dim: int) -> None:
    for table, (index, ops) in INDEXES.items():
        # An index on the column must go before the column type can change.
        op.execute(f"DROP INDEX IF EXISTS {index}")
        # MiniLM vectors cannot be converted into Gemini's vector space: clear them.
        # scripts/reembed.py recomputes them with the new model.
        op.execute(f"ALTER TABLE {table} ALTER COLUMN embedding TYPE vector({dim}) USING NULL")
        op.execute(f"CREATE INDEX {index} ON {table} USING hnsw (embedding {ops})")


def upgrade() -> None:
    """MiniLM (384) -> Gemini gemini-embedding-001 (768). Run scripts/reembed.py afterwards."""
    _change_dim(NEW_DIM)


def downgrade() -> None:
    _change_dim(OLD_DIM)
