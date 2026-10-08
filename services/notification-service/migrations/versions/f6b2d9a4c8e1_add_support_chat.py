"""add support chat

Revision ID: f6b2d9a4c8e1
Revises: e1f5a8c3b7d2
Create Date: 2026-10-08 15:00:00.000000

A customer's conversation with FinCore's staff.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f6b2d9a4c8e1"
down_revision: str | None = "e1f5a8c3b7d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    sender = postgresql.ENUM("CUSTOMER", "STAFF", name="support_sender", create_type=False)
    status = postgresql.ENUM("OPEN", "RESOLVED", name="support_status", create_type=False)
    sender.create(op.get_bind(), checkfirst=True)
    status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "support_threads",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("status", status, server_default="OPEN", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sender", sender, nullable=False),
        sa.Column("last_body", sa.String(length=200), nullable=False),
        sa.Column("staff_unread", sa.Integer(), server_default="0", nullable=False),
        sa.Column("customer_unread", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(
        "ix_support_threads_inbox", "support_threads", ["status", "last_message_at"], unique=False
    )
    op.create_table(
        "support_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("sender", sender, nullable=False),
        sa.Column("staff_user_id", sa.UUID(), nullable=True),
        sa.Column("body", sa.String(length=2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_support_messages_thread", "support_messages", ["user_id", "created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_support_messages_thread", table_name="support_messages")
    op.drop_table("support_messages")
    op.drop_index("ix_support_threads_inbox", table_name="support_threads")
    op.drop_table("support_threads")
    op.execute("DROP TYPE support_status")
    op.execute("DROP TYPE support_sender")
