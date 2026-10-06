"""add transfer recipient card

Revision ID: b3e8f2a6d9c4
Revises: a9d3e7b1c5f2
Create Date: 2026-10-06 18:00:00.000000

The card number a transfer was sent to, for the sender's list of recent
recipients.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3e8f2a6d9c4'
down_revision: Union[str, None] = 'a9d3e7b1c5f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'transfers', sa.Column('recipient_card_number', sa.String(length=16), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('transfers', 'recipient_card_number')
