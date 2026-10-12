"""add savings accounts

Revision ID: f1b5d9c3a7e4
Revises: e8c3b7a1f5d2
Create Date: 2026-10-12 15:00:00.000000

Savings goals: a pooled SAVINGS system account per currency (what
customers have set aside) and the SAVINGS posting type.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1b5d9c3a7e4'
down_revision: Union[str, None] = 'e8c3b7a1f5d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# A snapshot, like the earlier migrations': what existed when this was written.
_SUPPORTED_CURRENCIES = ["UZS", "USD"]


def upgrade() -> None:
    # PostgreSQL won't let a transaction use an enum value it has itself
    # just added, so the two ALTER TYPEs commit on their own first.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE account_kind ADD VALUE IF NOT EXISTS 'SAVINGS'")
        op.execute("ALTER TYPE posting_type ADD VALUE IF NOT EXISTS 'SAVINGS'")

    for currency in _SUPPORTED_CURRENCIES:
        op.execute(
            sa.text(
                "INSERT INTO ledger_accounts (id, kind, owner_user_id, currency) "
                "VALUES (gen_random_uuid(), 'SAVINGS', NULL, :currency)"
            ).bindparams(currency=currency)
        )
    # Every account needs its balance row from the moment it exists.
    op.execute(
        "INSERT INTO account_balances (account_id, kind, balance_minor, held_minor, version) "
        "SELECT id, kind, 0, 0, 0 FROM ledger_accounts WHERE kind = 'SAVINGS'"
    )


def downgrade() -> None:
    # A ledger without savings accounts is one without savings: the
    # postings go with the accounts, as in the exchange migration, and
    # wallet balances they changed are NOT recomputed. A development
    # rollback, not something to run against real money.
    op.execute(
        "DELETE FROM ledger_entries WHERE posting_id IN "
        "(SELECT id FROM postings WHERE type = 'SAVINGS')"
    )
    op.execute("DELETE FROM postings WHERE type = 'SAVINGS'")
    op.execute("DELETE FROM account_balances WHERE kind = 'SAVINGS'")
    op.execute("DELETE FROM ledger_accounts WHERE kind = 'SAVINGS'")
    # PostgreSQL cannot drop an enum value, so 'SAVINGS' stays in both
    # types; ADD VALUE IF NOT EXISTS above makes upgrading again harmless.
