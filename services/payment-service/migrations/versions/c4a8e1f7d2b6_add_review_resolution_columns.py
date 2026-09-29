"""add review resolution columns to transfers and payments

Revision ID: c4a8e1f7d2b6
Revises: 05b49cb8770b
Create Date: 2026-09-29 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4a8e1f7d2b6"
down_revision: str | None = "05b49cb8770b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("transfers", "payments")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("reviewed_by_user_id", sa.UUID(), nullable=True))
        op.add_column(table, sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "reviewed_at")
        op.drop_column(table, "reviewed_by_user_id")
