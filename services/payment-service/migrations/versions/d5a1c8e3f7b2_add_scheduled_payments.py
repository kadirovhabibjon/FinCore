"""add scheduled payments

Revision ID: d5a1c8e3f7b2
Revises: c9e4a7b2d5f8
Create Date: 2026-10-12 12:00:00.000000

Payments FinCore makes for the customer every week or month.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd5a1c8e3f7b2'
down_revision: Union[str, None] = 'c9e4a7b2d5f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    kind = postgresql.ENUM('SERVICE', 'TRANSFER', name='template_kind', create_type=False)
    interval = postgresql.ENUM('WEEKLY', 'MONTHLY', name='schedule_interval', create_type=False)
    status = postgresql.ENUM('ACTIVE', 'PAUSED', name='schedule_status', create_type=False)
    interval.create(op.get_bind(), checkfirst=True)
    status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'scheduled_payments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_user_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('kind', kind, nullable=False),
        sa.Column('service_code', sa.String(length=32), nullable=True),
        sa.Column('service_account', sa.String(length=64), nullable=True),
        sa.Column('card_number', sa.String(length=16), nullable=True),
        sa.Column('recipient_name', sa.String(length=255), nullable=True),
        sa.Column('source_wallet_id', sa.UUID(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('amount_minor', sa.BigInteger(), nullable=False),
        sa.Column('interval', interval, nullable=False),
        sa.Column('day', sa.Integer(), nullable=False),
        sa.Column('status', status, server_default='ACTIVE', nullable=False),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_status', sa.String(length=32), nullable=True),
        sa.Column('last_error', sa.String(length=255), nullable=True),
        sa.Column('last_operation_id', sa.UUID(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.CheckConstraint(
            "(kind = 'SERVICE' AND service_code IS NOT NULL AND service_account IS NOT NULL"
            " AND card_number IS NULL) OR "
            "(kind = 'TRANSFER' AND card_number IS NOT NULL AND service_code IS NULL"
            " AND service_account IS NULL)",
            name='ck_scheduled_payments_fields_match_kind',
        ),
        sa.CheckConstraint('amount_minor > 0', name='ck_scheduled_payments_amount_positive'),
        sa.CheckConstraint(
            "(interval = 'WEEKLY' AND day BETWEEN 1 AND 7) OR "
            "(interval = 'MONTHLY' AND day BETWEEN 1 AND 28)",
            name='ck_scheduled_payments_day_fits_interval',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_scheduled_payments_owner_user_id', 'scheduled_payments', ['owner_user_id'], unique=False
    )
    op.create_index(
        'ix_scheduled_payments_due', 'scheduled_payments', ['status', 'next_run_at'], unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_scheduled_payments_due', table_name='scheduled_payments')
    op.drop_index('ix_scheduled_payments_owner_user_id', table_name='scheduled_payments')
    op.drop_table('scheduled_payments')
    op.execute('DROP TYPE schedule_status')
    op.execute('DROP TYPE schedule_interval')
