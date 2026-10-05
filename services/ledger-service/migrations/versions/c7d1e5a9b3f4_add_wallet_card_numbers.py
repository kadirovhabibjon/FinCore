"""add wallet card numbers

Revision ID: c7d1e5a9b3f4
Revises: af2fd3d94381
Create Date: 2026-10-05 13:40:00.000000

Every wallet gets a 16-digit card number to receive money by, including
the wallets that already exist: they are numbered here, before the
constraint that requires one is added.
"""
import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d1e5a9b3f4'
down_revision: Union[str, None] = 'af2fd3d94381'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# A copy of fincore_common.card_number as it was when this migration was
# written: a migration must keep doing the same thing even if that
# module changes later.
def _card_number() -> str:
    payload = '9955' + ''.join(secrets.choice('0123456789') for _ in range(11))
    total = 0
    for index, char in enumerate(reversed(payload)):
        digit = int(char)
        if index % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return payload + str((10 - total % 10) % 10)


def upgrade() -> None:
    op.add_column('ledger_accounts', sa.Column('card_number', sa.String(length=16), nullable=True))

    connection = op.get_bind()
    wallet_ids = connection.execute(
        sa.text("SELECT id FROM ledger_accounts WHERE kind = 'USER_WALLET'")
    ).scalars().all()
    used: set[str] = set()
    for wallet_id in wallet_ids:
        number = _card_number()
        while number in used:
            number = _card_number()
        used.add(number)
        connection.execute(
            sa.text("UPDATE ledger_accounts SET card_number = :number WHERE id = :id"),
            {"number": number, "id": wallet_id},
        )

    op.create_index(
        'uq_ledger_accounts_card_number', 'ledger_accounts', ['card_number'], unique=True,
        postgresql_where=sa.text('card_number IS NOT NULL'),
    )
    op.create_check_constraint(
        'ck_ledger_accounts_wallet_has_card_number', 'ledger_accounts',
        "(kind = 'USER_WALLET') = (card_number IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint('ck_ledger_accounts_wallet_has_card_number', 'ledger_accounts', type_='check')
    op.drop_index(
        'uq_ledger_accounts_card_number', table_name='ledger_accounts',
        postgresql_where=sa.text('card_number IS NOT NULL'),
    )
    op.drop_column('ledger_accounts', 'card_number')
