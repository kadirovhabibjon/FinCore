"""add transfer parties

Revision ID: f2b6d9c1a4e7
Revises: c4a8e1f7d2b6
Create Date: 2026-10-05 15:10:00.000000

Who a transfer went to, and a display name for each side, so the
recipient can be shown it and notified.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2b6d9c1a4e7'
down_revision: Union[str, None] = 'c4a8e1f7d2b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('transfers', sa.Column('recipient_user_id', sa.UUID(), nullable=True))
    op.add_column('transfers', sa.Column('sender_name', sa.String(length=120), nullable=True))
    op.add_column('transfers', sa.Column('recipient_name', sa.String(length=120), nullable=True))
    op.create_index(
        op.f('ix_transfers_recipient_user_id'), 'transfers', ['recipient_user_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_transfers_recipient_user_id'), table_name='transfers')
    op.drop_column('transfers', 'recipient_name')
    op.drop_column('transfers', 'sender_name')
    op.drop_column('transfers', 'recipient_user_id')
