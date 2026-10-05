"""notifications per recipient, read state

Revision ID: b8e3f1c6d2a9
Revises: ad979960a3ec
Create Date: 2026-10-05 15:40:00.000000

One event can now notify two people (a transfer's sender and its
recipient), so the idempotency guard becomes (event_id,
recipient_user_id); and a notification can be read.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8e3f1c6d2a9"
down_revision: str | None = "ad979960a3ec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notifications", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True)
    )
    # Everything sent before the bell existed would otherwise light it up
    # with a backlog on first sign-in.
    op.execute("UPDATE notifications SET read_at = now()")
    op.drop_constraint("notifications_event_id_key", "notifications", type_="unique")
    op.create_unique_constraint(
        "uq_notifications_event_recipient", "notifications", ["event_id", "recipient_user_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_notifications_event_recipient", "notifications", type_="unique")
    # Back to one notification per event: keep each event's oldest.
    op.execute(
        "DELETE FROM notifications a USING notifications b "
        "WHERE a.event_id = b.event_id AND a.created_at > b.created_at"
    )
    op.create_unique_constraint("notifications_event_id_key", "notifications", ["event_id"])
    op.drop_column("notifications", "read_at")
