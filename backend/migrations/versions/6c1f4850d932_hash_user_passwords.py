"""hash user passwords

Revision ID: 6c1f4850d932
Revises: 1495dfd2a35e
Create Date: 2026-11-16 18:25:42.801896

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy  # noqa: F401  (autogenerate emits pgvector types)


# revision identifiers, used by Alembic.
revision: str = '6c1f4850d932'
down_revision: Union[str, Sequence[str], None] = '1495dfd2a35e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Rename password -> password_hash and hash the existing PLAINTEXT values in place,
    so no user has to reset their password. (Hashes are one-way: there is no downgrade
    back to plaintext; downgrade only renames the column.)
    """
    from argon2 import PasswordHasher

    op.alter_column("user", "password", new_column_name="password_hash")
    hasher = PasswordHasher()
    conn = op.get_bind()
    rows = conn.execute(sa.text('SELECT id, password_hash FROM "user"')).fetchall()
    for user_id, value in rows:
        if value and not value.startswith("$argon2"):  # idempotent: skip already-hashed rows
            conn.execute(
                sa.text('UPDATE "user" SET password_hash = :h WHERE id = :id'),
                {"h": hasher.hash(value), "id": user_id},
            )


def downgrade() -> None:
    op.alter_column("user", "password_hash", new_column_name="password")
