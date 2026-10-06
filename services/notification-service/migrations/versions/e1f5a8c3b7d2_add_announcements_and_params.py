"""add announcements and notification params

Revision ID: e1f5a8c3b7d2
Revises: d4a7c2e9f1b6
Create Date: 2026-10-06 16:30:00.000000

Staff announcements for the bell, and the facts behind each
notification's text so clients can render it in another language.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e1f5a8c3b7d2"
down_revision: str | None = "d4a7c2e9f1b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_table(
        "announcements",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.String(length=1000), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_announcements_created_at"), "announcements", ["created_at"], unique=False
    )
    op.create_table(
        "announcement_reads",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("announcement_reads")
    op.drop_index(op.f("ix_announcements_created_at"), table_name="announcements")
    op.drop_table("announcements")
    op.drop_column("notifications", "params")
