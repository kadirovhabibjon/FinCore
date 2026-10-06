"""add money requests

Revision ID: c6f1a4e8b2d7
Revises: b3e8f2a6d9c4
Create Date: 2026-10-06 19:00:00.000000

One customer asking another for money.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c6f1a4e8b2d7'
down_revision: Union[str, None] = 'b3e8f2a6d9c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'money_requests',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('reference', sa.String(length=32), nullable=False),
        sa.Column('requester_user_id', sa.UUID(), nullable=False),
        sa.Column('requester_wallet_id', sa.UUID(), nullable=False),
        sa.Column('payer_user_id', sa.UUID(), nullable=False),
        sa.Column('requester_name', sa.String(length=120), nullable=True),
        sa.Column('payer_name', sa.String(length=120), nullable=True),
        sa.Column('amount_minor', sa.BigInteger(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'PAYING', 'PAID', 'DECLINED', 'CANCELLED', name='money_request_status'),
            server_default='PENDING',
            nullable=False,
        ),
        sa.Column('transfer_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('amount_minor > 0', name='ck_money_requests_amount_positive'),
        sa.CheckConstraint('requester_user_id != payer_user_id', name='ck_money_requests_not_from_self'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reference'),
    )
    op.create_index(op.f('ix_money_requests_requester_user_id'), 'money_requests', ['requester_user_id'], unique=False)
    op.create_index(op.f('ix_money_requests_payer_user_id'), 'money_requests', ['payer_user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_money_requests_payer_user_id'), table_name='money_requests')
    op.drop_index(op.f('ix_money_requests_requester_user_id'), table_name='money_requests')
    op.drop_table('money_requests')
    sa.Enum(name='money_request_status').drop(op.get_bind(), checkfirst=True)
