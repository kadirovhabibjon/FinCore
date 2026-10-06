"""add payment merchant snapshot

Revision ID: a9d3e7b1c5f2
Revises: f2b6d9c1a4e7
Create Date: 2026-10-06 16:00:00.000000

The merchant's name and owner as they were when a payment was made, for
notifications to the payer and the merchant.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9d3e7b1c5f2'
down_revision: Union[str, None] = 'f2b6d9c1a4e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('payments', sa.Column('merchant_name', sa.String(length=255), nullable=True))
    op.add_column('payments', sa.Column('merchant_owner_user_id', sa.UUID(), nullable=True))
    # Existing payments can be filled in: the merchant rows are right here.
    op.execute(
        "UPDATE payments p SET merchant_name = m.name, merchant_owner_user_id = m.owner_user_id "
        "FROM merchants m WHERE m.id = p.merchant_id"
    )


def downgrade() -> None:
    op.drop_column('payments', 'merchant_owner_user_id')
    op.drop_column('payments', 'merchant_name')
