"""add templates

Revision ID: c9e4a7b2d5f8
Revises: b7d2e9f4a1c6
Create Date: 2026-10-09 10:00:00.000000

Saved payments: a service provider and account, or a recipient's card,
that a customer pays again and again.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c9e4a7b2d5f8'
down_revision: Union[str, None] = 'b7d2e9f4a1c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    kind = postgresql.ENUM('SERVICE', 'TRANSFER', name='template_kind', create_type=False)
    kind.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'templates',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_user_id', sa.UUID(), nullable=False),
        sa.Column('kind', kind, nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('service_code', sa.String(length=32), nullable=True),
        sa.Column('service_account', sa.String(length=64), nullable=True),
        sa.Column('card_number', sa.String(length=16), nullable=True),
        sa.Column('recipient_name', sa.String(length=255), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('amount_minor', sa.BigInteger(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.CheckConstraint(
            "(kind = 'SERVICE' AND service_code IS NOT NULL AND service_account IS NOT NULL"
            " AND card_number IS NULL) OR "
            "(kind = 'TRANSFER' AND card_number IS NOT NULL AND service_code IS NULL"
            " AND service_account IS NULL)",
            name='ck_templates_fields_match_kind',
        ),
        sa.CheckConstraint(
            'amount_minor IS NULL OR amount_minor > 0', name='ck_templates_amount_positive'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_templates_owner_user_id', 'templates', ['owner_user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_templates_owner_user_id', table_name='templates')
    op.drop_table('templates')
    op.execute('DROP TYPE template_kind')
