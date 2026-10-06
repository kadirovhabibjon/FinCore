"""add exchange accounts

Revision ID: d2a6f9c4e8b1
Revises: c7d1e5a9b3f4
Create Date: 2026-10-06 20:00:00.000000

Currency exchange: an EXCHANGE system account per currency (FinCore's
position in it) and the EXCHANGE posting type.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2a6f9c4e8b1'
down_revision: Union[str, None] = 'c7d1e5a9b3f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# A snapshot, like the first migration's: what existed when this was written.
_SUPPORTED_CURRENCIES = ["UZS", "USD"]


def upgrade() -> None:
    # PostgreSQL won't let a transaction use an enum value it has itself
    # just added, so the two ALTER TYPEs commit on their own before the
    # rows that need them are inserted.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE account_kind ADD VALUE IF NOT EXISTS 'EXCHANGE'")
        op.execute("ALTER TYPE posting_type ADD VALUE IF NOT EXISTS 'EXCHANGE'")

    for currency in _SUPPORTED_CURRENCIES:
        op.execute(
            sa.text(
                "INSERT INTO ledger_accounts (id, kind, owner_user_id, currency) "
                "VALUES (gen_random_uuid(), 'EXCHANGE', NULL, :currency)"
            ).bindparams(currency=currency)
        )
    # Every account needs its balance row from the moment it exists.
    op.execute(
        "INSERT INTO account_balances (account_id, kind, balance_minor, held_minor, version) "
        "SELECT id, kind, 0, 0, 0 FROM ledger_accounts WHERE kind = 'EXCHANGE'"
    )


def downgrade() -> None:
    # Going back to a ledger without exchange accounts means going back
    # to one without exchanges: their postings go with the accounts, as
    # the earlier migrations' downgrades drop their tables whole. Both
    # legs of every exchange are EXCHANGE postings, so removing them
    # leaves every remaining posting balanced - but wallet balances that
    # exchanges changed are NOT recomputed here; this is a development
    # rollback, not something to run against real money.
    op.execute(
        "DELETE FROM ledger_entries WHERE posting_id IN "
        "(SELECT id FROM postings WHERE type = 'EXCHANGE')"
    )
    op.execute("DELETE FROM postings WHERE type = 'EXCHANGE'")
    op.execute("DELETE FROM account_balances WHERE kind = 'EXCHANGE'")
    op.execute("DELETE FROM ledger_accounts WHERE kind = 'EXCHANGE'")
    # PostgreSQL cannot drop an enum value, so 'EXCHANGE' stays in both
    # types; ADD VALUE IF NOT EXISTS above makes upgrading again harmless.
