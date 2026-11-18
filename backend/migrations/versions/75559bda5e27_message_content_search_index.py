"""message content search index

Revision ID: 75559bda5e27
Revises: bb99311688d9
Create Date: 2026-11-18 11:53:51.287961

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy  # noqa: F401  (autogenerate emits pgvector types)


# revision identifiers, used by Alembic.
revision: str = '75559bda5e27'
down_revision: Union[str, Sequence[str], None] = 'bb99311688d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """GIN expression index for full-text search over message content.

    Written by hand: autogenerate doesn't reliably compare expression indexes.
    (On a large live table you'd build it CONCURRENTLY, outside a transaction.)
    """
    op.create_index(
        "message_content_fts_idx",
        "message",
        [sa.text("to_tsvector('english', content)")],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("message_content_fts_idx", table_name="message")
