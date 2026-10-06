"""add exchanges

Revision ID: e4b7c1d9a3f6
Revises: c6f1a4e8b2d7
Create Date: 2026-10-06 20:30:00.000000

Currency exchanges between a customer's own wallets.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4b7c1d9a3f6'
down_revision: Union[str, None] = 'c6f1a4e8b2d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'exchanges',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('reference', sa.String(length=32), nullable=False),
        sa.Column('initiator_user_id', sa.UUID(), nullable=False),
        sa.Column('source_wallet_id', sa.UUID(), nullable=False),
        sa.Column('destination_wallet_id', sa.UUID(), nullable=False),
        sa.Column('source_position_account_id', sa.UUID(), nullable=False),
        sa.Column('destination_position_account_id', sa.UUID(), nullable=False),
        sa.Column('source_amount_minor', sa.BigInteger(), nullable=False),
        sa.Column('source_currency', sa.String(length=3), nullable=False),
        sa.Column('destination_amount_minor', sa.BigInteger(), nullable=False),
        sa.Column('destination_currency', sa.String(length=3), nullable=False),
        sa.Column('rate', sa.Numeric(precision=30, scale=15), nullable=False),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'DEBITED', 'COMPLETED', 'REVERSING', 'FAILED', name='exchange_status'),
            server_default='PENDING',
            nullable=False,
        ),
        sa.Column('failure_reason', sa.String(length=255), nullable=True),
        sa.Column('idempotency_key_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('source_amount_minor > 0', name='ck_exchanges_source_positive'),
        sa.CheckConstraint('destination_amount_minor > 0', name='ck_exchanges_destination_positive'),
        sa.CheckConstraint('source_currency != destination_currency', name='ck_exchanges_currencies_differ'),
        sa.ForeignKeyConstraint(['idempotency_key_id'], ['idempotency_keys.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key_id'),
        sa.UniqueConstraint('reference'),
    )
    op.create_index(op.f('ix_exchanges_initiator_user_id'), 'exchanges', ['initiator_user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_exchanges_initiator_user_id'), table_name='exchanges')
    op.drop_table('exchanges')
    sa.Enum(name='exchange_status').drop(op.get_bind(), checkfirst=True)
