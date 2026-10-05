"""add news

Revision ID: d4a7c2e9f1b6
Revises: b8e3f1c6d2a9
Create Date: 2026-10-05 17:00:00.000000

Banking news from public feeds, and when each customer last looked.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4a7c2e9f1b6"
down_revision: str | None = "b8e3f1c6d2a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "news_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("guid", sa.String(length=500), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.String(length=2000), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "guid", name="uq_news_items_source_guid"),
    )
    op.create_index(op.f("ix_news_items_fetched_at"), "news_items", ["fetched_at"], unique=False)
    op.create_table(
        "news_reads",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("news_reads")
    op.drop_index(op.f("ix_news_items_fetched_at"), table_name="news_items")
    op.drop_table("news_items")
