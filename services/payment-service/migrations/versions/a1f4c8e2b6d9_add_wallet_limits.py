"""add wallet limits

Revision ID: a1f4c8e2b6d9
Revises: e4b7c1d9a3f6
Create Date: 2026-10-08 11:00:00.000000

A customer's own daily sending limit per wallet.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f4c8e2b6d9'
down_revision: Union[str, None] = 'e4b7c1d9a3f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'wallet_limits',
        sa.Column('wallet_id', sa.UUID(), nullable=False),
        sa.Column('owner_user_id', sa.UUID(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('daily_limit_minor', sa.BigInteger(), nullable=False),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.CheckConstraint('daily_limit_minor > 0', name='ck_wallet_limits_positive'),
        sa.PrimaryKeyConstraint('wallet_id'),
    )
    # What the limit is checked against: a wallet's recent outgoing operations.
    op.create_index(
        'ix_transfers_source_wallet_created', 'transfers', ['source_wallet_id', 'created_at']
    )
    op.create_index(
        'ix_payments_source_wallet_created', 'payments', ['source_wallet_id', 'created_at']
    )


def downgrade() -> None:
    op.drop_index('ix_payments_source_wallet_created', table_name='payments')
    op.drop_index('ix_transfers_source_wallet_created', table_name='transfers')
    op.drop_table('wallet_limits')
