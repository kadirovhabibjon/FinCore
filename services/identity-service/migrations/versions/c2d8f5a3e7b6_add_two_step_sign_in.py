"""add two-step sign-in

Revision ID: c2d8f5a3e7b6
Revises: a5c9e2d7f4b1
Create Date: 2026-10-12 10:00:00.000000

An account can ask for a code, emailed to it, on every sign-in.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c2d8f5a3e7b6"
down_revision: str | None = "a5c9e2d7f4b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "two_factor_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    purpose = postgresql.ENUM("LOGIN", "ENABLE", name="login_code_purpose", create_type=False)
    purpose.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "login_codes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("purpose", purpose, nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_login_codes_user_id"), "login_codes", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_login_codes_user_id"), table_name="login_codes")
    op.drop_table("login_codes")
    op.execute("DROP TYPE login_code_purpose")
    op.drop_column("users", "two_factor_enabled")
