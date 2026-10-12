"""add savings goals

Revision ID: e7c2a9d4b6f1
Revises: d5a1c8e3f7b2
Create Date: 2026-10-12 16:00:00.000000

Money set aside for something: goals, and each movement in or out.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e7c2a9d4b6f1'
down_revision: Union[str, None] = 'd5a1c8e3f7b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    direction = postgresql.ENUM('DEPOSIT', 'WITHDRAW', name='savings_direction', create_type=False)
    status = postgresql.ENUM(
        'PENDING', 'COMPLETED', 'FAILED', name='savings_status', create_type=False
    )
    direction.create(op.get_bind(), checkfirst=True)
    status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'savings_goals',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_user_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('target_minor', sa.BigInteger(), nullable=False),
        sa.Column('saved_minor', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('target_minor > 0', name='ck_savings_goals_target_positive'),
        sa.CheckConstraint('saved_minor >= 0', name='ck_savings_goals_saved_not_negative'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_savings_goals_owner_user_id', 'savings_goals', ['owner_user_id'])
    op.create_table(
        'savings_movements',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('reference', sa.String(length=32), nullable=False),
        sa.Column('goal_id', sa.UUID(), nullable=False),
        sa.Column('owner_user_id', sa.UUID(), nullable=False),
        sa.Column('wallet_id', sa.UUID(), nullable=False),
        sa.Column('pool_account_id', sa.UUID(), nullable=False),
        sa.Column('direction', direction, nullable=False),
        sa.Column('amount_minor', sa.BigInteger(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('status', status, server_default='PENDING', nullable=False),
        sa.Column('failure_reason', sa.String(length=255), nullable=True),
        sa.Column('idempotency_key_id', sa.UUID(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('amount_minor > 0', name='ck_savings_movements_amount_positive'),
        sa.ForeignKeyConstraint(['goal_id'], ['savings_goals.id']),
        sa.ForeignKeyConstraint(['idempotency_key_id'], ['idempotency_keys.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reference'),
    )
    op.create_index('ix_savings_movements_goal', 'savings_movements', ['goal_id', 'created_at'])
    op.create_index('ix_savings_movements_status', 'savings_movements', ['status', 'updated_at'])


def downgrade() -> None:
    op.drop_index('ix_savings_movements_status', table_name='savings_movements')
    op.drop_index('ix_savings_movements_goal', table_name='savings_movements')
    op.drop_table('savings_movements')
    op.drop_index('ix_savings_goals_owner_user_id', table_name='savings_goals')
    op.drop_table('savings_goals')
    op.execute('DROP TYPE savings_status')
    op.execute('DROP TYPE savings_direction')
