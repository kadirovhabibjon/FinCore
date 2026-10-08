"""add wallet name, primary flag and owner block

Revision ID: e8c3b7a1f5d2
Revises: d2a6f9c4e8b1
Create Date: 2026-10-08 10:00:00.000000

What a customer can set on their own wallet: a name, which one is their
main wallet, and a block that stops money leaving it. Each customer's
oldest wallet becomes their main one, so everyone who has a wallet has
exactly one main wallet from here on.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8c3b7a1f5d2'
down_revision: Union[str, None] = 'd2a6f9c4e8b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ledger_accounts', sa.Column('name', sa.String(length=40), nullable=True))
    op.add_column(
        'ledger_accounts',
        sa.Column('is_primary', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )
    op.add_column(
        'ledger_accounts', sa.Column('blocked_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        "UPDATE ledger_accounts SET is_primary = true WHERE id IN ("
        "SELECT DISTINCT ON (owner_user_id) id FROM ledger_accounts "
        "WHERE owner_user_id IS NOT NULL ORDER BY owner_user_id, created_at, id)"
    )
    op.create_index(
        'uq_ledger_accounts_primary_per_owner',
        'ledger_accounts',
        ['owner_user_id'],
        unique=True,
        postgresql_where=sa.text('is_primary'),
    )
    op.create_check_constraint(
        'ck_ledger_accounts_only_wallets_are_set_up',
        'ledger_accounts',
        "kind = 'USER_WALLET' OR "
        "(name IS NULL AND NOT is_primary AND blocked_at IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint('ck_ledger_accounts_only_wallets_are_set_up', 'ledger_accounts')
    op.drop_index('uq_ledger_accounts_primary_per_owner', table_name='ledger_accounts')
    op.drop_column('ledger_accounts', 'blocked_at')
    op.drop_column('ledger_accounts', 'is_primary')
    op.drop_column('ledger_accounts', 'name')
