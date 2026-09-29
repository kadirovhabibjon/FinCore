"""add outbox_events table

Revision ID: e6b2c9d4a7f1
Revises: b5318f1d1118
Create Date: 2026-09-29 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e6b2c9d4a7f1"
down_revision: str | None = "b5318f1d1118"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Same shape as payment- and identity-service's outbox (spec Section 14.1).
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_outbox_events_aggregate_id"), "outbox_events", ["aggregate_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_outbox_events_aggregate_id"), table_name="outbox_events")
    op.drop_table("outbox_events")
